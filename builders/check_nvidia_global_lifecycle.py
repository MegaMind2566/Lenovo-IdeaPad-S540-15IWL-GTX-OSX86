#!/usr/bin/env python3
"""Execute the checked original global RM in explicit native user-space controls.

Every original translation unit is rebuilt for each instrumentation variant.
Only the privileged CR4 unit is replaced by a declared exact-ABI CPU fixture.
Unavailable external functions use exact typed refusals or aborting tripwires;
none is a successful service. This does not authorize kernel or GPU execution.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import re
import sys

import check_nvidia_global_crypto as crypto
import compile_nvidia_global_rm as original
import nvidia_execution_commands as commands

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/nvidia-global-rm'
SERVICES = ROOT / 'packages/nvidia-darwin-services'
CRYPTO = ROOT / 'packages/nvidia-global-rm-crypto'
DEVICE = ROOT / 'packages/nvidia-device-transport'
CPU_SOURCE = 'arch/nvalloc/unix/src/asm/x86/nv_rdcr.c'
CPU_FIXTURE = PACKAGE / 'tests/fixtures/nv_rdcr_fixture.c'
SERVICE_NAMES = ('Platform', 'Sync', 'Work', 'Timer', 'Process', 'Runtime', 'Check', 'UserCopy')
KERNEL_FLAGS = {'-msoft-float', '-mno-red-zone', '-mcmodel=kernel', '-mno-mmx',
                '-mno-sse', '-mno-sse2', '-mno-3dnow', '-fno-pic'}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expect(record: dict, expected: dict, description: str) -> None:
    mismatch = {key: {'expected': value, 'observed': record.get(key)}
                for key, value in expected.items()
                if type(record.get(key)) is not type(value) or record[key] != value}
    if mismatch:
        raise ValueError(description + ': ' + json.dumps(mismatch, sort_keys=True))


def _symbols(path: Path, host_control: bool) -> tuple[set[str], set[str]]:
    # Sanitized user-space objects legitimately contain compiler runtime
    # initializers. The kernel audit's macho_symbols deliberately refuses such
    # sections, so use nm here after the separate exact object-format check.
    result = commands.run('nm', '-g', str(path)).stdout
    defined, undefined = set(), set()
    for line in result.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        kind, name = fields[-2:]
        if not host_control:
            if not name.startswith('_'):
                raise ValueError('Unexpected Darwin native C/C++ external spelling: ' + name)
            name = name[1:]
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('Unexpected native control symbol: ' + name)
        if kind == 'U':
            undefined.add(name)
        elif kind.upper() not in ('W', 'V') or len(fields) == 3:
            defined.add(name)
    return defined, undefined


def _private_boundaries(output: Path, implemented: set[str]) -> dict:
    """Use retained source-reviewed prototypes; abort any unavailable scalar call."""
    contracts = json.loads((PACKAGE / 'EXTERNAL-CONTRACTS.json').read_text())
    if contracts['commit'] != original.COMMIT or len(contracts['contracts']) != 244:
        raise ValueError('The reviewed external ABI inventory changed.')
    spec = importlib.util.spec_from_file_location('global_refusals', PACKAGE / 'generate_refusals.py')
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    known = {row['symbol'] for row in contracts['contracts']}
    provided = {name.removeprefix(original.PREFIX) for name in implemented
                if name.startswith(original.PREFIX) and name.removeprefix(original.PREFIX) in known}
    source, manifest = module.generate(provided)
    # These are private process-terminating metadata boundaries, not production
    # bindings. Exact prototypes are compiled against the actual pinned headers.
    source += '\n#ifdef KERNEL\n#error "Native abort boundaries are forbidden in kernel builds"\n#endif\n'
    source += 'extern void abort(void) __attribute__((noreturn));\n'
    rows = {row['symbol']: row for row in contracts['contracts']}
    for name in manifest['blocked_scalar_or_void']:
        row = rows[name]
        parameters = row['parameters']
        args = ', '.join(module.parameter(item['type'], item['name']) for item in parameters) or 'void'
        source += '\n' + row['return_type'] + ' ' + name + '(' + args + ')\n{\n'
        source += ''.join('    (void)' + item['name'] + ';\n' for item in parameters)
        source += '    s540GlobalRmRecordUnavailable(511);\n    abort();\n}\n'
    if manifest['blocked_data']:
        # Data cannot be represented by a fail-on-call boundary. Every original
        # external variable must be supplied by the actual OS mechanism facade.
        raise ValueError('Native controls lack real global data bindings: ' +
                         ', '.join(manifest['blocked_data']))
    path = output / 'native-unavailable-boundaries.c'
    path.write_text(source)
    record = {**manifest, 'production_binding': False, 'entry_allowed': False,
              'native_control_only': True,
              'scalar_or_void_policy': 'process abort; no scalar fallback or successful no-op',
              'generated_source_sha256': _digest(path)}
    (output / 'native-boundaries.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def _user_flags(flags: list[str], target: list[str], host_control: bool) -> list[str]:
    # Preserve actual upstream ABI/profile defines and include order. Remove
    # kernel code-generation policy only for this separately labelled control.
    result = [flag for flag in flags if flag not in KERNEL_FLAGS and
              not flag.startswith(('-mindirect-branch', '-mfunction-return'))]
    result += [*target, '-O1', '-g', '-fPIC', '-ffunction-sections', '-fdata-sections']
    if host_control:
        result += ['-U__linux__', '-U__linux']
    return result


def _compile_original(output: Path, upstream: Path, checked: Path, namespace: Path,
                      cc: list[str], instrumentation: list[str], *, host_control: bool) -> tuple[list[Path], dict]:
    target = [] if host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0']
    compiler = Path(cc[0]) if host_control else Path('/usr/bin/clang')
    entries = original.original_commands(upstream, output, compiler)
    identification = output / 'g_nvid_string.c'
    identification.write_text('const char NVRM_ID[] = "nvidia id: NVIDIA UNIX Open Kernel Module '
                              'for x86_64 615.78.08 Native User-Space Control";\n'
                              'const char *const pNVRM_ID = NVRM_ID + 11;\n')
    source_root = checked / 'src/nvidia'
    def one(item):
        index, entry = item
        name = entry[entry.index('-c') + 1]
        source = identification if Path(name).is_absolute() else source_root / name
        fixture = name == CPU_SOURCE
        if fixture:
            source = CPU_FIXTURE
        flags = _user_flags(entry[1:entry.index('-c')], target, host_control)
        obj = output / ('original-%04d.o' % index)
        args = [*cc, *flags, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
                '-DNV_VERSION_STRING="' + original.RELEASE + '"', '-include', str(namespace),
                *instrumentation, '-c', str(source), '-o', str(obj)]
        # Make-declared relative include paths resolve against the isolated
        # checked tree; no original source or production flag is modified.
        commands.run(*args, cwd=source_root, timeout=300,
                     diagnostic_log=output / ('original-%04d.log' % index))
        crypto.verify_binary(obj, 1, host_control)
        return {'source': name, 'compiled_source': str(source), 'object': str(obj),
                'privileged_cpu_fixture': fixture, 'source_sha256': _digest(source),
                'object_sha256': _digest(obj), 'instrumented': bool(instrumentation)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(one, enumerate(entries)))
    if len(records) != 1100 or sum(row['privileged_cpu_fixture'] for row in records) != 1:
        raise ValueError('The full original source inventory or exact CPU fixture substitution changed.')
    original.validate_checked_source(upstream, checked)
    (output / 'original-compile-results.json').write_text(json.dumps(records, indent=2, sort_keys=True) + '\n')
    return [Path(row['object']) for row in records], {
        'source_units': 1099, 'actual_original_source_units': 1098,
        'generated_identification_units': 1, 'make_declared_translation_units': 1100,
        'all_original_units_instrumented': bool(instrumentation),
        'privileged_cpu_fixture_units': 1, 'original_cpu_source_executed': False,
        'source_profile': original.CHECKED_PROFILE,
        'compile_results_sha256': _digest(output / 'original-compile-results.json'),
        'compiler_version': commands.run(*cc, '--version').stdout.splitlines()[0],
        'instrumentation_flags': instrumentation}


def _cast_controls(work: Path, cc: list[str], cxx: list[str], bridge: list[str],
                   c_common: list[str], instrumentation: list[str], checked: Path, *, host_control: bool) -> dict:
    header = checked / 'src/nvidia/inc/libraries/nvoc/prelude.h'
    lines = header.read_text().splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines) if line.startswith('#define staticCast('))
    end = start
    while lines[end].rstrip().endswith(chr(92)):
        end += 1
    macro = work / 'exact-checked-nvoc-cast.h'
    macro.write_text(''.join(lines[start:end + 1]))
    records = {}
    for language, compiler in (('c', cc), ('cxx', cxx)):
        source = PACKAGE / ('tests/check_nvoc_cast_native.c' if language == 'c' else
                            'tests/check_nvoc_cast_cpp_native.cpp')
        flags = bridge
        if language == 'cxx':
            flags = [flag for flag in bridge if flag not in (
                '--std=gnu11', '-Wstrict-prototypes', '-Wold-style-definition', '-D_LANGUAGE_C')]
            flags += ['-std=c++17', '-include', str(macro)]
        binary = work / ('nvoc-cast-' + language)
        commands.run(*compiler, *flags, *c_common, *instrumentation,
                     str(source), '-o', str(binary),
                     diagnostic_log=work / ('nvoc-cast-' + language + '-compile.log'))
        crypto.verify_binary(binary, 2, host_control)
        record = json.loads(commands.run(str(binary),
                            diagnostic_log=work / ('nvoc-cast-' + language + '-run.log')).stdout)
        _expect(record, {'format': 1, 'component': 'nvidia-nvoc-cast-native',
                        'status': 'passed', 'checks': 12, 'failures': 0,
                        'null_and_inheritance': True, 'single_evaluation': True,
                        'qualified_source': True, 'gpu_access': False,
                        'kernel_executed': False}, 'actual-nvoc-cast/' + language)
        records[language] = {**record, 'actual_nvoc_generated_headers': language == 'c',
                             'reduced_cpp_layout_fixture': language == 'cxx',
                             'checked_header_sha256': _digest(header),
                             'exact_macro_sha256': _digest(macro)}
    return records


def _iterator_controls(work: Path, cc: list[str], bridge: list[str], c_common: list[str],
                       instrumentation: list[str], *, host_control: bool) -> dict:
    source = PACKAGE / 'tests/check_iterator_dispatch_native.c'
    binary = work / 'iterator-dispatch'
    commands.run(*cc, *bridge, *c_common, *instrumentation, str(source), '-o', str(binary),
                 diagnostic_log=work / 'iterator-dispatch-compile.log')
    crypto.verify_binary(binary, 2, host_control)
    record = json.loads(commands.run(str(binary),
                        diagnostic_log=work / 'iterator-dispatch-run.log').stdout)
    _expect(record, {'format': 1, 'component': 'nvidia-iterator-dispatch-native',
                    'status': 'passed', 'checks': 13, 'failures': 0,
                    'actual_container_headers': True, 'typed_callback_fixture': True,
                    'pointer_and_index_ranges': True, 'single_container_evaluation': True,
                    'gpu_access': False, 'kernel_executed': False}, 'typed-iterator-dispatch')
    return {**record, 'harness_sha256': _digest(source)}


@commands.logged(report='global-lifecycle-checks.json')
def check(output: Path, upstream: Path, namespace: Path, *, host_control: bool = False) -> dict:
    if not host_control and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
        raise ValueError('Authoritative original lifecycle controls require Intel macOS.')
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    upstream = original._pinned_upstream(upstream)
    namespace = namespace.resolve(strict=True)
    expected_namespace = json.loads((PACKAGE / 'upstream/adapted/SOURCE-CONTRACT.json').read_text())
    if _digest(namespace) != expected_namespace['namespace_sha256']:
        raise ValueError('Native lifecycle requires the actual verified original private namespace.')
    checked = output / 'checked-source'
    source_record = original.prepare_checked_source(upstream, checked)
    cc, cxx = crypto.compiler_pair(host_control)
    compiler = Path(cc[0]) if host_control else Path('/usr/bin/clang')
    target = [] if host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0']
    bridge = _user_flags(original.original_bridge_flags(upstream, output, compiler, namespace,
                                                        checked_source=checked), target, host_control)
    c_common = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                '-I', str(ROOT / 'packages/nvidia-os-adapter/upstream/include')]
    cpp_common = [*target, '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-std=c++17', '-pthread',
                  '-ffunction-sections', '-fdata-sections',
                  '-I', str(ROOT / 'packages/nvidia-os-adapter/upstream/include')]
    progress = commands.ComponentProgress(output / 'global-lifecycle-checks.json', {
        'component': 'nvidia-original-global-lifecycle', 'host_system': platform.system(),
        'authoritative_darwin_execution': not host_control, 'source_profile': original.CHECKED_PROFILE,
        'checked_source': source_record, 'production_candidate_allowed': False,
        'kernel_runtime': 'not_tested', 'gpu_access': False,
        'privileged_cpu_fixture': True, 'platform_facts_fixture': True})
    for label, instrumentation in (('native', []), ('sanitized', [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
            '-fno-omit-frame-pointer'])):
        work = output / label
        work.mkdir()
        progress.record['active_component'] = label + '-original-compile'
        progress.save()
        objects, compilation = _compile_original(work, upstream, checked, namespace, cc,
                                                 instrumentation, host_control=host_control)
        project = []
        header_directories = (PACKAGE / 'src', SERVICES / 'src', CRYPTO / 'src', DEVICE / 'src',
                              ROOT / 'packages/nvidia-os-adapter/upstream/include')
        project_header_hashes = {path.relative_to(ROOT).as_posix(): _digest(path)
            for directory in header_directories for path in sorted(directory.rglob('*'))
            if path.is_file() and path.suffix in ('.h', '.hpp')}
        receipt_header = DEVICE / 'tests/dma_stop_receipt_fixture.h'
        project_header_hashes[receipt_header.relative_to(ROOT).as_posix()] = _digest(receipt_header)
        project_source_hashes = {}
        for source in (*sorted((PACKAGE / 'src').glob('*.c')),
                       DEVICE / 'src/S540NvidiaUnsupportedMemory.c'):
            project_source_hashes[source.relative_to(ROOT).as_posix()] = _digest(source)
            obj = work / (source.stem + '.o')
            commands.run(*cc, *bridge, *c_common, *instrumentation, '-c', str(source), '-o', str(obj),
                         diagnostic_log=work / (source.stem + '-compile.log'))
            project.append(obj)
        for source in (PACKAGE / 'src/S540NvidiaGlobalRmHost.cpp',
                       PACKAGE / 'src/S540NvidiaGlobalRmFormat.cpp',
                       PACKAGE / 'src/S540NvidiaGlobalRmSystemBackend.cpp',
                       PACKAGE / 'src/S540NvidiaGlobalRmFirmwareTablesBackend.cpp',
                       DEVICE / 'src/S540NvidiaDeviceServices.cpp',
                       DEVICE / 'src/S540NvidiaDeviceTransport.cpp',
                       DEVICE / 'tests/dma_stop_receipt_fixture.cpp',
                       *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES)):
            project_source_hashes[source.relative_to(ROOT).as_posix()] = _digest(source)
            obj = work / (source.stem + '.o')
            commands.run(*cxx, *cpp_common, *instrumentation, '-c', str(source), '-o', str(obj),
                         diagnostic_log=work / (source.stem + '-compile.log'))
            project.append(obj)
        crypto_source = CRYPTO / 'src/S540NvidiaGlobalCrypto.c'
        project_source_hashes[crypto_source.relative_to(ROOT).as_posix()] = _digest(crypto_source)
        obj = work / 'S540NvidiaGlobalCrypto.o'
        commands.run(*cc, *target, *c_common, '-std=c11', *instrumentation,
                     '-c', str(CRYPTO / 'src/S540NvidiaGlobalCrypto.c'), '-o', str(obj),
                     diagnostic_log=work / 'crypto-compile.log')
        project.append(obj)
        if any(_digest(ROOT / path) != digest for path, digest in
               {**project_source_hashes, **project_header_hashes}.items()):
            raise ValueError('A lifecycle project source changed during its compilation.')
        compilation['project_source_sha256'] = project_source_hashes
        compilation['project_header_sha256'] = project_header_hashes
        compilation['project_object_sha256'] = {path.name: _digest(path) for path in project}
        compilation['dma_stop_receipt_fixture'] = {
            'source': (DEVICE / 'tests/dma_stop_receipt_fixture.cpp').relative_to(ROOT).as_posix(),
            'native_control_only': True, 'production_binding': False,
            'scope': 'No device Session or DMA epoch is started by these global controls; no receipt is issued.',
            'production_context_verifier_executed': False}
        defined = set().union(*(_symbols(path, host_control)[0] for path in project))
        boundaries = _private_boundaries(work, defined)
        obj = work / 'native-unavailable-boundaries.o'
        commands.run(*cc, *bridge, *c_common, *instrumentation, '-I', str(PACKAGE / 'src'),
                     '-c', str(work / 'native-unavailable-boundaries.c'), '-o', str(obj),
                     diagnostic_log=work / 'native-boundaries-compile.log')
        project.append(obj)
        fixture = PACKAGE / 'tests/fixtures/nvswitch_assert_fixture.c'
        obj = work / 'nvswitch_assert_fixture.o'
        commands.run(*cc, *bridge, *c_common, *instrumentation, '-I', str(PACKAGE / 'src'),
                     '-c', str(fixture), '-o', str(obj),
                     diagnostic_log=work / 'nvswitch-assert-fixture-compile.log')
        project.append(obj)
        boundaries['nvswitch_assertion_tripwire'] = {
            'source': fixture.relative_to(ROOT).as_posix(), 'sha256': _digest(fixture),
            'prototype_from': 'src/common/nvswitch/interface/export_nvswitch.h',
            'header_sha256': _digest(upstream / 'src/common/nvswitch/interface/export_nvswitch.h'),
            'policy': 'exact-ABI process abort; no hardware service'}
        objects += project
        results = {'compilation': compilation, 'boundaries': boundaries,
                   'nvoc_cast': _cast_controls(work, cc, cxx, bridge, c_common, instrumentation,
                                               checked, host_control=host_control),
                   'iterator_dispatch': _iterator_controls(work, cc, bridge, c_common,
                                                           instrumentation, host_control=host_control)}
        progress.record['native_execution'][label] = results
        progress.save()
        for component, harness, expected in (
                ('lifecycle', 'check_global_rm_native.cpp', {
                    'component': 'nvidia-global-rm-native', 'checks': 22,
                    'full_rm_initialized': True, 'original_system_children': 15,
                    'original_memory_export_client': True, 'unavailable_calls': 0,
                    'crypto_calls': 0, 'cleanup': True}),
                ('memory_retry', 'check_memory_init_native.cpp', {
                    'component': 'nvidia-memory-init-native', 'checks': 29,
                    'same_process_full_rm_retry': True, 'original_system_children': 15,
                    'raw_lock_failure': True, 'backing_lock_failure': True, 'cleanup': True}),
                ('global_domains', 'check_global_domains_native.cpp', {
                    'component': 'nvidia-global-domains', 'checks': 23,
                    'real_original_global_lifecycle': True, 'external_storage_preserved': True,
                    'external_allocations': 2, 'privileged_cpu_fixture': True,
                    'kernel_execution': 'not_tested', 'cleanup': True}),
                ('registry_epoch', 'check_registry_epoch_native.c', {
                    'component': 'nvidia-registry-epoch', 'checks': 23,
                    'real_original_registry': True, 'foreign_epoch_preserved': True,
                    'global_constructor_executed': False, 'kernel_execution': 'not_tested',
                    'cleanup': True}),
                ('allocation_faults', 'check_global_rm_fault_native.cpp', {})):
            progress.record['active_component'] = label + '/' + component
            progress.save()
            binary = work / component
            harness_source = PACKAGE / 'tests' / harness
            harness_input = harness_source
            if harness_source.suffix == '.c':
                harness_input = work / (component + '-harness.o')
                commands.run(*cc, *bridge, *c_common, *instrumentation, '-c', str(harness_source),
                             '-o', str(harness_input),
                             diagnostic_log=work / (component + '-harness-compile.log'))
            commands.run(*cxx, *cpp_common, *instrumentation, str(harness_input),
                         *(str(path) for path in objects),
                         '-Wl,--gc-sections' if host_control else '-Wl,-dead_strip',
                         '-o', str(binary), timeout=300, diagnostic_log=work / (component + '-link.log'))
            crypto.verify_binary(binary, 2, host_control)
            if component != 'allocation_faults':
                record = json.loads(commands.run(str(binary), diagnostic_log=work / (component + '-run.log')).stdout)
                fixture_fields = {} if component in ('registry_epoch', 'global_domains') else {
                    'privileged_cpu_fixture': True, 'kernel_executed': False}
                _expect(record, {'format': 1, 'status': 'passed', 'failures': 0,
                                'execution': 'native-user-space', 'gpu_access': False,
                                'platform_facts_fixture': True, **fixture_fields,
                                **expected}, label + '/' + component)
                results[component] = {**record, 'harness_sha256': _digest(harness_source)}
            else:
                count = results['lifecycle']['host_allocations']
                if type(count) is not int or count <= 0 or count > 8192:
                    raise ValueError('The observed original lifecycle allocation inventory is invalid.')
                faults = []
                for ordinal in range(1, count + 1):
                    record = json.loads(commands.run(str(binary), str(ordinal),
                        diagnostic_log=work / ('fault-%04d.log' % ordinal)).stdout)
                    _expect(record, {'format': 1, 'component': 'nvidia-global-rm-fault',
                                    'status': 'passed', 'ordinal': ordinal, 'allocation_failures': 1,
                                    'live_allocations': 0, 'live_bytes': 0, 'invalid_frees': 0,
                                    'unavailable_calls': 0, 'host_released': True,
                                    'privileged_cpu_fixture': True, 'platform_facts_fixture': True,
                                    'kernel_executed': False, 'gpu_access': False},
                            label + '/fault-' + str(ordinal))
                    faults.append(record)
                    # Keep completed fault ordinals if a later process refuses.
                    (work / 'allocation-fault-progress.json').write_text(json.dumps({
                        'format': 1, 'status': 'running', 'expected_cases': count,
                        'passed': len(faults), 'cases_original_status': faults},
                        indent=2, sort_keys=True) + '\n')
                results[component] = {'status': 'passed', 'cases': count, 'passed': len(faults),
                    'all_observed_allocation_ordinals': True, 'cases_original_status': faults,
                    'kernel_executed': False, 'gpu_access': False}
        progress.record['native_execution'][label] = results
        progress.save()
    progress.record.update(status='passed', active_component=None)
    progress.save()
    return progress.record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--namespace', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--host-control', action='store_true')
    args = parser.parse_args()
    record = check(args.output_dir, args.upstream, args.namespace, host_control=args.host_control)
    print(json.dumps({'status': record['status'], 'native_execution': list(record['native_execution']),
                      'production_candidate_allowed': False, 'gpu_access': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
