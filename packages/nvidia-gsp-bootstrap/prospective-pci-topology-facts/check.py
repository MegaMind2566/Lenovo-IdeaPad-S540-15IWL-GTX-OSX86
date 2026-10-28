#!/usr/bin/env python3
"""Run actual bounded PCI engine/facade/original CPU and public SDK controls."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text, name):
    start, end = prepare.function_span(text, name)
    return text[text.rfind('\n', 0, start) + 1:end] + '\n'


def facade_parts(text):
    names = ('stateValid', 's540PciTopologyRecordFailure', 's540PciTopologyUsesOsConfig',
        's540PciTopologyValidateForGsp', 'pciRead', 'pciWrite', 's540Global_os_pci_init_handle',
        's540Global_os_pci_read_byte', 's540Global_os_pci_read_word', 's540Global_os_pci_read_dword',
        's540Global_os_pci_write_byte', 's540Global_os_pci_write_word', 's540Global_os_pci_write_dword')
    return '\n'.join(function(text, name) for name in names)


def dependencies(path):
    return {str(Path(name).resolve(strict=True)): sha(Path(name).resolve(strict=True))
        for name in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1])}


def run(args):
    require(args.host_control, 'Explicit --host-control required for typed CPU resource endpoints')
    project = args.input_project.resolve(strict=True)
    source = args.input_source.resolve(strict=True)
    output = args.output.absolute()
    require(not output.exists() and not output.is_relative_to(project) and
            not project.is_relative_to(output), 'Fresh nonoverlapping PCI control output required')
    original_project = {name: (project / name).read_text() for name in prepare.INPUTS}
    original_source = {name: (source / name).read_text() for name in prepare.ORIGINAL_INPUTS}
    selected = prepare.transforms(original_project)
    selected_source = prepare.original_transforms(original_source)
    if args.composed_project:
        composed = args.composed_project.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected.items()),
                'Actual composed PCI project sources differ')
        require(all((composed / name).read_bytes() == path.read_bytes()
                    for name, path in prepare.COMPANIONS.items()), 'Actual PCI companion source differs')
    if args.composed_source:
        composed = args.composed_source.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected_source.items()),
                'Actual composed original PCI sources differ')
    # The exact GPU write gate and every unrelated existing device operation
    # remain byte-for-byte unchanged. No new handle reaches configWrite.
    require(function(selected[prepare.SERVICES], 'pciWrite') ==
            function(original_project[prepare.SERVICES], 'pciWrite'), 'Original GPU-only write gate changed')
    require(function(selected[prepare.SESSION], 'Session::writeConfig') ==
            function(original_project[prepare.SESSION], 'Session::writeConfig'), 'Original Session GPU write policy changed')
    require(function(selected[prepare.DARWIN], 'configWrite') ==
            function(original_project[prepare.DARWIN], 'configWrite'), 'Original Darwin GPU write policy changed')
    output.mkdir(parents=True)
    copy = output / 'project'
    shutil.copytree(project, copy)
    for name, path in prepare.COMPANIONS.items():
        target = copy / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
    for name, text in selected.items():
        (copy / name).write_text(text)
    files = [HERE / 'prepare.py', *(HERE / name for name in prepare.SOURCE_FILES), *prepare.COMPANIONS.values()]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in files}
    compilers = {'c': args.cc.expanduser().absolute(), 'cpp': args.cxx.expanduser().absolute()}
    identities = {name: dict(invocation_path=str(path), resolved_path=str(path.resolve(strict=True)),
        sha256=sha(path.resolve(strict=True))) for name, path in compilers.items()}
    include = copy / prepare.DIRECTORY
    engine = (include / 'S540PciTopology.cpp').read_text()
    facade = facade_parts(selected[prepare.SERVICES])
    gpu_edge = function(selected[prepare.DARWIN], 'verifyTopologyGpu') + '\n' + function(
        selected[prepare.DARWIN], 'S540NvidiaDeviceTransport::validateDarwinTopology')
    original = prepare.original.cpu_fragments(selected_source)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    variants, commands = {}, []

    def execute(label, component, *, sanitized=False, negative=False, changed=None):
        work = output / label; work.mkdir()
        cpp = component != 'original'
        bodies = {'actual-engine.cpp': engine}
        if component == 'facade': bodies['actual-facade.inc'] = facade
        if component == 'gpu-edge': bodies['actual-gpu-edge.inc'] = gpu_edge
        if component == 'original': bodies = dict(original)
        if changed: bodies.update(changed)
        for name, text in bodies.items(): (work / name).write_text(text)
        unit = work / ('control.cpp' if cpp else 'control.c')
        fixture = ('check_topology.cpp.inc' if component == 'engine' else
            'check_facade.cpp.inc' if component == 'facade' else
            'check_gpu_edge.cpp.inc' if component == 'gpu-edge' else 'check_original.c.inc')
        unit.write_bytes((HERE / 'tests' / fixture).read_bytes())
        binary, dependency = work / 'control', work / 'control.d'
        command = [str(compilers['cpp' if cpp else 'c']), '-std=c++17' if cpp else '-std=c11',
            '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-I', str(include), '-I', str(work),
            '-I', str(copy / 'packages/nvidia-device-transport/src')]
        if sanitized: command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command += ['-MD', '-MF', str(dependency), str(unit), '-o', str(binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, env=environment)
        (work / 'compile.log').write_text(result.stdout + result.stderr)
        require(result.returncode == 0, 'Actual PCI CPU compilation failed:' + label + '\n' + result.stderr[-6500:])
        commands.append(command)
        bindings = dependencies(dependency)
        require(str((include / 'S540PciTopologyFacts.h').resolve()) in bindings,
                'Actual typed topology header omitted from CPU dependencies')
        results = []
        for scenario in (range(33) if component == 'engine' else [None]):
            result = subprocess.run([str(binary), *([] if scenario is None else [str(scenario)])],
                capture_output=True, text=True, timeout=45, env=environment)
            (work / ('run-' + str(scenario) + '.log')).write_text(result.stdout + result.stderr)
            if negative:
                if result.returncode != 0:
                    results.append(dict(scenario=scenario, killed=True, returncode=result.returncode)); break
            else:
                require(result.returncode == 0, 'Actual PCI CPU control failed:' + label + '\n' + result.stderr[-6500:])
                results.append(json.loads(result.stdout))
        if negative: require(results and results[-1].get('killed'), 'Actual PCI mutant survived:' + label)
        variants[label] = dict(component=component, sanitized=sanitized, negative_control=negative,
            cases=sum(row.get('cases', 0) for row in results), checks=sum(row.get('checks', 0) for row in results),
            killed=negative, results=results, binary_sha256=sha(binary), dependency_sha256=bindings)

    for component in ('engine', 'original', 'facade', 'gpu-edge'):
        execute(component + '-selected', component)
        execute(component + '-selected-sanitized', component, sanitized=True)
        require(variants[component + '-selected']['checks'] == variants[component + '-selected-sanitized']['checks'],
                'Plain and fatal-sanitized PCI check counts differ')
    spec = importlib.util.spec_from_file_location('pci_engine_mutations', HERE / 'engine_mutations.py')
    catalog = importlib.util.module_from_spec(spec); spec.loader.exec_module(catalog)
    for name, (before, after) in catalog.MUTATIONS.items():
        require(engine.count(before) == 1, 'Exact PCI engine mutant anchor changed:' + name)
        execute('mutant-engine-' + name, 'engine', negative=True,
                changed={'actual-engine.cpp': engine.replace(before, after)})
    for name, (filename, before, after) in prepare.original.ORIGINAL_MUTATIONS.items():
        require(original[filename].count(before) == 1, 'Exact original PCI mutant anchor changed:' + name)
        execute('mutant-original-' + name, 'original', negative=True,
                changed={filename: original[filename].replace(before, after)})
    facade_mutations = {
        'foreign-nv-accepted': ('state == binding.state', 'state != nullptr'),
        'non-GPU-write-accepted': ('!handle || handle != binding.pciHandle)', '!handle || false)'),
        'non-GPU-read-uses-GPU': ('return binding.session->readTopology(handle,offset,width,value);',
                                'return binding.session->readConfig(offset,width,value);'),
        'lookup-reads-GPU-before-fixed-match': ('if (!facts.segmentKnown || facts.segment != segment) return nullptr;',
            'if (!binding.session->accessible() || !facts.segmentKnown || facts.segment != segment) return nullptr;'),
        'lost-actual-refusal-status': ('s540FirstTxnObserveServiceRefusal(7U, producer, status);',
            's540FirstTxnObserveServiceRefusal(7U, producer, NV_ERR_NOT_SUPPORTED);'),
        'failure-publication-order': ('s540FirstTxnObserveServiceRefusal(7U, producer, status);\n    s540GlobalRmRecordUnavailable(producer);',
            's540GlobalRmRecordUnavailable(producer);\n    s540FirstTxnObserveServiceRefusal(7U, producer, status);'),
        'read-failure-clobbers-output': ('if (status == NV_OK) *out = static_cast<NvU8>(captured);',
            'if (true) *out = static_cast<NvU8>(captured);'),
        'preboot-generation-change-ignored': ('return after == before ? NV_OK : NV_ERR_INVALID_STATE;',
            'return NV_OK;'),
        'preboot-late-cancellation-ignored': ('status = s540FirstTxnOptionalNvlinkActive(exactNv, &after);',
            'after = before; status = NV_OK;')
    }
    for name, (before, after) in facade_mutations.items():
        require(facade.count(before) == 1, 'Exact PCI facade mutant anchor changed:' + name)
        execute('mutant-facade-' + name, 'facade', negative=True,
                changed={'actual-facade.inc': facade.replace(before, after)})
    spec = importlib.util.spec_from_file_location('pci_gpu_edge_mutations', HERE / 'gpu_edge_mutations.py')
    gpu_catalog = importlib.util.module_from_spec(spec); spec.loader.exec_module(gpu_catalog)
    for name, (before, after) in gpu_catalog.MUTATIONS.items():
        require(gpu_edge.count(before) == 1, 'Exact PCI GPU-edge mutant anchor changed:' + name)
        execute('mutant-gpu-edge-' + name, 'gpu-edge', negative=True,
                changed={'actual-gpu-edge.inc': gpu_edge.replace(before, after)})
    spec = importlib.util.spec_from_file_location('pci_system_info_controls', HERE / 'check_system_info.py')
    system_info_helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(system_info_helper)
    system_info = system_info_helper.run(selected_source[prepare.original.GSP], output / 'system-info', compilers['c'])
    sdk_rows, sdk_identity = [], None
    if args.kernel_sdk:
        sdk = args.kernel_sdk.resolve(strict=True)
        sys.path.insert(0, str(ROOT / 'builders'))
        import link_nvidia_first_transaction as linker
        import compose_nvidia_first_transaction as composer
        sdk_common = composer.load('pci_sdk_identity', composer.FIRST / 'original/common.py')
        sdk_identity = sdk_common.validate_sdk(sdk, None, True)
        flags, cpp_flags = linker.kernel_flags(sdk)
        index = flags.index('-arch'); del flags[index:index + 2]
        flags.remove('-mmacosx-version-min=15.0')
        flags = ['-target', 'x86_64-apple-macos15.0', *flags]
        preceding_composition = json.loads((project.parent / 'composition.json').read_bytes())
        sdk_includes = [part for name in preceding_composition['retained_trial']['include_directories']
            for part in ('-I', str(copy / name))]
        source_macros = {row['source']: row.get('compile_definitions', {})
            for row in preceding_composition['project_translation_units']}
        sdk_output = output / 'sdk'; sdk_output.mkdir()
        for index, name in enumerate((prepare.SESSION, prepare.DARWIN, prepare.SERVICES,
                prepare.DIRECTORY + '/S540PciTopology.cpp', prepare.DIRECTORY + '/sdk_import_reference.cpp')):
            obj = sdk_output / ('source-%u.o' % index); dependency = obj.with_suffix('.d')
            command = [str(compilers['cpp']), *flags, *cpp_flags, '-fcheck-new',
                '-fno-use-cxa-atexit', '-mllvm', '-disable-atexit-based-global-dtor-lowering',
                *['-D' + key + '=' + value for key, value in sorted(source_macros.get(name, {}).items())],
                '-I', str(include), *sdk_includes, '-Wframe-larger-than=4096', '-Werror=frame-larger-than', '-fstack-usage',
                '-MD', '-MF', str(dependency), '-c', str(copy / name), '-o', str(obj)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            obj.with_suffix('.log').write_text(result.stdout + result.stderr)
            require(result.returncode == 0, 'Actual PCI SDK cross compilation failed:' + name + '\n' + result.stderr[-6500:])
            commands.append(command)
            sdk_rows.append(dict(source=name, source_sha256=sha(copy / name), object_sha256=sha(obj),
                command=command, dependency_sha256=dependencies(dependency), stack_usage_path=str(obj.with_suffix('.su'))))
        require(sdk_common.validate_sdk(sdk, None, True) == sdk_identity,
                'Actual pinned kernel SDK changed during PCI controls')
    require({str(path.relative_to(ROOT)): sha(path) for path in files} == hashes,
            'PCI profile source changed during controls')
    report = dict(format=1, status='passed-actual-PCI-topology-facts-controls',
        exact_project_input_sha256={n: hashlib.sha256(v.encode()).hexdigest() for n, v in original_project.items()},
        exact_original_input_sha256={n: hashlib.sha256(v.encode()).hexdigest() for n, v in original_source.items()},
        exact_project_output_sha256={n: hashlib.sha256(v.encode()).hexdigest() for n, v in selected.items()},
        exact_original_output_sha256={n: hashlib.sha256(v.encode()).hexdigest() for n, v in selected_source.items()},
        source_file_sha256=hashes, variants=variants, commands=commands, compiler_identities=identities,
        sdk_cross=sdk_rows, sdk_identity=sdk_identity, system_info=system_info,
        actual_fixed_record_engine=True, actual_original_PCI_wrapper_and_fallback_bodies=True,
        actual_linear_and_DFS_scan_bodies=True, actual_Darwin_GPU_edge_validation_bodies=True,
        actual_DeviceServices_facade_bodies=True, kernel_ancestry_executed=False,
        actual_kernel_Session_executed=False, original_RM_executed=False, native_Darwin_compilation=False,
        physical_PCI_executed=False, GSP_executed=False, new_user_wire_protocol=False,
        physical_release_authorized=False, formal_stack_or_deadline_bound_proven=False,
        endpoints='Typed CPU PCI Reader, GPU Session/ordinary/thread/binding, OBJGPU/CL/OS services; actual non-GPU engine executes.',
        sanitizer_policy=dict(address_and_undefined_fatal=True, leak_sanitizer_enabled=False))
    selected_variants = [value for value in variants.values()
        if not value['negative_control'] and not value['sanitized']]
    report['control_summary'] = dict(
        cases=sum(value['cases'] for value in selected_variants) + system_info['cases'],
        checks_per_mode=sum(value['checks'] for value in selected_variants) + system_info['checks_per_mode'],
        mutants_killed=sum(bool(value['killed']) for value in variants.values()) + system_info['mutants_killed'],
        sdk_units=len(sdk_rows))
    (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input-project', 'input-source', 'output', 'cc', 'cxx'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('composed-project', 'composed-source', 'kernel-sdk'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--host-control', action='store_true')
    report = run(parser.parse_args())
    print(json.dumps(dict(status=report['status'], **report['control_summary'])))
