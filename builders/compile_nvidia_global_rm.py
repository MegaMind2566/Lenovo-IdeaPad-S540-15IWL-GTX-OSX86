#!/usr/bin/env python3
"""Compile pinned RM and explicit checked overlays under a Darwin profile.

This compilation audit is independent of driver runtime evidence. It never
executes rm_init_rm, rm_init_adapter, firmware, or GPU commands.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/nvidia-global-rm'
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
RELEASE = '615.78.08'
PREFIX = 's540Global_'
COMPILER_MEMORY_IMPORTS = {'__bzero', 'bzero', 'memcpy', 'memset', 'memmove'}
GLOBAL_ROOTS = ('rm_init_rm', 'rm_shutdown_rm')
ADAPTER_ROOTS = (*GLOBAL_ROOTS, 'rm_init_adapter', 'rm_shutdown_adapter',
                 'rm_disable_adapter', 'rm_isr', 'rm_isr_bh', 'rm_isr_bh_unlocked')
MH_BUNDLE = 8
MH_KEXT_BUNDLE = 11
DYLIB_LOAD_COMMANDS = {0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023}
CHECKED_PROFILE = 'checked-cleanup-development'
CHECKED_MANIFEST = 'checked-source-manifest.json'
CHECKED_PATCHES = ('nvlog_printf-init-unwind.patch', 'journal-construction-guard.patch',
                   'thread-state-unwind.patch', 'portable-memory-init-checked.patch',
                   'resource-server-construction-unwind.patch',
                   'system-resource-lifetime-unwind.patch', 'rmapi-lock-tls-failure-unwind.patch',
                   'registry-profile-init-propagation.patch',
                   'nvoc-static-cast-single-evaluation.patch',
                   'iterator-dispatch-typed-abi.patch')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pinned_upstream(upstream: Path) -> Path:
    upstream = upstream.resolve(strict=True)
    if execute(['git', '-C', str(upstream), 'rev-parse', 'HEAD']).stdout.strip() != COMMIT:
        raise ValueError('The original RM source revision differs from its pinned commit.')
    if execute(['git', '-C', str(upstream), 'status', '--porcelain']).stdout:
        raise ValueError('Original RM compilation requires an unchanged upstream checkout.')
    return upstream


def _strict_patch(files: dict[str, bytes], patch: bytes) -> dict[str, bytes]:
    """Apply exact unified hunks in memory: no offsets, fuzz, rename or creation."""
    lines = patch.decode('utf-8').splitlines(keepends=True)
    changed, i = {}, 0
    while i < len(lines):
        if not lines[i].startswith('--- a/') or i + 1 >= len(lines):
            raise ValueError('An approved patch has an invalid file header.')
        name = lines[i][6:].rstrip('\n')
        if (lines[i + 1] != '+++ b/' + name + '\n' or name not in files
                or name in changed or Path(name).is_absolute() or '..' in Path(name).parts):
            raise ValueError('An approved patch has an invalid or repeated source path.')
        original = files[name].decode('utf-8').splitlines(keepends=True)
        out, position, hunks = [], 0, 0
        i += 2
        while i < len(lines) and not lines[i].startswith('--- a/'):
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[i])
            if match is None:
                raise ValueError('An approved patch has an invalid hunk header.')
            start, old_count = int(match[1]) - 1, int(match[2] or 1)
            if start < position or start > len(original):
                raise ValueError('An approved patch hunk is out of order or range.')
            out.extend(original[position:start])
            position, old_seen, new_seen = start, 0, 0
            if len(out) != int(match[3]) - 1:
                raise ValueError('An approved patch changes its declared hunk offset.')
            i += 1
            while i < len(lines) and not lines[i].startswith(('@@ ', '--- a/')):
                line = lines[i]
                if line[:1] not in (' ', '-', '+'):
                    raise ValueError('An approved patch has unsupported hunk content.')
                if line[:1] in (' ', '-'):
                    if position >= len(original) or original[position] != line[1:]:
                        raise ValueError('An approved patch source context changed: ' + name)
                    position += 1
                    old_seen += 1
                if line[:1] in (' ', '+'):
                    out.append(line[1:])
                    new_seen += 1
                i += 1
            if old_seen != old_count or new_seen != int(match[4] or 1):
                raise ValueError('An approved patch hunk count is invalid.')
            hunks += 1
        if not hunks:
            raise ValueError('An approved patch has no hunks.')
        changed[name] = ''.join(out + original[position:]).encode('utf-8')
    return changed


def _checked_profile(upstream: Path) -> tuple[dict, dict[str, bytes]]:
    """Reconstruct expected bytes from pinned Git blobs and reviewed manifests."""
    upstream = _pinned_upstream(upstream)
    tree = execute(['git', '-C', str(upstream), 'ls-tree', '-rz', COMMIT]).stdout
    original, modes = {}, {}
    for entry in tree.split('\0'):
        if not entry:
            continue
        metadata, name = entry.split('\t', 1)
        mode, kind, blob = metadata.split()
        source = upstream / name
        if (kind != 'blob' or mode not in ('100644', '100755') or source.is_symlink()
                or not source.is_file() or not source.resolve().is_relative_to(upstream)):
            raise ValueError('The pinned source inventory contains an unsupported file: ' + name)
        data = source.read_bytes()
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != blob:
            raise ValueError('A pinned source does not match its original Git blob: ' + name)
        original[name], modes[name] = data, mode
    if len(original) != 4005:
        raise ValueError('The pinned complete upstream file inventory changed.')
    manifest_path = PACKAGE / 'upstream/ADAPTATIONS.json'
    audit_path = PACKAGE / 'upstream/adapted/CHECKED-INTEGRATION-AUDIT.json'
    manifest, audit = json.loads(manifest_path.read_bytes()), json.loads(audit_path.read_bytes())
    adaptations = manifest['adaptations']
    if ([Path(item['patch']).name for item in adaptations] != list(CHECKED_PATCHES)
            or audit['commit'] != COMMIT or manifest.get('commit') != COMMIT
            or audit.get('profile') != CHECKED_PROFILE):
        raise ValueError('The approved checked-overlay profile identity changed.')
    adapted, patches = dict(original), []
    for item in adaptations:
        name = Path(item['patch']).name
        patch = (PACKAGE / 'upstream/adapted' / name).read_bytes()
        if _sha(patch) != item['patch_sha256']:
            raise ValueError('An approved patch hash changed: ' + name)
        descriptors = item.get('sources') or [{'path': item['source'],
            'upstream_sha256': item['upstream_sha256'], 'adapted_sha256': item['adapted_sha256']}]
        standalone = _strict_patch(original, patch)
        if set(standalone) != {d['path'] for d in descriptors}:
            raise ValueError('A patch changes sources outside its approved manifest: ' + name)
        for descriptor in descriptors:
            path = descriptor['path']
            if (_sha(original[path]) != descriptor['upstream_sha256']
                    or _sha(standalone[path]) != descriptor['adapted_sha256']):
                raise ValueError('An approved standalone source hash changed: ' + path)
        adapted.update(_strict_patch(adapted, patch))
        patches.append({'path': item['patch'], 'sha256': _sha(patch)})
    if patches != audit['patches']:
        raise ValueError('The combined source audit uses a different overlay set.')
    approved = {item['path']: item['sha256'] for item in audit['composed_sources']}
    if len(approved) != len(audit['composed_sources']):
        raise ValueError('The composed source audit contains a duplicate source.')
    changed = {name: data for name, data in adapted.items() if data != original[name]}
    if set(changed) != set(approved) or any(_sha(data) != approved[name] for name, data in changed.items()):
        raise ValueError('The complete composed source/header bytes differ from their approved audit.')
    def files(values):
        return {name: {'sha256': _sha(data), 'mode': modes[name]} for name, data in sorted(values.items())}
    baseline_files, adapted_files = files(original), files(adapted)
    digest = lambda value: _sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())
    return {'format': 1, 'profile': CHECKED_PROFILE, 'commit': COMMIT,
            'source_semantics_unchanged': False, 'production_candidate_allowed': False,
            'kernel_execution': 'not_tested', 'gpu_access': False,
            'adaptations_manifest_sha256': _sha(manifest_path.read_bytes()),
            'combined_audit_sha256': _sha(audit_path.read_bytes()), 'patches': patches,
            'file_count': len(adapted_files), 'files': adapted_files,
            'upstream_tree_sha256': digest(baseline_files), 'tree_sha256': digest(adapted_files),
            'changed_files': approved, 'checked_memory_header': audit['checked_memory_header']}, changed


def _verify_workspace(directory: Path, expected: dict) -> None:
    observed = {}
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise ValueError('A checked source workspace contains a symlink.')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('A checked source workspace contains a non-regular file.')
        observed[path.relative_to(directory).as_posix()] = {
            'sha256': _sha(path.read_bytes()), 'mode': '100755' if path.stat().st_mode & 0o111 else '100644'}
    if observed != expected['files']:
        raise ValueError('The complete checked source workspace changed or contains extra files.')


def prepare_checked_source(upstream: Path, directory: Path) -> dict:
    directory = directory.absolute()
    if directory.resolve().is_relative_to(upstream.resolve(strict=True)):
        raise ValueError('The checked-source workspace must be isolated from the pinned checkout.')
    manifest_path = directory.parent / CHECKED_MANIFEST
    if directory.exists() or manifest_path.exists():
        raise ValueError('Checked-source preparation requires a fresh workspace and manifest.')
    expected, changed = _checked_profile(upstream)
    expected['directory'] = directory.name
    directory.mkdir(parents=True)
    for name, item in expected['files'].items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in changed:
            target.write_bytes(changed[name])
        else:
            shutil.copyfile(upstream / name, target)
        target.chmod(int(item['mode'], 8) & 0o777)
    _verify_workspace(directory, expected)
    raw = (json.dumps(expected, indent=2, sort_keys=True) + '\n').encode()
    with manifest_path.open('xb') as stream:
        stream.write(raw)
    return {**expected, 'manifest_sha256': _sha(raw)}


def validate_checked_source(upstream: Path, directory: Path) -> dict:
    if directory.is_symlink():
        raise ValueError('The checked-source workspace must not be a symlink.')
    directory = directory.resolve(strict=True)
    expected, _ = _checked_profile(upstream)
    expected['directory'] = directory.name
    manifest_path = directory.parent / CHECKED_MANIFEST
    if manifest_path.is_symlink():
        raise ValueError('The checked-source manifest must be a regular file.')
    raw = manifest_path.read_bytes()
    if json.loads(raw) != expected:
        raise ValueError('The checked-source manifest differs from its reconstructed approved profile.')
    _verify_workspace(directory, expected)
    return {**expected, 'manifest_sha256': _sha(raw)}


def execute(args: list[str], *, cwd: Path | None = None,
            timeout: int = 180, diagnostic_log: Path | None = None) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                                timeout=timeout)
    except subprocess.TimeoutExpired as error:
        # TimeoutExpired may retain bytes even when text mode was requested.
        def decoded(value: str | bytes | None) -> str:
            return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
        result = subprocess.CompletedProcess(args, -1, decoded(error.stdout), decoded(error.stderr))
        failure = 'Command timed out after ' + str(timeout) + ' seconds'
    else:
        failure = 'Command failed with exit status ' + str(result.returncode)
    if diagnostic_log is not None:
        diagnostic_log.write_text('stdout:\n' + result.stdout + '\nstderr:\n' + result.stderr)
    if result.returncode:
        # A link command contains 1,100 object paths. Preserve its diagnostics
        # instead of replacing them with CalledProcessError's enormous argv.
        detail = result.stderr.strip() or result.stdout.strip() or 'No diagnostic output was returned.'
        if len(detail) > 8000:
            detail = '[Earlier diagnostic output omitted.]\n' + detail[-8000:]
        log = '\nFull diagnostics: ' + str(diagnostic_log) if diagnostic_log is not None else ''
        raise RuntimeError(failure + ': ' + shlex.join(args[:2]) + ' (' + str(len(args)) +
                           ' arguments)\n' + detail + log)
    return result


def original_commands(upstream: Path, output: Path, compiler: Path) -> list[list[str]]:
    """Extract the upstream make-declared source profile without executing it."""
    dry = execute(['make', '-B', '-n', '-C', str(upstream / 'src/nvidia'),
                   'OUTPUTDIR=' + str(output), 'NV_BUILD_USER=build', 'NV_BUILD_HOST=ci',
                   'TARGET_OS=Darwin', 'TARGET_ARCH=x86_64', 'NV_VERBOSE=1',
                   'NV_AUTO_DEPEND=0', 'CC=' + str(compiler)]).stdout
    commands = [shlex.split(line.split(' && ')[0]) for line in dry.splitlines()
                if line.startswith(str(compiler) + ' ') and ' -c ' in line]
    if len(commands) != 1100:
        raise ValueError('The original source profile must declare exactly 1,100 C translation units.')
    return commands


def original_bridge_flags(upstream: Path, output: Path, compiler: Path,
                          namespace: Path, *, checked_source: Path | None = None) -> list[str]:
    """Give original-header bridge TUs the same actual C ABI/profile as RM."""
    command = original_commands(upstream, output, compiler)[0]
    flags = command[1:command.index('-c')]
    if checked_source is not None:
        validate_checked_source(upstream, checked_source)
    source_root = (checked_source if checked_source is not None else upstream) / 'src/nvidia'
    normalized, index = [], 0
    while index < len(flags):
        flag = flags[index]
        normalized.append(flag)
        if flag in ('-I', '-include'):
            index += 1
            normalized.append(str((source_root / flags[index]).resolve(strict=flag == '-include')))
        index += 1
    return [*normalized, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
            '-DNV_VERSION_STRING="' + RELEASE + '"', '-include', str(namespace.resolve(strict=True))]


def macho_symbols(path: Path, *, expected_type: int = 1,
                  reviewed_project_initializers: bool = False) -> tuple[set[str], set[str], list[str]]:
    """Read exact external nlist records without requiring a host Mach-O nm."""
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError('A Mach-O object is truncated: ' + path.name)
    magic, cpu, _, filetype, commands, _, _, _ = struct.unpack_from('<8I', data)
    if (magic, cpu, filetype) != (0xfeedfacf, 0x01000007, expected_type):
        raise ValueError('An original RM output is not a thin x86_64 Mach-O object: ' + path.name)
    offset, table, sections = 32, None, []
    for _ in range(commands):
        command, size = struct.unpack_from('<II', data, offset)
        if size < 8 or offset + size > len(data):
            raise ValueError('Invalid Mach-O load command.')
        if expected_type == MH_KEXT_BUNDLE and command in DYLIB_LOAD_COMMANDS:
            raise ValueError('A kernel dependency-control image links a dynamic library.')
        if command == 2:
            table = struct.unpack_from('<4I', data, offset + 8)
        if command == 0x19:
            count = struct.unpack_from('<I', data, offset + 64)[0]
            for index in range(count):
                section = offset + 72 + index * 80
                if section + 80 > offset + size:
                    raise ValueError('Invalid Mach-O section table.')
                sections.append(data[section:section + 16].split(b'\0', 1)[0].decode('ascii'))
        offset += size
    if not reviewed_project_initializers and ('__mod_init_func' in sections or '__mod_term_func' in sections):
        raise ValueError('An original RM object contains implicit initialization: ' + path.name)
    # Original architecture/profile gates intentionally produce empty objects.
    if table is None:
        return set(), set(), sections
    symbol_offset, count, string_offset, string_size = table
    if symbol_offset + count * 16 > len(data) or string_offset + string_size > len(data):
        raise ValueError('Invalid Mach-O symbol table range.')
    defined, undefined = set(), set()
    for index in range(count):
        name_offset, kind, _, _, value = struct.unpack_from('<IBBHQ', data, symbol_offset + index * 16)
        if kind & 0xe0 or not kind & 1 or not name_offset:
            continue
        if name_offset >= string_size:
            raise ValueError('Invalid Mach-O symbol name offset.')
        end = data.find(b'\0', string_offset + name_offset, string_offset + string_size)
        if end < 0:
            raise ValueError('Unterminated Mach-O symbol name.')
        symbol = data[string_offset + name_offset:end].decode('ascii')
        if not symbol.startswith('_'):
            raise ValueError('Unexpected Darwin C external spelling: ' + symbol)
        symbol = symbol[1:]
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', symbol):
            raise ValueError('Unexpected original RM C external identifier: ' + symbol)
        if kind & 0x0e == 0 and value == 0:
            undefined.add(symbol)
        else:
            defined.add(symbol)
    return defined, undefined, sections


def namespace_contract(objects: list[Path], output: Path) -> dict:
    defined, referenced = set(), set()
    for path in objects:
        object_defined, object_referenced, _ = macho_symbols(path)
        defined.update(object_defined)
        referenced.update(object_referenced)
    external = referenced - defined
    # These names are emitted by the compiler, not original source services.
    compiler = {name for name in external if name.startswith('__') or name in COMPILER_MEMORY_IMPORTS}
    unexpected_compiler = compiler - COMPILER_MEMORY_IMPORTS - {'__stack_chk_fail', '__stack_chk_guard',
        '__udivti3', '__umodti3', '__divti3', '__modti3', '__ashlti3', '__lshrti3', '__ashrti3'}
    if unexpected_compiler:
        raise ValueError('Unreviewed compiler-generated RM imports: ' + str(sorted(unexpected_compiler)))
    if any(name.startswith('__x86_indirect_thunk_') for name in referenced):
        raise ValueError('Linux retpoline ABI must not enter the Darwin profile.')
    aliases = sorted(defined | (external - compiler))
    header = ('/* Generated from all original Darwin Mach-O C external symbols. */\n'
              '/* Source semantics are unchanged; the private namespace isolates full RM from standalone RS. */\n'
              '#ifndef S540_GLOBAL_RM_NAMESPACE_H\n#define S540_GLOBAL_RM_NAMESPACE_H\n' +
              ''.join('#define ' + name + ' ' + PREFIX + name + '\n' for name in aliases) +
              '#endif\n')
    record = {'format': 1, 'commit': COMMIT, 'release': RELEASE,
              'profile': 'NV_UNIX=1; actual Darwin/Apple compiler target; RS_STANDALONE=0',
              'source_units': 1099, 'generated_identification_units': 1,
              'prefix': PREFIX, 'defined_count': len(defined),
              'external_count': len(external), 'alias_count': len(aliases),
              'defined': sorted(defined), 'external': sorted(external),
              'compiler_helpers': sorted(compiler),
              'namespace_sha256': hashlib.sha256(header.encode()).hexdigest(),
              'global_rm_executed': False, 'adapter_initialized': False,
              'firmware_loaded': False, 'gpu_commands': False}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'S540GlobalRmNamespace.h').write_text(header)
    (output / 'SOURCE-CONTRACT.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def compile_with_namespace(upstream: Path, output: Path, compiler: Path,
                           *, cross_probe: bool = False,
                           linker: Path | None = None) -> dict:
    """Generate the large source-derived header during the build, never in git."""
    output = output.absolute()
    baseline = compile_original(upstream, output / 'original', compiler,
                                cross_probe=cross_probe)
    observed = baseline['namespace_contract']
    expected = json.loads((PACKAGE / 'upstream/adapted/SOURCE-CONTRACT.json').read_text())
    keys = ('format', 'commit', 'release', 'profile', 'source_units',
            'generated_identification_units', 'prefix', 'defined_count',
            'alias_count', 'namespace_sha256')
    mismatches = {key: {'expected': expected.get(key), 'observed': observed.get(key)}
                  for key in keys if type(expected.get(key)) is not type(observed.get(key))
                  or expected[key] != observed[key]}
    if mismatches:
        raise ValueError('The pinned source-derived private namespace changed: ' +
                         json.dumps(mismatches, sort_keys=True))
    header = output / 'original/contract/S540GlobalRmNamespace.h'
    record = compile_original(upstream, output / 'namespaced', compiler,
                              cross_probe=cross_probe, namespace=header, linker=linker,
                              summary_path=output / 'darwin-compile.json')
    record['source_namespace_verified'] = True
    record['source_namespace_contract'] = expected
    record['generated_namespace_header'] = 'original/contract/S540GlobalRmNamespace.h'
    (output / 'darwin-compile.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    if 'dependency_controls' in record:
        (output / 'dependency-controls.json').write_text(
            json.dumps(record['dependency_controls'], indent=2, sort_keys=True) + '\n')
    return record


def audit_namespace(objects: list[Path], namespace: Path) -> dict:
    aliases = re.findall(r'^#define ([A-Za-z_][A-Za-z0-9_]*) ' + PREFIX +
                         r'\1$', namespace.read_text(), re.M)
    if not aliases or len(aliases) != len(set(aliases)):
        raise ValueError('The full RM namespace header is empty or ambiguous.')
    defined, referenced = set(), set()
    for path in objects:
        defs, refs, _ = macho_symbols(path)
        defined.update(defs)
        referenced.update(refs)
    external = referenced - defined
    escaped = {symbol for symbol in defined if not symbol.startswith(PREFIX)}
    unsupported = {symbol for symbol in external
                   if not symbol.startswith(PREFIX) and symbol not in COMPILER_MEMORY_IMPORTS}
    if escaped or unsupported:
        raise ValueError('Full RM escaped its private C namespace: definitions=' +
                         str(sorted(escaped)) + '; imports=' + str(sorted(unsupported)))
    original_definitions = {symbol[len(PREFIX):] for symbol in defined}
    if not original_definitions <= set(aliases):
        raise ValueError('The namespace manifest does not cover every original definition.')
    return {'format': 1, 'prefix': PREFIX, 'alias_count': len(aliases),
            'defined_count': len(defined), 'external_count': len(external),
            'defined': sorted(defined), 'external': sorted(external),
            'compiler_memory_imports': sorted(external & COMPILER_MEMORY_IMPORTS),
            'unprefixed_definitions': [],
            'namespace_sha256': hashlib.sha256(namespace.read_bytes()).hexdigest()}


def link_dependency_controls(objects: list[Path], output: Path,
                             linker: list[str], *, cross_probe: bool = False) -> dict:
    """Inspect real Mach-O root reachability; unresolved images are never loaded."""
    # Native original RM uses -mkernel/-fno-pic. Apple ld's -kext profile
    # permits its kernel text relocations and leaves kernel symbols unresolved
    # without a user-space libSystem dependency. The explicit Zig PIC cross
    # probe uses a normal bundle because its LLD linker has no -kext support;
    # this is a different output profile, never a native fallback.
    filetype = MH_BUNDLE if cross_probe else MH_KEXT_BUNDLE
    output_kind = '-bundle' if cross_probe else '-kext'
    records = {}
    for name, roots in (('global', GLOBAL_ROOTS), ('adapter', ADAPTER_ROOTS)):
        image = output / (name + '-dependency-control.bundle')
        args = [*linker, '-arch', 'x86_64', '-platform_version', 'macos', '15.0', '15.0',
                output_kind, '-undefined', 'dynamic_lookup', '-dead_strip', '-no_uuid']
        args += [value for root in roots for value in ('-exported_symbol', '_' + PREFIX + root)]
        execute([*args, *(str(path) for path in objects), '-o', str(image)], timeout=300,
                diagnostic_log=output / (name + '-dependency-control.log'))
        defined, external, sections = macho_symbols(image, expected_type=filetype)
        if defined != {PREFIX + root for root in roots}:
            raise ValueError('The dependency-control exports differ from the exact RM roots.')
        records[name] = {'roots': list(roots), 'external_count': len(external),
                         'external': sorted(external), 'image_bytes': image.stat().st_size,
                         'sections': sections, 'image_executed': False,
                         'mach_o_filetype': filetype,
                         'image_type': 'MH_BUNDLE' if cross_probe else 'MH_KEXT_BUNDLE',
                         'link_profile': 'explicit-pic-cross-probe' if cross_probe else 'native-kernel-non-pic',
                         'root_scope': 'selected-original-global-adapter-isr-subset; not-complete-coordinator-closure',
                         'production_candidate_allowed': False}
        if not cross_probe:
            records[name]['dynamic_libraries_linked'] = False
    (output / 'dependency-controls.json').write_text(json.dumps(records, indent=2, sort_keys=True) + '\n')
    return records


def compile_original(upstream: Path, output: Path, compiler: Path,
                     *, cross_probe: bool = False, namespace: Path | None = None,
                     linker: Path | None = None, summary_path: Path | None = None,
                     checked_source: Path | None = None) -> dict:
    if not cross_probe and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
        raise ValueError('Authoritative original RM compilation requires Intel macOS.')
    upstream = _pinned_upstream(upstream)
    checked = None
    if checked_source is not None:
        if output.exists() or namespace is None:
            raise ValueError('Checked compilation requires fresh output and the verified baseline namespace.')
        checked = validate_checked_source(upstream, checked_source)
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    if namespace is not None:
        namespace = namespace.resolve(strict=True)
    source_base = checked_source.resolve(strict=True) if checked_source is not None else upstream
    source_root = source_base / 'src/nvidia'
    commands = original_commands(upstream, output, compiler)
    # Identification text is fixed and intentionally excludes local identity/time.
    (output / 'g_nvid_string.c').write_text(
        'const char NVRM_ID[] = "nvidia id: NVIDIA UNIX Open Kernel Module for x86_64 '
        '615.78.08 Release Build (build@ci)";\nconst char *const pNVRM_ID = NVRM_ID + 11;\n')
    def one(entry: tuple[int, list[str]]) -> dict:
        index, args = entry
        source = args[args.index('-c') + 1]
        args += ['-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
                 '-DNV_VERSION_STRING="' + RELEASE + '"', '-Wframe-larger-than=4096',
                 '-Werror=frame-larger-than']
        if namespace is not None:
            args += ['-include', str(namespace)]
        if cross_probe:
            # Zig cross-target implementation requires PIC. Native Apple kernel
            # compilation uses the original non-PIC flags and -mkernel instead.
            args += ['-target', 'x86_64-macos-none', '-fPIC']
        else:
            args += ['-mkernel', '-arch', 'x86_64', '-mmacosx-version-min=15.0']
        result = subprocess.run(args, cwd=source_root, text=True, capture_output=True, timeout=180)
        (output / ('compile-%04d.log' % index)).write_text(result.stdout + result.stderr)
        return {'source': source, 'status': result.returncode,
                'object': args[args.index('-o') + 1], 'diagnostics': result.stderr}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, enumerate(commands)))
    failures = [item for item in results if item['status']]
    (output / 'compile-results.json').write_text(json.dumps(results, indent=2) + '\n')
    if failures:
        raise ValueError('Original RM Darwin compilation failed: ' +
                         json.dumps(failures, sort_keys=True)[:12000])
    objects = [Path(item['object']) for item in results]
    if len(objects) != len(set(objects)):
        raise ValueError('Original RM object paths collide.')
    contract = (audit_namespace(objects, namespace) if namespace is not None else
                namespace_contract(objects, output / 'contract'))
    record = {'format': 1, 'status': 'compiled', 'architecture': 'x86_64',
              'object_format': 'Mach-O', 'commit': COMMIT, 'source_units': 1099,
              'generated_identification_units': 1, 'native_apple_compiler': not cross_probe,
              'cross_compile_probe': cross_probe, 'namespace_applied': namespace is not None,
              'namespace_contract': contract, 'global_rm_executed': False,
              'adapter_initialized': False, 'firmware_loaded': False,
              'compiler_version': execute([str(compiler), '--version']).stdout.splitlines()[0],
              'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in objects},
              'source_sha256': {
                  (str((source_root / item['source']).resolve().relative_to(source_base))
                   if not Path(item['source']).is_absolute() else 'generated/g_nvid_string.c'):
                  hashlib.sha256((source_root / item['source']).read_bytes()).hexdigest()
                  for item in results},
              'warnings': [item for item in results if item['diagnostics']]}
    def save_record() -> None:
        text = json.dumps(record, indent=2, sort_keys=True) + '\n'
        (output / 'darwin-compile.json').write_text(text)
        if summary_path is not None:
            summary_path.write_text(text)

    if checked is not None:
        # Verify again after compilation, including headers and untouched files.
        validate_checked_source(upstream, source_base)
        record.update(source_profile=CHECKED_PROFILE, source_semantics_unchanged=False,
                      production_candidate_allowed=False, kernel_execution='not_tested', gpu_access=False,
                      checked_source={'directory': source_base.name, 'manifest': CHECKED_MANIFEST,
                                      'manifest_sha256': checked['manifest_sha256'],
                                      'tree_sha256': checked['tree_sha256'], 'file_count': checked['file_count'],
                                      'patch_count': len(checked['patches']),
                                      'checked_memory_header': checked['checked_memory_header']},
                      all_original_units_use_checked_source=True)

    needs_link = namespace is not None and (linker is not None or not cross_probe)
    record['dependency_controls_status'] = 'pending' if needs_link else 'not_requested'
    # Successful compilation and namespace evidence must survive a later link
    # failure. These records do not authorize reuse until the caller has also
    # completed the source-namespace and dependency-control checks.
    save_record()
    if needs_link:
        try:
            record['dependency_controls'] = link_dependency_controls(objects, output,
                [str(linker)] if linker is not None else ['/usr/bin/xcrun', 'ld'],
                cross_probe=cross_probe)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            record['dependency_controls_status'] = 'failed'
            save_record()
            raise
        record['dependency_controls_status'] = 'passed'
        save_record()
    return record


def _compilation_inputs(compiled: dict, source: Path, objects_directory: Path,
                        namespace: Path) -> list[Path]:
    objects = sorted(objects_directory.glob('*.o'))
    if (len(objects) != 1100 or any(path.is_symlink() for path in objects)
            or {path.name: _sha(path.read_bytes()) for path in objects} != compiled['object_sha256']):
        raise ValueError('The complete compiled RM object bytes changed.')
    if audit_namespace(objects, namespace) != compiled['namespace_contract']:
        raise ValueError('The compiled RM private namespace changed.')
    hashes = compiled['source_sha256']
    if len(hashes) != 1100 or 'generated/g_nvid_string.c' not in hashes:
        raise ValueError('The compiled source inventory is incomplete.')
    for name, expected in hashes.items():
        path = (objects_directory / 'g_nvid_string.c' if name == 'generated/g_nvid_string.c'
                else source / name)
        if (Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink()
                or _sha(path.read_bytes()) != expected):
            raise ValueError('A compiled source hash changed: ' + name)
    return objects


def compile_checked_overlays(upstream: Path, compilation_root: Path, compiler: Path,
                             *, cross_probe: bool = False, linker: Path | None = None) -> dict:
    """Explicitly compile reviewed semantic changes after preserving the baseline."""
    upstream = _pinned_upstream(upstream)
    root = compilation_root.resolve(strict=True)
    target = root / 'checked-namespaced'
    summary = root / 'checked-darwin-compile.json'
    if target.exists() or summary.exists():
        raise ValueError('Checked overlay compilation requires fresh checked output.')
    baseline_path = root / 'darwin-compile.json'
    baseline = json.loads(baseline_path.read_bytes())
    expected = json.loads((PACKAGE / 'upstream/adapted/SOURCE-CONTRACT.json').read_bytes())
    namespace = root / 'original/contract/S540GlobalRmNamespace.h'
    if (baseline.get('status') != 'compiled' or baseline.get('source_namespace_verified') is not True
            or baseline.get('namespace_applied') is not True or baseline.get('commit') != COMMIT
            or baseline.get('dependency_controls_status') != 'passed'
            or baseline.get('cross_compile_probe') is not cross_probe
            or baseline.get('native_apple_compiler') is not (not cross_probe)
            or baseline.get('source_namespace_contract') != expected
            or _sha(namespace.read_bytes()) != expected['namespace_sha256']):
        raise ValueError('The checked profile requires the verified pinned baseline compilation.')
    _compilation_inputs(baseline, upstream, root / 'namespaced', namespace)
    source = root / 'checked-source'
    prepare_checked_source(upstream, source)
    record = compile_original(upstream, target, compiler, cross_probe=cross_probe,
                              namespace=namespace, linker=linker, summary_path=summary,
                              checked_source=source)
    if (record['namespace_contract']['defined'] != baseline['namespace_contract']['defined']
            or record['dependency_controls_status'] != 'passed'):
        raise ValueError('Checked compilation changed original definitions or lacks completed link controls.')
    record.update(source_namespace_verified=True, source_namespace_contract=expected,
                  generated_namespace_header='original/contract/S540GlobalRmNamespace.h',
                  baseline_compile_sha256=_sha(baseline_path.read_bytes()),
                  namespace_header_origin='unchanged-baseline-symbol-aliases; source-semantics-are-adapted')
    raw = json.dumps(record, indent=2, sort_keys=True) + '\n'
    summary.write_text(raw)
    (target / 'darwin-compile.json').write_text(raw)
    return record


def load_checked_compilation(upstream: Path, compilation_root: Path,
                             *, require_native: bool = True) -> tuple[dict, Path, Path, list[Path]]:
    """Revalidate adapted source/header, objects and selected roots before reuse."""
    upstream = _pinned_upstream(upstream)
    root = compilation_root.resolve(strict=True)
    compiled = json.loads((root / 'checked-darwin-compile.json').read_bytes())
    if (compiled.get('status') != 'compiled' or compiled.get('source_profile') != CHECKED_PROFILE
            or compiled.get('source_semantics_unchanged') is not False
            or compiled.get('source_namespace_verified') is not True
            or compiled.get('namespace_applied') is not True
            or compiled.get('production_candidate_allowed') is not False
            or compiled.get('commit') != COMMIT or compiled.get('dependency_controls_status') != 'passed'
            or compiled.get('all_original_units_use_checked_source') is not True
            or type(compiled.get('native_apple_compiler')) is not bool
            or type(compiled.get('cross_compile_probe')) is not bool
            or compiled['native_apple_compiler'] is compiled['cross_compile_probe']
            or (require_native and (compiled.get('native_apple_compiler') is not True
                                    or compiled.get('cross_compile_probe') is not False))):
        raise ValueError('The checked compilation profile is incomplete or unauthorized.')
    expected = json.loads((PACKAGE / 'upstream/adapted/SOURCE-CONTRACT.json').read_bytes())
    if (compiled['source_namespace_contract'] != expected
            or compiled['generated_namespace_header'] != 'original/contract/S540GlobalRmNamespace.h'
            or compiled['checked_source']['directory'] != 'checked-source'
            or compiled['checked_source']['manifest'] != CHECKED_MANIFEST
            or compiled['baseline_compile_sha256'] != _sha((root / 'darwin-compile.json').read_bytes())):
        raise ValueError('The checked compilation baseline/profile identity changed.')
    source, namespace = root / 'checked-source', root / 'original/contract/S540GlobalRmNamespace.h'
    checked = validate_checked_source(upstream, source)
    identity = {'directory': source.name, 'manifest': CHECKED_MANIFEST,
                'manifest_sha256': checked['manifest_sha256'], 'tree_sha256': checked['tree_sha256'],
                'file_count': checked['file_count'], 'patch_count': len(checked['patches']),
                'checked_memory_header': checked['checked_memory_header']}
    if (compiled['checked_source'] != identity
            or _sha(namespace.read_bytes()) != expected['namespace_sha256']):
        raise ValueError('The checked compilation source/header/namespace provenance changed.')
    objects = _compilation_inputs(compiled, source, root / 'checked-namespaced', namespace)
    for name, roots in (('global', GLOBAL_ROOTS), ('adapter', ADAPTER_ROOTS)):
        control = compiled['dependency_controls'][name]
        filetype = MH_BUNDLE if compiled['cross_compile_probe'] else MH_KEXT_BUNDLE
        defined, external, _ = macho_symbols(root / 'checked-namespaced' /
                                             (name + '-dependency-control.bundle'), expected_type=filetype)
        if (control['roots'] != list(roots) or defined != {PREFIX + symbol for symbol in roots}
                or sorted(external) != control['external'] or control['image_executed'] is not False
                or control['production_candidate_allowed'] is not False):
            raise ValueError('A checked dependency control changed.')
    return compiled, source, namespace, objects


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--cross-compile-probe', action='store_true')
    parser.add_argument('--namespace', type=Path)
    parser.add_argument('--generate-namespace', action='store_true',
                        help='Generate and verify the private namespace before compiling it.')
    parser.add_argument('--checked-cleanup-overlays', action='store_true',
                        help='After the unchanged baseline, compile the approved checked development-only overlays separately.')
    parser.add_argument('--linker', type=Path,
                        help='Optional cross-probe Mach-O linker; native uses Apple ld.')
    args = parser.parse_args()
    if args.generate_namespace and args.namespace:
        parser.error('--generate-namespace and --namespace are mutually exclusive')
    if args.checked_cleanup_overlays and not args.generate_namespace:
        parser.error('--checked-cleanup-overlays requires --generate-namespace')
    if args.checked_cleanup_overlays and args.cross_compile_probe and args.linker is None:
        parser.error('Checked cross-probe compilation requires an explicit Mach-O linker')
    if args.generate_namespace:
        record = compile_with_namespace(args.upstream, args.output_dir, args.compiler,
                                        cross_probe=args.cross_compile_probe, linker=args.linker)
        if args.checked_cleanup_overlays:
            record = compile_checked_overlays(args.upstream, args.output_dir, args.compiler,
                                              cross_probe=args.cross_compile_probe, linker=args.linker)
    else:
        record = compile_original(args.upstream, args.output_dir, args.compiler,
                                  cross_probe=args.cross_compile_probe, namespace=args.namespace,
                                  linker=args.linker)
    print(json.dumps({key: record[key] for key in ('status', 'source_units',
        'native_apple_compiler', 'cross_compile_probe', 'namespace_applied')}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
