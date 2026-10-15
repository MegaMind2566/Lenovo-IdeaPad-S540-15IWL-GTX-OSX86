#!/usr/bin/env python3
"""Compile the complete pinned original RM under an explicit Darwin profile.

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
                 'rm_disable_adapter', 'rm_isr', 'rm_isr_bh')


def execute(args: list[str], *, cwd: Path | None = None,
            timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                          check=True, timeout=timeout)


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
                          namespace: Path) -> list[str]:
    """Give original-header bridge TUs the same actual C ABI/profile as RM."""
    command = original_commands(upstream, output, compiler)[0]
    flags = command[1:command.index('-c')]
    source_root = upstream / 'src/nvidia'
    normalized, index = [], 0
    while index < len(flags):
        flag = flags[index]
        normalized.append(flag)
        if flag in ('-I', '-include'):
            index += 1
            normalized.append(str((source_root / flags[index]).resolve(strict=True)))
        index += 1
    return [*normalized, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
            '-DNV_VERSION_STRING="' + RELEASE + '"', '-include', str(namespace.resolve(strict=True))]


def macho_symbols(path: Path, *, expected_type: int = 1) -> tuple[set[str], set[str], list[str]]:
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
    if '__mod_init_func' in sections or '__mod_term_func' in sections:
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
                              cross_probe=cross_probe, namespace=header, linker=linker)
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
                             linker: list[str]) -> dict:
    """Inspect real Mach-O root reachability; unresolved images are never loaded."""
    records = {}
    for name, roots in (('global', GLOBAL_ROOTS), ('adapter', ADAPTER_ROOTS)):
        image = output / (name + '-dependency-control.bundle')
        args = [*linker, '-arch', 'x86_64', '-platform_version', 'macos', '15.0', '15.0',
                '-bundle', '-undefined', 'dynamic_lookup', '-dead_strip', '-no_uuid']
        args += [value for root in roots for value in ('-exported_symbol', '_' + PREFIX + root)]
        execute([*args, *(str(path) for path in objects), '-o', str(image)], timeout=300)
        defined, external, sections = macho_symbols(image, expected_type=8)
        if defined != {PREFIX + root for root in roots}:
            raise ValueError('The dependency-control exports differ from the exact RM roots.')
        records[name] = {'roots': list(roots), 'external_count': len(external),
                         'external': sorted(external), 'image_bytes': image.stat().st_size,
                         'sections': sections, 'image_executed': False}
    (output / 'dependency-controls.json').write_text(json.dumps(records, indent=2, sort_keys=True) + '\n')
    return records


def compile_original(upstream: Path, output: Path, compiler: Path,
                     *, cross_probe: bool = False, namespace: Path | None = None,
                     linker: Path | None = None) -> dict:
    if not cross_probe and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
        raise ValueError('Authoritative original RM compilation requires Intel macOS.')
    upstream = upstream.resolve(strict=True)
    if execute(['git', '-C', str(upstream), 'rev-parse', 'HEAD']).stdout.strip() != COMMIT:
        raise ValueError('The original RM source revision differs from its pinned commit.')
    if execute(['git', '-C', str(upstream), 'status', '--porcelain']).stdout:
        raise ValueError('Original RM compilation requires an unchanged upstream checkout.')
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    if namespace is not None:
        namespace = namespace.resolve(strict=True)
    source_root = upstream / 'src/nvidia'
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
              'source_sha256': {
                  (str((source_root / item['source']).resolve().relative_to(upstream))
                   if not Path(item['source']).is_absolute() else 'generated/g_nvid_string.c'):
                  hashlib.sha256((source_root / item['source']).read_bytes()).hexdigest()
                  for item in results},
              'warnings': [item for item in results if item['diagnostics']]}
    if namespace is not None and (linker is not None or not cross_probe):
        record['dependency_controls'] = link_dependency_controls(objects, output,
            [str(linker)] if linker is not None else ['/usr/bin/xcrun', 'ld'])
    (output / 'darwin-compile.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--cross-compile-probe', action='store_true')
    parser.add_argument('--namespace', type=Path)
    parser.add_argument('--generate-namespace', action='store_true',
                        help='Generate and verify the private namespace before compiling it.')
    parser.add_argument('--linker', type=Path,
                        help='Optional cross-probe Mach-O linker; native uses Apple ld.')
    args = parser.parse_args()
    if args.generate_namespace and args.namespace:
        parser.error('--generate-namespace and --namespace are mutually exclusive')
    if args.generate_namespace:
        record = compile_with_namespace(args.upstream, args.output_dir, args.compiler,
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
