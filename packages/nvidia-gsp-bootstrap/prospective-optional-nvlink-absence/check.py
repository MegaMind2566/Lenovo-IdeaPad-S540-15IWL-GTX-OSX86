#!/usr/bin/env python3
"""Execute actual optional-child, strong-record and diagnostic C bodies."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import shlex
import shutil
import subprocess
import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHARED = ROOT / 'packages/nvidia-gsp-bootstrap/cancellation/prepare_wait_candidates.py'
SHARED_SHA = 'f8e0099f904b5e1a756e628985ef991c9a09475214f52a38c921ccc5df6de471'
LIBRARY = 'src/common/nvlink/kernel/nvlink/nvlink_lib_mgmt.c'
CANCELLATION = 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c'
HELPERS = ('currentThread', 'bound', 'exact', 'master', 'first', 'checkedMaster',
           'globalMaster', 'exactGlobalMaster')
PROBES = ('s540FirstTxnOptionalNvlinkActive', 's540FirstTxnOptionalNvlinkReturned')
CASES = ('active', 'helper_null_out', 'helper_null_gpu', 'helper_null_slot',
    'absence', 'repeat', 'hal_skip', 'other_class', 'other_instance', 'initialized',
    'engine86', 'base86', 'missing', 'published', 'registry_error', 'registry_zero',
    'registry_other', 'registry_sticky', 'registry_cancel', 'reserve_failure',
    'reserve_generation', 'get_unpublished', 'get_null', 'get_sticky', 'get_inflight',
    'get_no_exit', 'get_not_returned', 'get_stale', 'get_foreign_nv', 'get_foreign_master',
    'get_irq', 'get_global_state', 'get_global_unvalidated', 'get_global_not_returned',
    'get_owner_mismatch', 'get_generation_mismatch', 'get_master_mismatch',
    'get_global_status', 'get_global_validation', 'log_absent', 'log_sticky',
    'log_unavailable', 'log_foreign', 'foreign_nv', 'null_nv', 'foreign_master', 'irq',
    'thread_error', 'thread_zero', 'unbound', 'owner_missing', 'owner_mismatch',
    'generation_mismatch', 'master_mismatch', 'sticky', 'phase', 'not_inflight',
    'exit_ready', 'already_returned', 'global_state', 'global_unvalidated',
    'global_not_returned', 'global_status', 'global_validation', 'cancel_scope', 'cancel_status',
    'cancel_idle', 'cancel_token', 'cancel_unbound', 'cancel_owner', 'cancel_cleanup',
    'cancel_revoked', 'cancel_publication', 'cancel_generation', 'cancel_format',
    'cancel_bound', 'cancel_output_generation', 'cancel_race')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def changed(text, before, after, count=1):
    require(text.count(before) == count, 'Actual optional-child mutation anchor changed: ' + before)
    return text.replace(before, after)


def function(text, name):
    first, last = prepare.function_span(text, name)
    begin = text.rfind('\n', 0, first) + 1
    if not text[begin:first].strip():
        begin = text.rfind('\n', 0, begin - 1) + 1
    return text[begin:last] + '\n'


def dependencies(path):
    return {str(Path(p).resolve(strict=True)): sha(Path(p).resolve(strict=True))
        for p in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1])}


def run(args):
    require(args.host_control, 'Explicit --host-control is required for CPU endpoints')
    require(sha(SHARED) == SHARED_SHA, 'The shared actual-C function extractor changed')
    source = args.input_source.resolve(strict=True)
    project = args.input_project.resolve(strict=True)
    out = args.output.absolute()
    require(not out.exists() and not any(out.is_relative_to(p) or p.is_relative_to(out)
        for p in (source, project)), 'A fresh nonoverlapping output directory is required')
    originals = {p: (source / p).read_text() for p in prepare.ORIGINAL_INPUTS}
    inputs = {p: (project / p).read_text() for p in prepare.INPUTS}
    original_output = prepare.original_transforms(originals)
    project_output = prepare.transforms(inputs)
    if args.composed_source:
        final = args.composed_source.resolve(strict=True)
        require(all((final / p).read_text() == text for p, text in original_output.items()),
                'Actual composed original source differs from the optional-child profile')
    if args.composed_project:
        final = args.composed_project.resolve(strict=True)
        require(all((final / p).read_text() == text for p, text in project_output.items()),
                'Actual composed project differs from the optional-child profile')
        require(all(sha(final / p) == sha(path) for p, path in prepare.COMPANIONS.items()),
                'Actual composed optional-child companion differs')
    refusals = 0
    for transform, values in ((prepare.original_transforms, originals), (prepare.transforms, inputs)):
        for altered in ({}, dict(values, unexpected='extra'),
                        {**values, next(iter(values)): values[next(iter(values))] + '\n'}):
            try:
                transform(altered)
            except ValueError:
                refusals += 1
            else:
                raise ValueError('A changed optional-child input was accepted')
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_bytes())
    for name, digest in contract['CPU_header_sha256'].items():
        require(sha(project / name) == digest, 'Actual CPU header changed: ' + name)
    for name, digest in contract['global_registry_bridge_sha256'].items():
        require(sha(project / name) == digest, 'Actual global registry bridge changed: ' + name)
    for name, digest in contract['project_binding_sha256'].items():
        require(sha(project / name) == digest, 'Actual cancellation producer changed: ' + name)
    for name, digest in contract['original_binding_sha256'].items():
        require(sha(source / name) == digest, 'Actual original library/profile binding changed: ' + name)
    pred = contract['predicates']
    require(pred['actual_library_macro_required'] in (source / 'src/nvidia/Makefile').read_text(),
            'The actual compiled NVLink library macro is absent')
    require(pred['selected_windows_feature_macro'] in
        (source / 'src/nvidia/generated/rmconfig.h').read_text().splitlines(),
        'The selected original profile is not the exact reviewed non-Windows profile')
    require(pred['actual_class_macro'] in
        (source / 'src/nvidia/generated/g_kernel_nvlink_nvoc.h').read_text().splitlines(),
        'Actual optional class identity changed')
    registry = (source / 'src/nvidia/arch/nvalloc/unix/include/nv-reg.h').read_text()
    require('#define __NV_NVLINK_DISABLE NvLinkDisable' in registry and
        '#define NV_REG_NVLINK_DISABLE NV_REG_STRING(__NV_NVLINK_DISABLE)' in registry,
        'Actual original global registry key spelling changed')
    gpu = original_output[prepare.GPU]
    record = project_output[prepare.RECORD]
    storage = re.search(r'static struct \{\n    NvU64 control,.*?\n\} record;', record, re.S)
    global_storage = re.search(r'static struct \{ NvU32 state,originalStatus,.*?\} globalEpoch;', record, re.S)
    require(storage and global_storage, 'The actual record storage declarations changed')
    cancellation = (project / CANCELLATION).read_text()
    cancellation_bits = re.search(r'enum \{ BOUND = 1,.*?SHIFT = 8 \};', cancellation, re.S)
    cancellation_slot = re.search(r'static struct \{\n    NvU64 control, generation, ownerThread,.*?\} slot;', cancellation, re.S)
    require(cancellation_bits and cancellation_slot, 'The actual cancellation storage declarations changed')
    cancellation_word = changed(function(cancellation, 'word'), 'word(void)', 'actualCancellationWord(void)')
    cancellation_snapshot = changed(function(cancellation, 's540GspCancellationGetSnapshot'),
        's540GspCancellationGetSnapshot(', 'actualCancellationSnapshot(')
    nv_header = (source / 'src/nvidia/arch/nvalloc/unix/include/nv.h').read_text()
    nv_macro = re.search(r'#define NV_GET_NV_STATE\(pGpu\) \\\n[^\n]+', nv_header)
    require(nv_macro is not None, 'The actual Unix GPU registry identity macro changed')
    parts = dict(RECORD_STORAGE=storage.group() + '\n' + global_storage.group(),
        CANCELLATION_STORAGE=cancellation_bits.group() + '\n' + cancellation_slot.group(),
        CANCELLATION_WORD=cancellation_word,
        CANCELLATION_HELPERS='\n'.join(function(cancellation, name) for name in ('generation', 'matches')),
        CANCELLATION_SNAPSHOT=cancellation_snapshot,
        RECORD_HELPERS='\n'.join(function(record, name) for name in HELPERS),
        RECORD_PROBES='\n'.join(function(record, name) for name in PROBES),
        BACKEND_GETTER=function((source / LIBRARY).read_text(), 'nvlink_lib_is_initialized'),
        GPU_HELPER=function(gpu, prepare.GPU_HELPER), GPU_BODY=function(gpu, 'gpuCreateObject'),
        CONTEXT_LOGGER=function(project_output[prepare.CONTEXT], 's540LogOptionalNvlinkAbsence'),
        REGISTRY_NV_MACRO=nv_macro.group(),
        REGISTRY_BASE=function((source / 'src/nvidia/arch/nvalloc/unix/src/os.c').read_text(), 'osReadRegistryDwordBase'),
        CLASS_MACRO=pred['actual_class_macro'])
    require('S540FirstTxnSnapshot' not in parts['RECORD_PROBES'] and
            's540FirstTxnGetSnapshot' not in parts['RECORD_PROBES'] and
            'checkExecution(' not in parts['RECORD_PROBES'],
            'Cached FirstTxn snapshot or mutating execution check used as optional-child authority')
    initialize = function(project_output[prepare.CONTEXT], 's540GspContextInitializeAdapter')
    boundary = '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);'
    call = '    s540LogOptionalNvlinkAbsence(context);'
    require(initialize.count(boundary) == initialize.count(call) == 1 and
        initialize.index(boundary) < initialize.index(call), 'Actual diagnostic wrapper-return order changed')
    require('objDelete(' not in parts['GPU_HELPER'] and 'nvlink_lib_initialize(' not in parts['GPU_HELPER'],
            'Optional absence added a destructor or library initialization')
    compiler = args.cc.expanduser().absolute()
    executable = compiler.resolve(strict=True)
    require(executable.is_file() and os.access(compiler, os.X_OK), 'Executable C compiler required')
    helper_paths = (SHARED, HERE / 'prepare.py', *(HERE / p for p in prepare.SOURCE_FILES), *prepare.COMPANIONS.values())
    helper_hashes = {str(p.relative_to(ROOT)): sha(p) for p in helper_paths}
    out.mkdir(parents=True)
    copy = out / 'project'
    shutil.copytree(project, copy)
    for name, body in project_output.items():
        (copy / name).write_text(body)
    for name, path in prepare.COMPANIONS.items():
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    template = (HERE / 'tests/check_optional.c.inc').read_text()
    gsp = (source / 'src/nvidia/generated/g_gpu_nvoc.h').read_text()
    actual_gsp = next(line for line in gsp.splitlines() if line.startswith('#define IS_GSP_CLIENT(pGpu)'))
    feature = next(line for line in (source / 'src/nvidia/generated/rmconfig.h').read_text().splitlines()
                   if line.startswith('#define RMCFG_FEATURE_GSP_CLIENT_RM '))
    template = changed(template, '#define IS_GSP_CLIENT(gpu) ((gpu)->isGspClient)', feature + '\n' + actual_gsp)
    production = (HERE / 'S540OptionalNvlinkAbsence.c').read_text()
    report = dict(format=1, status='running',
        scope='actual-optional-child-GPU-bodies-actual-strong-record-storage-and-probes-and-private-C-TU-with-explicit-CPU-endpoints',
        input_original_sha256={p: sha(source / p) for p in originals},
        input_project_sha256={p: sha(project / p) for p in inputs},
        output_original_sha256={p: hashlib.sha256(v.encode()).hexdigest() for p, v in original_output.items()},
        output_project_sha256={p: hashlib.sha256(v.encode()).hexdigest() for p, v in project_output.items()},
        helper_sha256=helper_hashes, exact_input_refusals=refusals,
        compiler_invocation_path=str(compiler), compiler_path=str(executable), compiler_sha256=sha(executable),
        actual_record_storage_and_probe_bodies_executed=True, cached_FirstTxn_snapshot_authority=False,
        actual_cancellation_storage_and_stable_snapshot_bodies_executed=True,
        actual_stable_cancellation_snapshot_authority=True,
        deliberate_cancellation_producer_output_fault_controls=['zero-format', 'unbound-output', 'wrong-generation-output'],
        cancellation_counter_purity_checked=True,
        actual_original_library_getter_body_executed=True, full_original_driver_execution=False,
        actual_original_global_registry_base_body_executed=True,
        actual_GSP_execution=False, native_Darwin_compilation=False, physical_release_authorized=False,
        new_destructor_or_initializer=False, wrapper_return_logging_boundary_checked=True,
        leak_sanitizer_enabled=False, leak_sanitizer_reason='Managed host task inventory unavailable; endpoint ownership is checked explicitly.',
        variants={}, negative_controls={}, commands=[], dependency_sha256={})
    path = out / 'results.json'
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def write():
        path.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')

    def execute(command, log):
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True, env=env, timeout=120)
        log.write_text(result.stdout + result.stderr)
        report['commands'].append([str(x) for x in command])
        return result

    def variant(label, selected_parts, selected_production, cases, *, sanitized=False, negative=False, windows=False):
        work = out / label
        work.mkdir()
        text = template
        for marker, body in selected_parts.items():
            require(text.count('@' + marker + '@') == 1, 'Exactly one actual C body marker required: ' + marker)
            text = text.replace('@' + marker + '@', body)
        fixture = work / 'check-optional.c'
        fixture.write_text(text)
        unit = copy / prepare.UNIT
        original = unit.read_bytes()
        try:
            unit.write_text(selected_production)
            instrumentation = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                               '-fno-omit-frame-pointer'] if sanitized else []
            include = (copy / 'packages', copy / Path(prepare.RECORD_HEADER).parent,
                copy / prepare.DIRECTORY, copy / 'packages/nvidia-gsp-bootstrap/prospective-attach-failure-witness',
                copy / 'packages/nvidia-os-adapter/upstream/include')
            flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                *instrumentation, *[item for p in include for item in ('-I', str(p))]]
            if windows:
                flags += ['-DRMCFG_FEATURE_PLATFORM_WINDOWS=1']
            objects = []
            for name, source_file in (('fixture', fixture), ('production', unit)):
                obj, dep = work / (name + '.o'), work / (name + '.d')
                built = execute([compiler, *flags, '-MD', '-MF', dep, '-c', source_file, '-o', obj], work / (name + '-compile.log'))
                require(built.returncode == 0, 'Optional-child fixture compilation failed: ' + label + '\n' + built.stderr[-5000:])
                report['dependency_sha256'][label + '-' + name] = dependencies(dep)
                objects.append(obj)
            binary = work / 'check-optional'
            linked = execute([compiler, *instrumentation, *objects, '-o', binary], work / 'link.log')
            require(linked.returncode == 0, 'Optional-child fixture link failed: ' + label + '\n' + linked.stderr[-3000:])
            checks = 0
            for case in cases:
                result = execute([binary, case], work / (case + '.log'))
                if negative:
                    require(result.returncode != 0, 'Actual optional-child mutant survived: ' + label)
                    return dict(killed=True, case=case, returncode=result.returncode, binary_sha256=sha(binary))
                require(result.returncode == 0, 'Optional-child case failed: ' + case + '\n' + result.stderr[-3000:])
                observed = json.loads(result.stdout)
                require(observed['status'] == 'passed' and observed['checks'] > 0, 'No successful CPU observations')
                checks += observed['checks']
            return dict(status='passed', cases=len(cases), checks=checks, binary_sha256=sha(binary),
                        fatal_sanitizers=sanitized, altered_Windows_feature_control=windows)
        finally:
            unit.write_bytes(original)

    write()
    try:
        report['variants']['plain'] = variant('plain', parts, production, CASES)
        report['variants']['fatal-sanitizers'] = variant('fatal-sanitizers', parts, production, CASES, sanitized=True)
        require(report['variants']['plain']['checks'] == report['variants']['fatal-sanitizers']['checks'],
                'Plain and fatal-sanitizer observations differ')
        report['variants']['windows-fallthrough-control'] = variant('windows-fallthrough-control', parts, production,
            ('windows', 'engine86'), windows=True)
        mutants = []

        def mutation(label, part, before, after, case, count=1):
            altered = dict(parts)
            altered[part] = changed(altered[part], before, after, count)
            mutants.append((label, altered, production, case))

        mutation('wrong-class-admitted', 'GPU_BODY', 'classId == classId(KernelNvlink) && instanceID == 0',
                 'instanceID == 0', 'other_class')
        mutation('wrong-instance-admitted', 'GPU_BODY', 'classId == classId(KernelNvlink) && instanceID == 0',
                 'classId == classId(KernelNvlink)', 'other_instance')
        mutation('published-child-admitted', 'GPU_HELPER', '!pGpu || !ppChildPtr || *ppChildPtr != NULL',
                 '!pGpu || !ppChildPtr', 'published')
        mutation('initialized-core-ignored', 'GPU_HELPER', 'if (nvlink_lib_is_initialized()) return NV_OK;',
                 'if (0) return NV_OK;', 'initialized')
        mutation('registry-value-ignored', 'GPU_HELPER', 'if (disabled != 1U) return NV_ERR_INVALID_STATE;',
                 'if (0) return NV_ERR_INVALID_STATE;', 'registry_zero')
        mutation('registry-error-replaced', 'GPU_HELPER',
                 'status = osReadRegistryDwordBase(NULL, "NvLinkDisable", &disabled);\n    if (status != NV_OK) return status;',
                 'status = osReadRegistryDwordBase(NULL, "NvLinkDisable", &disabled);\n    if (status != NV_OK) return NV_ERR_INVALID_STATE;',
                 'registry_error')
        mutation('foreign-nv-admitted', 'RECORD_HELPERS', 'return bound() && nv && nv==LD(&record.nv);',
                 'return bound() && nv;', 'foreign_nv')
        mutation('foreign-master-admitted', 'RECORD_HELPERS', 'return tid && tid==LD(&record.masterThread);',
                 'return tid != 0;', 'foreign_master')
        mutation('ordinary-context-ignored', 'RECORD_HELPERS', 's540Darwin_os_semaphore_may_sleep()',
                 'NV_TRUE', 'irq', 2)
        mutation('epoch-generation-ignored', 'RECORD_HELPERS', 'globalEpoch.generation==LD(&record.generation) &&',
                 'NV_TRUE &&', 'generation_mismatch')
        for label, before, after, case in (
            ('phase-ignored', 'LD(&record.phase) != S540_FIRST_OP ||', 'NV_FALSE ||', 'phase'),
            ('original-inflight-ignored', '!LD(&record.originalInFlight) || LD(&record.originalExitReady) ||',
             'LD(&record.originalExitReady) ||', 'not_inflight'),
            ('original-exit-ignored', '!LD(&record.originalInFlight) || LD(&record.originalExitReady) ||',
             '!LD(&record.originalInFlight) ||', 'exit_ready'),
            ('original-return-ignored', '        LD(&record.originalReturned) ||', '        NV_FALSE ||', 'already_returned'),
            ('global-validation-ignored', '!LD(&globalEpoch.validated) || !LD(&globalEpoch.originalReturned) ||',
             '!LD(&globalEpoch.originalReturned) ||', 'global_unvalidated')):
            mutation(label, 'RECORD_PROBES', before, after, case, 2 if label == 'global-validation-ignored' else 1)
        mutation('published-unsupported-normalized', 'GPU_BODY',
                 '        // Retain the published child slot and its parent ownership.\n        return status;',
                 '        // Retain the published child slot and its parent ownership.\n        return NV_OK;', 'engine86')
        mutation('early-read-admitted', 'RECORD_PROBES',
                 'LD(&record.originalInFlight) || !LD(&record.originalExitReady) ||\n        !LD(&record.originalReturned) ||',
                 'NV_FALSE ||', 'absence')
        mutation('absence-log-forged', 'CONTEXT_LOGGER', 'absent.format, absent.bytes, absent.absent, absent.classId,',
                 'absent.format, absent.bytes, 0U, absent.classId,', 'log_absent')
        for label, before, after, case in (
            ('cancel-format-ignored', 'cancellation.format != 1U || !cancellation.bound ||', '!cancellation.bound ||', 'cancel_format'),
            ('cancel-bound-ignored', 'cancellation.format != 1U || !cancellation.bound ||', 'cancellation.format != 1U ||', 'cancel_bound'),
            ('cancel-generation-ignored', 'cancellation.generation != LD(&record.cancelToken) ||', 'NV_FALSE ||', 'cancel_output_generation'),
            ('cancel-owner-ignored', 'cancellation.ownerThread != LD(&record.masterThread) ||', 'NV_FALSE ||', 'cancel_owner'),
            ('cancel-phase-ignored', 'cancellation.phase != S540_GSP_CANCEL_OPERATION', 'NV_FALSE', 'cancel_idle'),
            ('cancel-publication-ignored', 'if (cancellation.publicationInFlight) return NV_ERR_NOT_READY;', 'if (0) return NV_ERR_NOT_READY;', 'cancel_publication'),
            ('cancel-revocation-ignored', 'if (cancellation.revoked) return NV_ERR_OPERATION_ABORTED;', 'if (0) return NV_ERR_OPERATION_ABORTED;', 'cancel_revoked')):
            mutation(label, 'RECORD_PROBES', before, after, case)
        mutation('cancel-snapshot-mutates-counter', 'CANCELLATION_SNAPSHOT',
                 'result.checks = __atomic_load_n(&slot.checks, __ATOMIC_RELAXED);',
                 'result.checks = __atomic_fetch_add(&slot.checks, 1U, __ATOMIC_RELAXED);', 'absence')
        mutation('cancel-unstable-word-admitted', 'CANCELLATION_SNAPSHOT',
                 'if (word() != value) return NV_ERR_BUSY_RETRY;', 'if (0) return NV_ERR_BUSY_RETRY;', 'cancel_race')
        mutants.append(('second-authority-probe-omitted', parts,
            changed(production, 'status = s540FirstTxnOptionalNvlinkActive(nv, &checkedGeneration);',
                    'checkedGeneration = generation; status = NV_OK;'), 'reserve_failure'))
        mutants.append(('first-generation-lost', parts,
            changed(production, 'if (!generation || checkedGeneration != generation) return NV_ERR_INVALID_STATE;',
                    'if (!generation) return NV_ERR_INVALID_STATE;'), 'reserve_generation'))
        for label, selected, unit, case in mutants:
            report['negative_controls'][label] = variant(label, selected, unit, (case,), negative=True)
        for name, digest in helper_hashes.items():
            require(sha(ROOT / name) == digest, 'Bound optional-child helper changed during controls: ' + name)
        for bindings in report['dependency_sha256'].values():
            for name, digest in bindings.items():
                if name != str((copy / prepare.UNIT).resolve()):
                    require(sha(name) == digest, 'Bound header or fixture changed during controls: ' + name)
        report['status'] = 'passed-actual-optional-child-record-and-diagnostic-CPU-controls'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input-source', 'input-project', 'output', 'cc'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('composed-source', 'composed-project'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--host-control', action='store_true')
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], variants=result['variants'],
        mutants_killed=len(result['negative_controls']))))
