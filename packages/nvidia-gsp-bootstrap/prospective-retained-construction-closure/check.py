#!/usr/bin/env python3
"""Run actual original retained construction at every Host allocation position.

CPU-only controls, not a kernel-entry successor. Every original TU is compiled;
only the reviewed privileged CR4 TU uses the existing explicit CPU fixture.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import shlex
import importlib.util
import prepare as candidate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import compile_nvidia_global_rm as original
import compose_nvidia_first_transaction as composition
import check_nvidia_global_lifecycle as lifecycle
sys.path.insert(0, str(HERE.parent / 'prospective-first-transaction/original'))
import common

RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
EXCLUDED = {
    'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp',
    'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKmod.cpp'}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def command(argv, log: Path, *, cwd=None, timeout=300):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, text=True,
        capture_output=True, timeout=timeout)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Retained-construction CPU command failed; see ' + str(log) + '\n' + result.stderr[-6000:])
    return result

def run(args):
    upstream = original._pinned_upstream(args.upstream)
    composed = args.composition.resolve(strict=True)
    manifest = composition.verify_composition(composed)
    for name in ('retained_diagnostic','retained_backends','global_epoch'):
        if manifest.get('fixed_source_profiles', {}).get(name) is not True:
            raise ValueError('Exact retained construction prerequisite missing: '+name)
    output = composition.new_output(args.output, [upstream, composed, HERE,
        ROOT / 'packages/nvidia-global-rm', ROOT / 'packages/nvidia-gsp-bootstrap'])
    cc, cxx = common.compiler(str(args.cc)), common.compiler(str(args.cxx))
    identity = common.execution_identity(cc, cxx, args.host_control)
    output.mkdir(parents=True)
    project = output / 'project'
    shutil.copytree(composed / 'project', project)
    source = output / 'source'
    shutil.copytree(composed / 'source', source)
    values = {name:(project/name).read_text() for name in candidate.INPUTS}
    for name,value in candidate.transforms(values).items():
        (project/name).write_text(value)
    values = {name:(source/name).read_text() for name in candidate.ORIGINAL_INPUTS}
    for name,value in candidate.original_transforms(values).items():
        (source/name).write_text(value)
    # Observation-only hooks surround the exact retention boundary and both
    # generated cleanup sites. They cannot change any original outcome.
    system=source/candidate.SYSTEM
    system.write_text(candidate.once(system.read_text(),
        '#include "S540NvidiaGspFirstTransaction.h"',
        '#include "S540NvidiaGspFirstTransaction.h"\n'
        'extern void s540RetainedControlClaim(const void *, NV_STATUS);\n'
        'extern void s540RetainedControlCleanup(unsigned, const void *);'))
    system.write_text(candidate.once(system.read_text(),
        '    if (s540FirstTxnGlobalRetainConstruction(pSys, status))\n        return status;',
        '    if (s540FirstTxnGlobalRetainConstruction(pSys, status)) {\n'
        '        s540RetainedControlClaim(pSys, status);\n        return status;\n    }\n'
        '    s540RetainedControlCleanup(1, pSys);'))
    generated_source=source/candidate.GENERATED
    generated_source.write_text(candidate.once(generated_source.read_text(),
        '#include "S540NvidiaGspFirstTransaction.h"',
        '#include "S540NvidiaGspFirstTransaction.h"\n'
        'extern void s540RetainedControlCleanup(unsigned, const void *);'))
    generated_source.write_text(candidate.once(generated_source.read_text(),
        '        goto __nvoc_ctor_OBJSYS_exit;\n    __nvoc_dtor_OBJTRACEABLE',
        '        goto __nvoc_ctor_OBJSYS_exit;\n'
        '    s540RetainedControlCleanup(2, arg_this);\n    __nvoc_dtor_OBJTRACEABLE'))
    generated_source.write_text(candidate.once(generated_source.read_text(),
        '        return __nvoc_status;\n\n    // Unlink the child',
        '        return __nvoc_status;\n'
        '    s540RetainedControlCleanup(3, __nvoc_pThis);\n\n    // Unlink the child'))
    # Explicit CPU-only hook after the complete actual original core returns.
    # It can acquire the genuine API/allocation lock, never set readiness.
    lifecycle_source = project / 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
    lifecycle_source.write_text(candidate.once(lifecycle_source.read_text(), '    status=coreInitializeRm();',
        '    status=coreInitializeRm();\n    s540GlobalEpochControlAfterCore();'))
    lifecycle_source.write_text(candidate.once(lifecycle_source.read_text(), 'extern RsServer g_resServ;',
        'extern void s540GlobalEpochControlAfterCore(void);\nextern RsServer g_resServ;'))
    project_inventory = composition.inventory(project)
    original_inventory = composition.inventory(source)
    namespace = composed / manifest['namespace']
    include = [v.replace(str(composed / 'project'), str(project))
               for v in composition.include_flags(composed)] + ['-I', str(HERE)]
    target = [] if args.host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0']
    definitions = dict(manifest.get('fixed_source_profiles', {}).get('required_compile_definitions', {}))
    # These immutable source guards select already composed implementations;
    # no definition grants original entry or a hardware/lifetime receipt.
    if any('/prospective-platform-closure/' in row['source'] for row in manifest['project_translation_units']):
        definitions['S540_NVIDIA_DARWIN_PLATFORM_CLOSURE'] = '1'
    defines = ['-D' + k + '=' + v for k, v in sorted(definitions.items())]
    source_root = source / 'src/nvidia'
    base_flags = original.original_bridge_flags(upstream, output / 'bridge-plan', cc, namespace)
    raw, base = str(upstream), str(source)
    base_flags = [base + v[len(raw):] if v.startswith(raw + '/') else v for v in base_flags]
    bridge = lifecycle._user_flags(base_flags, target, args.host_control) + defines + include
    cpp_flags = [*target, '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-std=c++17',
        '-pthread', '-ffunction-sections', '-fdata-sections', '-fno-exceptions', '-fno-rtti',
        *defines, *include]
    common_c = [*target, '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
        '-ffunction-sections', '-fdata-sections', *defines, *include]
    report = {'format': 1, 'status': 'running', **identity,
        'component': 'actual-original-retained-construction-allocation-closure',
        'composition_sha256': sha(composed / 'composition.json'),
        'record_source_sha256': sha(composed / 'project' / RECORD),
        'source_successor': 'retained-failed-global-construction',
        'record_policy_modified': True, 'cpu_postcore_lock_acquisition_hook': True,
        'control_source_sha256': {p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
        'original_source_inventory_sha256': composition.tree_sha(original_inventory),
        'privileged_cpu_fixture': True, 'platform_facts_fixture': True,
        'unavailable_scalar_policy': 'exact typed aborting CPU tripwire',
        'excluded_kernel_only_sources': sorted(EXCLUDED), 'variants': {},
        'kernel_execution': False, 'gpu_access': False, 'original_entry_admission': False,
        'production_candidate_allowed': False, 'installable_candidate_generated': False}
    destination = output / 'results.json'
    write(destination, report)
    reuse_root = args.reuse_originals.resolve(strict=True) if args.reuse_originals else None
    if reuse_root:
        prior=json.loads((reuse_root/'results.json').read_text())
        if prior['composition_sha256']!=report['composition_sha256'] or prior['compilers']!=report['compilers']:
            raise ValueError('Original object reuse requires the exact composed sources and compiler identity')
        # Original compilation can see any companion header. Only the nonincluded record
        # implementation may differ; every header and every
        # other companion byte must remain the same, including forced input.
        prior_project=composition.inventory(reuse_root/'project')
        for name in set(prior_project)|set(project_inventory):
            if name == candidate.RECORD:continue
            if prior_project.get(name)!=project_inventory.get(name):
                raise ValueError('Original compile companion changed before reuse: '+name)
        report['original_reuse_input']={'path':str(reuse_root),
            'results_sha256':sha(reuse_root/'results.json'),
            'all_original_sources_bound_by_composition':True,
            'all_project_companions_identical_except_nonincluded_record_C_implementation':True}
        if composition.inventory(reuse_root/'source') != original_inventory:
            raise ValueError('Original reuse requires every original source/header byte to match')
    try:
        for variant in args.variants:
            work = output / variant
            work.mkdir()
            instrument = [] if variant == 'plain' else [
                '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
                '-fno-omit-frame-pointer']
            entries = original.original_commands(upstream, work / 'make-plan', cc)
            generated = work / 'g_nvid_string.c'
            generated.write_text('const char NVRM_ID[] = "nvidia id: 615.78.08 Global Owner CPU Control";\n'
                                 'const char *const pNVRM_ID = NVRM_ID + 11;\n')
            reuse_manifest=reuse_root/variant/'original-compilation.json' if reuse_root else None
            reuse_rows={r['source']:r for r in json.loads(reuse_manifest.read_text())} if reuse_manifest and reuse_manifest.is_file() else {}
            def compile_original(item):
                index, entry = item
                relative = entry[entry.index('-c') + 1]
                source = generated if Path(relative).is_absolute() else source_root / relative
                fixture = relative == lifecycle.CPU_SOURCE
                if fixture: source = lifecycle.CPU_FIXTURE
                flags = lifecycle._user_flags(entry[1:entry.index('-c')], target, args.host_control)
                source_profile = [] if Path(relative).is_absolute() else composition.original_source_flags(
                    manifest,(source_root/relative).resolve().relative_to(output/'source').as_posix())
                obj = work / ('original-%04d.o' % index)
                argv = [cc, *flags, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
                    '-DNV_VERSION_STRING="615.78.08"', '-include', namespace,
                    *defines, *source_profile, *include, *instrument, '-c', source, '-o', obj]
                previous=reuse_rows.get(relative)
                reused=False
                if previous:
                    normalized=[v.replace(str(reuse_root),str(output)) for v in previous['command']]
                    old_object=Path(previous['object'])
                    if (normalized==[str(v) for v in argv] and
                        previous['source_sha256']==sha(source) and
                        old_object.is_file() and sha(old_object)==previous['object_sha256']):
                        shutil.copyfile(old_object,obj);reused=True
                if not reused:command(argv, obj.with_suffix('.log'), cwd=source_root)
                return {'source': relative, 'compiled_source': str(source),
                    'source_sha256': sha(source), 'object': str(obj), 'object_sha256': sha(obj),
                    'privileged_cpu_fixture': fixture, 'command': [str(x) for x in argv],
                    'byte_identical_original_object_reused':reused}
            rows = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
                futures = {pool.submit(compile_original, item): item[0] for item in enumerate(entries)}
                for future in concurrent.futures.as_completed(futures):
                    rows.append(future.result())
                    if len(rows) % 100 == 0:
                        print(json.dumps({'variant': variant, 'compiled_original_units': len(rows)}), flush=True)
            rows.sort(key=lambda row: row['source'])
            if len(rows) != 1100 or sum(row['privileged_cpu_fixture'] for row in rows) != 1:
                raise ValueError('Actual full original source/CPU-fixture inventory changed.')
            write(work / 'original-compilation.json', rows)
            objects = [Path(row['object']) for row in rows]
            project_objects = []
            project_rows = []
            for index, row in enumerate(manifest['project_translation_units']):
                if row['source'] in EXCLUDED: continue
                source = project / row['source']
                obj = work / ('project-%03d-' % index + source.stem + '.o')
                kind = row['kind']
                compiler, flags = ((cxx, cpp_flags) if kind == 'cpp' else
                    (cc, bridge) if kind == 'original-c' else
                    (cc, ['-std=c11', *common_c]))
                flags = [*flags,*['-D'+name+'='+value for name,value in sorted(
                    row.get('compile_definitions',{}).items())]]
                for relative in row.get('original_include_directories',[]):
                    flags += ['-I',str(output/'source'/composition.checked_relative(relative))]
                argv = [compiler, *flags, *instrument, '-c', source, '-o', obj]
                command(argv, obj.with_suffix('.log'), cwd=source_root)
                project_objects.append(obj)
                project_rows.append({'source': row['source'], 'source_sha256': sha(source),
                    'object': str(obj), 'object_sha256': sha(obj), 'command': [str(x) for x in argv]})
            write(work / 'project-compilation.json', project_rows)
            provided = set().union(*(lifecycle._symbols(p, args.host_control)[0] for p in project_objects))
            boundaries = lifecycle._private_boundaries(work, provided)
            boundary = work / 'native-unavailable-boundaries.o'
            command([cc, *bridge, *instrument, '-c', work / 'native-unavailable-boundaries.c',
                     '-o', boundary], work / 'native-boundaries.log', cwd=source_root)
            assertion = work / 'nvswitch-assert-fixture.o'
            command([cc, *bridge, *instrument, '-c', lifecycle.PACKAGE / 'tests/fixtures/nvswitch_assert_fixture.c',
                     '-o', assertion], work / 'nvswitch-assert.log', cwd=source_root)
            original_control = work / 'epoch-original-control.o'
            command([cc, *bridge, *instrument, '-c', HERE / 'check_original.c', '-o', original_control],
                work / 'original-control.log', cwd=source_root)
            harness = work / 'global-epoch-harness.o'
            command([cxx, *cpp_flags, *instrument, '-c', HERE / 'check_epoch.cpp',
                     '-o', harness], work / 'harness.log')
            binary = work / 'global-epoch-check'
            command([cxx, *cpp_flags, *instrument, harness, *objects, *project_objects, original_control, boundary,
                     assertion, '-Wl,--gc-sections' if args.host_control else '-Wl,-dead_strip',
                     '-o', binary], work / 'link.log', timeout=300)
            observations = []
            environment = dict(os.environ)
            environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
            environment['UBSAN_OPTIONS'] = 'halt_on_error=1:abort_on_error=1'
            for scenario in range(10):
                result = subprocess.run([str(binary), str(scenario)], text=True, capture_output=True,
                    timeout=120, env=environment)
                (work / ('scenario-%u.log' % scenario)).write_text(result.stdout + result.stderr)
                try: observed = json.loads(result.stdout)
                except json.JSONDecodeError:
                    raise RuntimeError('Actual global-owner scenario terminated without a result: ' +
                        str(scenario) + '\n' + result.stderr[-6000:])
                observed['process_status'] = result.returncode
                observations.append(observed)
                report['variants'][variant] = {'observations': observations, 'boundaries': boundaries,
                    'actual_original_units': 1098, 'privileged_cpu_fixture_units': 1,
                    'generated_identification_units': 1, 'actual_project_units': len(project_rows),
                    'byte_identical_original_objects_reused':sum(r['byte_identical_original_object_reused'] for r in rows),
                    'original_compilation_sha256': sha(work / 'original-compilation.json'),
                    'project_compilation_sha256': sha(work / 'project-compilation.json'),
                    'binary_sha256': sha(binary)}
                write(destination, report)
                print(json.dumps({'variant': variant, **observed}), flush=True)
                if result.returncode or observed['failures']:
                    raise RuntimeError('Actual composed global construction did not satisfy owner integration: scenario ' + str(scenario))
            allocation_positions=observations[0]['allocations']
            if allocation_positions<154:
                raise ValueError('The genuine original success path no longer reaches late allocation154')
            faults=[]
            for ordinal in range(1,allocation_positions+2):
                result=subprocess.run([str(binary),'6',str(ordinal)],text=True,capture_output=True,
                    timeout=30,env=environment)
                (work/('allocation-%04d.log'%ordinal)).write_text(result.stdout+result.stderr)
                try:observed=json.loads(result.stdout)
                except json.JSONDecodeError:
                    raise RuntimeError('Actual allocation fault did not return a result: '+str(ordinal)+'\n'+result.stderr[-6000:])
                observed['process_status']=result.returncode
                faults.append(observed)
                report['variants'][variant]['allocation_faults']=faults
                write(destination,report)
                if result.returncode or observed['failures']:
                    raise RuntimeError('Actual original retained allocation failure failed: '+str(ordinal))
                if ordinal<=allocation_positions and not observed['allocation_failures']:
                    raise RuntimeError('Declared allocation position was not actually injected: '+str(ordinal))
                if ordinal==allocation_positions+1 and observed['allocation_failures']:
                    raise RuntimeError('Terminal control unexpectedly reached a new allocation position')
            report['variants'][variant]['all_allocation_positions_tested']=allocation_positions
            report['variants'][variant]['terminal_unreached_fault_control']=True
            write(destination,report)
        composition.verify_composition(composed)
        for name,digest in report['control_source_sha256'].items():
            if sha(HERE/name)!=digest:raise ValueError('Control source changed during check: '+name)
        if composition.inventory(project) != project_inventory:
            raise ValueError('The CPU project companion changed during its integration check.')
        if composition.inventory(output / 'source') != original_inventory:
            raise ValueError('Actual original source changed during retained-construction checks')
        report['status'] = 'passed-actual-original-retained-construction-allocation-closure'
        report['global_allocation_failure_closure']=True
    except Exception as error:
        report.update(status='failed', failure_type=type(error).__name__, failure=str(error))
        raise
    finally:
        write(destination, report)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream', 'composition', 'output', 'cc', 'cxx'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    parser.add_argument('--variants', choices=('plain', 'sanitized'), nargs='+', default=['plain', 'sanitized'])
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--reuse-originals',type=Path)
    run(parser.parse_args())
