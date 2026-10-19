#!/usr/bin/env python3
"""Relocatable helpers for this opt-in source-only candidate."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
V3 = REPO / 'packages/nvidia-gsp-bootstrap/prospective-v3'
sys.path.insert(0, str(REPO / 'builders'))
import compile_nvidia_global_rm as original
import check_nvidia_execution as execution
sys.path.insert(0, str(REPO / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

SDK_COMMIT = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
SDK_ARCHIVE_SHA = '8931e622b6d16a7052cb2c2dabe16be06963a34b747f19e6cda2bbe8bc7e2557'

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def contract() -> dict:
    result = json.loads((HERE / 'SOURCE-CONTRACT.json').read_text())
    if sha((REPO / result['base_profile']).read_bytes()) != result['base_profile_sha256']:
        raise ValueError('The frozen V3 source contract changed.')
    if sha((HERE / result['patch']).read_bytes()) != result['patch_sha256']:
        raise ValueError('The isolated first-transaction patch changed.')
    return result

def output_path(path: Path, upstream: Path) -> Path:
    path = path.resolve()
    build = REPO / 'build'
    if REPO.is_relative_to(path) or (path.is_relative_to(REPO) and
            not (path != build and path.is_relative_to(build))):
        raise ValueError('Repository output is allowed only under the canonical build directory.')
    if path.is_relative_to(upstream) or upstream.is_relative_to(path):
        raise ValueError('Output must not contain or be contained by upstream.')
    # Reuse is needed for check.py followed by compile_full.py. Existing
    # generated paths must still be ordinary files/directories: a source or
    # objects symlink could redirect a later write into an input tree.
    if path.exists() and any(p.is_symlink() for p in path.rglob('*')):
        raise ValueError('Reusable output must not contain symlinks.')
    path.mkdir(parents=True, exist_ok=True)
    return path

def compiler(value: str) -> Path:
    selected = shutil.which(value) if '/' not in value else value
    if selected is None:
        raise ValueError('Compiler not found: ' + value)
    # Driver basename is semantic: resolving clang++'s symlink to clang drops
    # the default C++ runtime link. Preserve the caller's executable path.
    path = Path(selected).absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Compiler is not executable: ' + str(path))
    return path

def execution_identity(cc: Path, cxx: Path, host_control: bool) -> dict:
    native = sys.platform == 'darwin' and platform.machine() == 'x86_64'
    if not host_control and not native:
        raise ValueError('Authoritative controls require Intel macOS; select --host-control for Linux ELF controls.')
    if host_control and (sys.platform != 'linux' or platform.machine() != 'x86_64'):
        raise ValueError('--host-control is an explicit Linux x86_64 control, not authoritative Darwin execution.')
    versions = {}
    for label, path in [('cc', cc), ('cxx', cxx)]:
        result = original.execute([str(path), '--version']).stdout
        if not host_control and 'Apple clang' not in result:
            raise ValueError('Authoritative controls require the actual Apple compiler: ' + str(path))
        versions[label] = {'path': str(path), 'version': result.splitlines()[0]}
    return {'authoritative_darwin_execution': not host_control,
            'host_control': host_control, 'host_system': platform.system(), 'compilers': versions}

def parser(description: str, *, compile_only: bool = False) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    for name in ('upstream', 'namespace', 'output'):
        result.add_argument('--' + name, type=Path, required=True)
    result.add_argument('--cc', required=True)
    result.add_argument('--cxx', required=True)
    result.add_argument('--v3-root', type=Path)
    result.add_argument('--host-control', action='store_true')
    if compile_only:
        result.add_argument('--sdk', type=Path)
        result.add_argument('--sdk-archive', type=Path)
    return result

def resolve_arguments(args):
    args.upstream = args.upstream.resolve(strict=True)
    args.namespace = args.namespace.resolve(strict=True)
    args.output = output_path(args.output, args.upstream)
    args.cc, args.cxx = compiler(args.cc), compiler(args.cxx)
    if args.v3_root is not None:
        args.v3_root = args.v3_root.resolve(strict=True)
    return args, execution_identity(args.cc, args.cxx, args.host_control)

def validate_sdk(sdk: Path | None, archive: Path | None, host_control: bool) -> dict:
    if sdk is None:
        value = os.environ.get('MAC_KERNEL_SDK') or os.environ.get('KERNEL_SDK')
        if value:
            sdk = Path(value)
        elif host_control:
            raise ValueError('A non-Apple cross probe requires --sdk (and --sdk-archive for an archive extraction).')
        else:
            # These are original C TUs and a C prototype bridge, with no IOKit
            # declarations. Do not invent pinned kernel-SDK evidence from Xcode.
            return {'used_by_original_c_tus': False, 'provided': False,
                    'native_apple_compiler': True, 'kernel_sdk_identity_claimed': False}
    sdk = sdk.resolve(strict=True)
    files = {}
    if archive is not None:
        archive = archive.resolve(strict=True)
        if sha(archive.read_bytes()) != SDK_ARCHIVE_SHA:
            raise ValueError('Kernel SDK archive differs from its pinned bytes.')
        prefix = 'MacKernelSDK-' + SDK_COMMIT + '/'
        with tarfile.open(archive, 'r:gz') as source:
            for member in source.getmembers():
                if member.isdir():
                    continue
                if not member.isfile() or not member.name.startswith(prefix):
                    raise ValueError('Unexpected kernel SDK archive entry.')
                name = member.name[len(prefix):]
                data = source.extractfile(member).read()
                target = sdk / name
                if target.is_symlink() or target.read_bytes() != data:
                    raise ValueError('Kernel SDK differs from pinned archive: ' + name)
                files[name] = sha(data)
        observed = {p.relative_to(sdk).as_posix() for p in sdk.rglob('*') if p.is_file()}
        if observed != set(files):
            raise ValueError('Kernel SDK has extra or missing files.')
        identity = {'archive_sha256': SDK_ARCHIVE_SHA, 'source': 'exact pinned archive and full file inventory'}
    else:
        def git(*values):
            return original.execute(['git', '-C', str(sdk), *values]).stdout
        if git('rev-parse', 'HEAD').strip() != SDK_COMMIT:
            raise ValueError('Kernel SDK revision differs from its pinned commit.')
        if git('status', '--porcelain', '--untracked-files=all'):
            raise ValueError('Kernel SDK checkout is dirty.')
        for entry in git('ls-tree', '-rz', 'HEAD').split('\0'):
            if not entry:
                continue
            metadata, name = entry.split('\t', 1)
            mode, kind, blob = metadata.split()
            target = sdk / name
            if kind != 'blob' or mode not in ('100644', '100755') or target.is_symlink():
                raise ValueError('Unsupported kernel SDK tree entry: ' + name)
            data = target.read_bytes()
            if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != blob:
                raise ValueError('Kernel SDK tracked bytes changed: ' + name)
            files[name] = sha(data)
        identity = {'source': 'clean pinned Git checkout and every tracked blob'}
    return {'provided': True, 'reference_commit': SDK_COMMIT, **identity,
            'file_count': len(files), 'tree_sha256': sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()),
            'used_by_original_c_tus': False}
