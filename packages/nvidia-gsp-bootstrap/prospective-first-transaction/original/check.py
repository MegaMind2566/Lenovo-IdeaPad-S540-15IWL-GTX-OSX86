#!/usr/bin/env python3
"""Run actual-header body controls; authoritative execution defaults to Intel macOS."""
from __future__ import annotations
import json
from pathlib import Path
from common import HERE, REPO, execution, original, parser, resolve_arguments, sha, write_json
from prepare_controls import prepare_controls

EXPECTED = {'component': 'nvidia-first-transaction-original-bodies', 'checks': 74,
    'actual_original_wrapper': True, 'actual_original_api_lock_bodies': 4,
    'real_native_lock_tokens': True, 'original_gpu_init_endpoint_fixture': True,
    'first_transaction_record_endpoint_fixture': True, 'actual_service_counter_probes': True,
    'actual_nvoc_bodies': 4, 'actual_timer_ctor_body': True,
    'full_lock_capability_refused': True, 'original_entry_admission': False}

def run(args) -> dict:
    args, identity = resolve_arguments(args)
    prepared = prepare_controls(args.upstream, args.v3_root, args.output)
    services = [execution.SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp')
                for name in execution.SERVICE_NAMES]
    old_pair = execution.crypto.compiler_pair
    old_flags = original.original_bridge_flags
    # Reuse the established execution/binary/codesign/sanitizer helper while
    # selecting explicit compilers and the already verified full V3 headers.
    def pair(host_control):
        if host_control != args.host_control:
            raise ValueError('Execution mode changed inside a control.')
        return [str(args.cc)], [str(args.cxx)]
    def flags(upstream, output, compiler, namespace, **unused):
        values = old_flags(upstream, output, compiler, namespace)
        root, base = str(args.upstream), str(prepared['base_source'])
        return [base + value[len(root):] if value.startswith(root + '/') else value for value in values]
    execution.crypto.compiler_pair, original.original_bridge_flags = pair, flags
    try:
        controls = execution.original_header_case(args.output / 'controls', 'first-original',
            args.upstream, args.namespace,
            [HERE / 'S540NvidiaGspFirstTransactionOriginal.c', HERE / 'check_wrapper_bodies.c',
             HERE / 'check_nvoc_bodies.c',
             REPO / 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c',
             REPO / 'packages/nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c',
             REPO / 'packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c'],
            [*services, REPO / 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp', HERE / 'check_native.cpp'],
            EXPECTED, host_control=args.host_control, dead_strip=True,
            extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                '-I', str(args.output), '-I', str(HERE),
                '-I', str(REPO / 'packages/nvidia-gsp-bootstrap/cancellation'),
                '-I', str(REPO / 'packages/nvidia-device-transport/src')],
            extra_cpp_flags=['-I', str(HERE)])
    finally:
        execution.crypto.compiler_pair, original.original_bridge_flags = old_pair, old_flags
    report = {'format': 1, 'status': 'passed-isolated-original-body-controls', **identity,
        'controls': controls, 'source_contract_sha256': prepared['manifest']['source_contract_sha256'],
        'namespace_sha256': sha(args.namespace.read_bytes()),
        'v3_full_inventory_verified': True, 'complete_extracted_bodies': 11,
        'original_functions_and_wrappers': 9, 'new_source_resident_helpers': 2,
        'full_lock_capability_refused': True, 'production_candidate_allowed': False,
        'kernel_execution': 'not_tested', 'gpu_access': False, 'original_entry_admission': False}
    write_json(args.output / 'wrapper-results.json', report)
    return report

def main():
    result = run(parser(__doc__).parse_args())
    print(json.dumps({'status': result['status'], 'checks_per_variant': 74,
        'authoritative_darwin_execution': result['authoritative_darwin_execution'],
        'original_entry_admission': False}))

if __name__ == '__main__':
    main()
