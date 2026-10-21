#!/usr/bin/env python3
"""Execute actual transformed Owner/Session and real PM/cancellation services.

Provider, device addresses and RM bodies are explicit CPU fixtures/tripwires.
The permanent case intentionally keeps its actual worker and resources alive.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import prepare


def transformed_test(text):
    text = prepare.once(text,
        'struct ResourceFixture { bool active = false, failStop = false, policyAvailable = true; };',
        'struct ResourceFixture { bool active = false, failStop = false, policyAvailable = true;\n'
        '    NvU32 released = 0, unmapped = 0; };\n'
        'struct PageResource { NvU8 *bytes; NvU32 pages; };')
    text = prepare.once(text,
        'NV_STATUS allocate(void *, NvU32, bool, NvU32, void **, NvU8 **) { std::abort(); }',
        '''NV_STATUS allocate(void *, NvU32 pages, bool, NvU32, void **out, NvU8 **host) {
    auto *resource = new PageResource{static_cast<NvU8 *>(std::calloc(pages, kPageBytes)), pages};
    if(!resource->bytes){delete resource;return NV_ERR_NO_MEMORY;}
    *out=resource;*host=resource->bytes;return NV_OK;
}''')
    text = prepare.once(text,
        'NV_STATUS page(void *, void *, NvU32, bool, NvU64 &) { std::abort(); }',
        'NV_STATUS page(void *, void *, NvU32 index, bool, NvU64 &out) {\n'
        '    out=0x400000ULL+NvU64(index)*kPageBytes;return NV_OK;\n}')
    text = prepare.once(text,
        'NV_STATUS map(void *, void *, NvU32) { std::abort(); }',
        'NV_STATUS map(void *, void *, NvU32) { return NV_OK; }')
    text = prepare.once(text,
        'NV_STATUS allocationOperation(void *, void *) { std::abort(); }',
        '''NV_STATUS unmapAllocation(void *opaque, void *) {
    ++static_cast<ResourceFixture *>(opaque)->unmapped;return NV_OK;
}
NV_STATUS releaseAllocation(void *opaque, void *allocation) {
    auto *resource=static_cast<PageResource *>(allocation);
    ++static_cast<ResourceFixture *>(opaque)->released;
    std::free(resource->bytes);delete resource;return NV_OK;
}''')
    text = prepare.once(text, 'allocate, page, map, allocationOperation, allocationOperation, install,',
        'allocate, page, map, unmapAllocation, releaseAllocation, install,')
    text = prepare.once(text, 'NV_STATUS inspect(void *, void *) { return NV_OK; }',
        (HERE/'tests/page-fixture.cpp.inc').read_text()+'\nNV_STATUS inspect(void *, void *) { return NV_OK; }')
    text = prepare.once(text, '    std::printf("{\\"format\\":1,',
        (HERE/'tests/retained-case.cpp.inc').read_text()+'\n    std::printf("{\\"format\\":1,')
    text = prepare.once(text, '"\\"original_rm_executed\\":false,\\"firmware_loaded\\":false,',
        '"\\"permanent_session_retained\\":true,\\"fixed_pm_deadline_verified\\":true,"\n'
        '        "\\"original_rm_executed\\":false,\\"firmware_loaded\\":false,')
    return text


def check(args):
    if not args.host_control:
        raise ValueError('This CPU runner requires explicit --host-control; target execution is separate')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT) or ROOT.is_relative_to(output):
        raise ValueError('Fresh output separate from package/project source required')
    output.mkdir(parents=True)
    project = output/'project'
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns('.git', 'build', '__pycache__'))
    inputs = {name: prepare.sha(ROOT/name) for name in prepare.INPUTS}
    values = {name: (project/name).read_text() for name in prepare.INPUTS}
    changed = prepare.transforms(values)
    for name, value in changed.items():
        (project/name).write_text(value)
    test = project/'packages/nvidia-gsp-bootstrap/tests/check_bootstrap_native.cpp'
    test.write_text(transformed_test(test.read_text()))
    loader = (ROOT/prepare.LOADER).read_text()
    guarded = prepare.loader_transform(loader)
    module_stop = guarded.index('kern_return_t s540ProspectiveModuleStopBackend(void)')
    control_stop = guarded.index('void S540ProspectiveLoaderControl::stop(IOService *provider)')
    if not (guarded.index('s540GspDiagnosticLifetimePinCount()', module_stop) <
            guarded.index('s540ProspectiveBeginStop(&state)', module_stop) and
            guarded.index('s540GspDiagnosticLifetimePinCount()', control_stop) <
            guarded.index('s540ProspectiveServiceGone(&state)', control_stop)):
        raise ValueError('Actual loader lifetime guards must precede destructive state transitions')
    (output/'guarded-loader.cpp').write_text(guarded)
    sys.path.insert(0, str(project/'builders'))
    import check_nvidia_execution as checks
    os.environ['CC'] = str(args.cc.resolve(strict=True))
    os.environ['CXX'] = str(args.cxx.resolve(strict=True))
    os.environ['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
    os.environ['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    # Reuse the real production source list, selecting this successor test;
    # changing only the expected fields avoids laundering old case counts.
    original_case = checks.original_header_case
    def successor_case(*positional, **keywords):
        positional = list(positional)
        positional[6] = {key:value for key,value in positional[6].items() if key != 'checks'}
        positional[6].update(permanent_session_retained=True, fixed_pm_deadline_verified=True)
        return original_case(*positional, **keywords)
    checks.original_header_case = successor_case
    results = checks.bootstrap_case(output/'controls', args.upstream, args.namespace,
        args.assets, host_control=True)
    if any(prepare.sha(ROOT/name) != digest for name,digest in inputs.items()):
        raise ValueError('Baseline source changed during controls')
    report = {'format': 1, 'component': 'prospective-session-lifetime-closure', 'status':'passed',
        'actual_owner_session_controls': results, 'input_sha256':inputs,
        'changed_source_sha256': {name:prepare.sha(project/name) for name in changed},
        'test_source_sha256':prepare.sha(test), 'guarded_loader_sha256':prepare.sha(output/'guarded-loader.cpp'),
        'loader_stop_guards_source_order_verified':True, 'native_provider_and_dma_endpoints_are_fixtures':True,
        'leak_sanitizer_disabled_for_intentionally_retained_worker':True,
        'original_rm_executed':False, 'gpu_initialized':False, 'hardware_admission':False,
        'pm_30_second_shutdown_bound_proven':False, 'physical_reclamation_authorized':False}
    (output/'session-lifetime-controls.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'status':'passed','checks':{k:v['checks'] for k,v in results.items()},
                      'original_entry_admission':False,'pm_deadline_closed':False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--namespace', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--cxx', type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    check(parser.parse_args())
