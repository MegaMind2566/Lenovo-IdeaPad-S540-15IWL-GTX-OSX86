#!/usr/bin/env python3
"""Fresh CPU controls for the reconstructed retained constructor failure path.

Every complete original TU is compiled. The privileged CR4 TU is an explicit
CPU fixture. No historical binary, freeze, or compile result is reused.
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
        raise RuntimeError('CPU global-owner command failed; see ' + str(log) + '\n' + result.stderr[-6000:])
    return result

def dependency_inventory(path,cwd):
    raw=path.read_text().replace('\\\n',' ')
    if ':' not in raw:raise ValueError('Malformed compiler dependency capture')
    files=shlex.split(raw.split(':',1)[1])
    out={}
    for name in files:
        source=Path(name)
        if not source.is_absolute():source=cwd/source
        source=source.resolve(strict=True)
        out[str(source)]=sha(source)
    if not out:raise ValueError('Compiler captured no actual dependencies')
    return out

def run(args):
    upstream = original._pinned_upstream(args.upstream)
    composed = args.composition.resolve(strict=True)
    manifest = composition.verify_composition(composed)
    if manifest.get('fixed_source_profiles', {}).get('retained_diagnostic') is not True:
        raise ValueError('The exact composed retained Host source profile is required.')
    output = composition.new_output(args.output, [upstream, composed, HERE,
        ROOT / 'packages/nvidia-global-rm', ROOT / 'packages/nvidia-gsp-bootstrap'])
    cc, cxx = common.compiler(str(args.cc)), common.compiler(str(args.cxx))
    identity = common.execution_identity(cc, cxx, args.host_control)
    output.mkdir(parents=True)
    project = output / 'project'
    shutil.copytree(composed / 'project', project)
    record = project / RECORD
    if not all(manifest.get('fixed_source_profiles',{}).get(k) is True
            for k in ('retained_diagnostic','retained_backends','global_epoch')):
        raise ValueError('Exact retained Host/backend/global epoch composition required')
    source=output/'source'
    shutil.copytree(composed/'source',source)
    for name,text in candidate.project_transforms({n:(project/n).read_text() for n in candidate.PROJECT_INPUTS}).items():
        (project/name).write_text(text)
    for name,text in candidate.original_transforms({n:(source/n).read_text() for n in candidate.ORIGINAL_INPUTS}).items():
        (source/name).write_text(text)
    # Observation hooks capture actual bytes at the genuine retention boundary,
    # and observe both generated cleanup guards. They do not decide retention.
    system=source/candidate.SYSTEM
    system.write_text(candidate.once(system.read_text(),
        '        if (retentionStatus == NV_OK)\n            return status;',
        '        if (retentionStatus == NV_OK) {\n'
        '            s540ConstructionControlRetained(pSys);\n            return status;\n        }'))
    system.write_text('extern void s540ConstructionControlRetained(const void *);\n'+system.read_text())
    generated=source/candidate.GENERATED
    text=candidate.once(generated.read_text(),
        '    if (s540FirstTxnGlobalFailedSystemRetained(arg_this)) return status;',
        '    if (s540FirstTxnGlobalFailedSystemRetained(arg_this)) {\n'
        '        s540ConstructionControlGuard(arg_this,1);return status;\n    }')
    text=candidate.once(text,'        /* Preserve heap-construction failure output',
        '        s540ConstructionControlGuard(__nvoc_pThis,2);\n'
        '        /* Preserve heap-construction failure output')
    generated.write_text('extern void s540ConstructionControlGuard(const void *,unsigned);\n'+text)
    # Explicit CPU-only hook after the complete actual original core returns.
    # It can acquire the genuine API/allocation lock, never set readiness.
    lifecycle_source = project / 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
    lifecycle_source.write_text(candidate.once(lifecycle_source.read_text(), '    status=coreInitializeRm();',
        '    status=coreInitializeRm();\n    s540GlobalEpochControlAfterCore();'))
    lifecycle_source.write_text(candidate.once(lifecycle_source.read_text(), 'extern RsServer g_resServ;',
        'extern void s540GlobalEpochControlAfterCore(void);\nextern RsServer g_resServ;'))
    project_inventory = composition.inventory(project)
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
        'component': 'reconstructed-retained-constructor-cpu-integration',
        'composition_sha256': sha(composed / 'composition.json'),
        'record_source_sha256': sha(composed / 'project' / RECORD),
        'source_successor': 'reconstructed-global-construction-retention',
        'record_policy_modified': True, 'cpu_postcore_lock_acquisition_hook': True,
        'control_source_sha256': {p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
        'privileged_cpu_fixture': True, 'platform_facts_fixture': True,
        'unavailable_scalar_policy': 'exact typed aborting CPU tripwire',
        'excluded_kernel_only_sources': sorted(EXCLUDED), 'variants': {},
        'kernel_execution': False, 'gpu_access': False, 'original_entry_admission': False,
        'production_candidate_allowed': False, 'installable_candidate_generated': False}
    destination = output / 'results.json'
    write(destination, report)
    reuse_root=args.reuse_originals.resolve(strict=True) if args.reuse_originals else None
    prior_rows={}
    if reuse_root:
        prior=json.loads((reuse_root/'results.json').read_text())
        if prior['composition_sha256']!=report['composition_sha256'] or prior['compilers']!=report['compilers']:
            raise ValueError('Reuse requires the exact composition and compiler identity')
        if composition.inventory(reuse_root/'source')!=composition.inventory(source):
            raise ValueError('Reuse requires every original source and header byte to match')
        if composition.inventory(reuse_root/'project')!=project_inventory:
            raise ValueError('Reuse requires every project companion byte to match')
        report['fresh_object_reuse_input']={'path':str(reuse_root),
            'results_sha256':sha(reuse_root/'results.json'),
            'prior_status':prior['status'],'prior_run_result_reused':False}
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
            prior_rows={r['source']:r for r in json.loads(reuse_manifest.read_text())} if reuse_manifest and reuse_manifest.is_file() else {}
            def compile_original(item):
                index, entry = item
                relative = entry[entry.index('-c') + 1]
                source = generated if Path(relative).is_absolute() else source_root / relative
                fixture = relative == lifecycle.CPU_SOURCE
                if fixture: source = lifecycle.CPU_FIXTURE
                flags = lifecycle._user_flags(entry[1:entry.index('-c')], target, args.host_control)
                obj = work / ('original-%04d.o' % index)
                argv = [cc, *flags, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
                    '-DNV_VERSION_STRING="615.78.08"', '-include', namespace,
                    *defines, *include, *instrument, '-c', source, '-o', obj]
                dependency=obj.with_suffix('.d')
                argv += ['-MMD','-MF',dependency]
                reused=False;previous=prior_rows.get(relative)
                if previous:
                    normalize=lambda value:value.replace(str(reuse_root),str(output))
                    expected={normalize(name):digest for name,digest in previous['dependency_sha256'].items()}
                    if ([normalize(v) for v in previous['command']]!=[str(v) for v in argv] or
                        previous['source_sha256']!=sha(source) or
                        sha(Path(previous['object']))!=previous['object_sha256'] or
                        sha(Path(previous['object']).with_suffix('.d'))!=previous['dependency_capture_sha256'] or
                        any(sha(Path(name))!=digest for name,digest in expected.items())):
                        raise ValueError('Exact fresh original object/dependency reuse proof changed: '+relative)
                    shutil.copyfile(previous['object'],obj)
                    # Preserve the authentic prior compiler capture verbatim;
                    # normalized dependency identities are explicit below.
                    shutil.copyfile(Path(previous['object']).with_suffix('.d'),dependency)
                    dependencies=expected;reused=True
                else:
                    command(argv,obj.with_suffix('.log'),cwd=source_root)
                    dependencies=dependency_inventory(dependency,source_root)
                return {'source': relative, 'compiled_source': str(source),
                    'source_sha256': sha(source), 'object': str(obj), 'object_sha256': sha(obj),
                    'privileged_cpu_fixture': fixture, 'command': [str(x) for x in argv],
                    'byte_identical_original_object_reused':reused,
                    'dependency_sha256':dependencies, 'dependency_capture_sha256':sha(dependency)}
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
            binary_digest=sha(binary)
            def binary_unchanged():
                if not binary.stat().st_mode&0o111 or sha(binary)!=binary_digest:
                    raise RuntimeError('CPU executable integrity changed outside the declared build: '+str(binary))
            observations = []
            environment = dict(os.environ)
            environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
            environment['UBSAN_OPTIONS'] = 'halt_on_error=1:abort_on_error=1'
            for scenario in range(10):
                binary_unchanged()
                result = subprocess.run([str(binary), str(scenario)], text=True, capture_output=True,
                    timeout=120, env=environment)
                binary_unchanged()
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
                    'binary_sha256': binary_digest}
                write(destination, report)
                print(json.dumps({'variant': variant, **observed}), flush=True)
                if result.returncode or observed['failures']:
                    raise RuntimeError('Actual composed global construction did not satisfy owner integration: scenario ' + str(scenario))
            # All of these are actual returned outcomes. A timeout/crash is
            # a failed regression, never a passing negative control.
            regressions=[]
            for scenario,ordinal in [(6,154),(7,155),(7,156)]:
                binary_unchanged()
                result=subprocess.run([str(binary),str(scenario),str(ordinal)],text=True,
                    capture_output=True,timeout=10,env=environment)
                binary_unchanged()
                log=work/('allocation-%u.log'%ordinal);log.write_text(result.stdout+result.stderr)
                observed=json.loads(result.stdout)
                observed['process_status']=result.returncode;regressions.append(observed)
                report['variants'][variant]['allocation_regressions']=regressions
                write(destination,report);print(json.dumps({'variant':variant,**observed}),flush=True)
                if result.returncode or observed['failures']:
                    raise RuntimeError('Actual retained allocation regression failed: '+str(ordinal))
        composition.verify_composition(composed)
        for name,digest in report['control_source_sha256'].items():
            if sha(HERE/name)!=digest:raise ValueError('Control source changed during check: '+name)
        if composition.inventory(project) != project_inventory:
            raise ValueError('The CPU project companion changed during its integration check.')
        report['status'] = 'passed-reconstructed-constructor-returned-cpu-controls'
        report['global_allocation_failure_closure']=False
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
