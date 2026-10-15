#!/usr/bin/env python3
"""Verify exact unavailable crypto ABI without substituting security success."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import sys

import build_nvidia_transport as transport

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/nvidia-global-rm-crypto'
EXPECTED = {'status': 'passed', 'checks': 603, 'failures': 0,
            'component': 'nvidia-global-rm-crypto-unavailable',
            'abi_symbols': 64, 'serial_refusals': 128,
            'concurrent_refusals': 16384, 'crypto_implemented': False,
            'caller_memory_unchanged': True, 'gpu_access': False,
            'execution': 'native-user-space', 'kernel_execution': 'not_tested'}


def compiler_pair(host_control: bool) -> tuple[list[str], list[str]]:
    if not host_control:
        return ['/usr/bin/xcrun', 'clang'], ['/usr/bin/xcrun', 'clang++']
    cc = shutil.which(os.environ.get('CC', 'clang'))
    cxx = shutil.which(os.environ.get('CXX', 'clang++'))
    if not cc or not cxx:
        raise ValueError('Explicit host controls require available C/C++ compilers (CC/CXX).')
    return [cc], [cxx]


def verify_binary(path: Path, kind: int, host_control: bool) -> None:
    if not host_control:
        transport.macho(path, kind)
        if kind == 2:
            transport.run('/usr/bin/codesign', '--force', '--sign', '-', str(path))
            transport.run('/usr/bin/codesign', '--verify', '--strict', str(path))
        return
    header = path.read_bytes()[:20]
    if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01'
            or struct.unpack_from('<H', header, 18)[0] != 62
            or struct.unpack_from('<H', header, 16)[0] not in ({1} if kind == 1 else {2, 3})):
        raise ValueError('A host-control output is not the expected x86_64 ELF object/executable.')


def check(output: Path, upstream: Path | None = None, *, host_control: bool = False) -> dict:
    if not host_control and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
        raise ValueError('Authoritative crypto boundary checks require Intel macOS.')
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    provenance = [sys.executable, str(PACKAGE / 'tests/test_crypto_provenance.py')]
    if upstream is not None:
        provenance += ['--upstream', str(upstream.resolve(strict=True))]
    checked = transport.run(*provenance)
    print((checked.stdout + checked.stderr).strip())
    cc, cxx = compiler_pair(host_control)
    target = [] if host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0']
    common = [*target, '-O1', '-g',
              '-Wall', '-Wextra', '-Werror', '-Wundef',
              '-I', str(ROOT / 'packages/nvidia-os-adapter/upstream/include')]
    results = {}
    for label, instrumentation in (('native', []), ('sanitized', [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
            '-fno-omit-frame-pointer'])):
        work = output / label
        work.mkdir(exist_ok=True)
        objects = []
        for source in (PACKAGE / 'tests/check_crypto_abi.c',
                       PACKAGE / 'src/S540NvidiaGlobalCrypto.c'):
            obj = work / (source.stem + '.o')
            transport.run(*cc, '-std=c11', *common,
                          *instrumentation, '-c', str(source), '-o', str(obj))
            verify_binary(obj, 1, host_control)
            objects.append(str(obj))
        binary = work / 'check-crypto-unavailable'
        transport.run(*cxx, '-std=c++17', '-pthread',
                      *common, *instrumentation,
                      str(PACKAGE / 'tests/check_crypto_unavailable_native.cpp'),
                      *objects, '-o', str(binary))
        verify_binary(binary, 2, host_control)
        result = json.loads(transport.run(str(binary)).stdout)
        for key, value in EXPECTED.items():
            if type(result.get(key)) is not type(value) or result[key] != value:
                raise ValueError('The exact crypto refusal checks changed: ' + label + '/' + key)
        results[label] = result
    inputs = [path for path in PACKAGE.rglob('*') if path.is_file()
              and '__pycache__' not in path.parts and path.suffix != '.pyc']
    record = {'format': 1, 'component': 'nvidia-global-rm-crypto',
              'status': 'passed', 'architecture': 'x86_64',
              'host_system': platform.system(),
              'authoritative_darwin_execution': not host_control,
              'native_execution': results, 'crypto_implemented': False,
              'kernel_runtime': 'not_tested', 'gpu_access': False,
              'source_sha256': {path.relative_to(ROOT).as_posix():
                  hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(inputs)}}
    (output / 'global-crypto-checks.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--host-control', action='store_true',
                        help='Explicit Linux ELF control; never authoritative Darwin evidence.')
    args = parser.parse_args()
    check(args.output_dir, args.upstream, host_control=args.host_control)
    print('The 64 exact unavailable-crypto contracts passed native and fatal sanitizer checks.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
