#!/usr/bin/env python3
"""Execute exact queue/page-size/original OS allocation C bodies with CPU endpoints."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import resource
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHARED = ROOT / 'packages/nvidia-gsp-bootstrap/cancellation/prepare_wait_candidates.py'
SHARED_SHA256 = 'f8e0099f904b5e1a756e628985ef991c9a09475214f52a38c921ccc5df6de471'
sys.path.insert(0, str(SHARED.parent))
from prepare_wait_candidates import function_span


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text, name):
    first, last = function_span(text, name)
    start = text.rfind('\n', 0, first) + 1
    if not text[start:first].strip():
        previous = text.rfind('\n', 0, start - 1) + 1
        require(re.fullmatch(r'(?:static )?(?:void|NV_STATUS|NvBool|NvU64)\s*',
                            text[previous:start]), 'Unknown exact original return declaration: ' + name)
        start = previous
    return text[start:last]


def module():
    spec = importlib.util.spec_from_file_location('s540_gsp_base_pages', HERE / 'prepare.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def macro(text, name):
    found = re.findall(r'^#define\s+' + re.escape(name) + r'\b(?:\([^\n]*?\))?[^\n]*$', text, re.M)
    require(len(found) == 1, 'One exact pinned macro required: ' + name)
    return found[0]


def fixture(source, queue):
    sdk = source / 'src/common/sdk/nvidia/inc'
    files = {
        'memdesc': source / 'src/nvidia/src/kernel/gpu/mem_mgr/mem_desc.c',
        'os': source / 'src/nvidia/arch/nvalloc/unix/src/os.c',
        'desc_header': source / 'src/nvidia/generated/g_mem_desc_nvoc.h',
        'queue_header': source / 'src/nvidia/inc/kernel/gpu/gsp/message_queue_priv.h',
        'queue_public': source / 'src/nvidia/inc/kernel/gpu/gsp/message_queue.h',
        'prelude': source / 'src/nvidia/inc/kernel/core/prelude.h',
        'nv_header': source / 'src/nvidia/arch/nvalloc/unix/include/nv.h',
        'registry': source / 'src/nvidia/interface/nvrm_registry.h',
    }
    raw = {name: path.read_text() for name, path in files.items()}
    headers = [sdk / name for name in ('nvtypes.h', 'nvstatus.h', 'nvmisc.h',
                                      'nv-kernel-interface-api.h')]
    headers += [source / 'src/nvidia/inc/kernel/gpu/mem_mgr/rm_page_size.h',
                source / 'src/nvidia/inc/kernel/os/nv_memory_type.h']
    constants = []
    for names, key in (
        (('MEMDESC_FLAGS_NONE', 'MEMDESC_FLAGS_KERNEL_MODE', 'MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY',
          'MEMDESC_FLAGS_PHYSICALLY_CONTIGUOUS', 'MEMDESC_FLAGS_GUEST_ALLOCATED',
          'MEMDESC_FLAGS_MEMORY_TYPE_DISPLAY_NISO', 'MEMDESC_FLAGS_ALLOC_32BIT_ADDRESSABLE',
          'memdescTagAlloc', 'ADDR_SYSMEM', 'AT_CPU', 'AT_GPU', 'AT_VARIANT'), 'desc_header'),
        (('RM_ALIGN_UP', 'RM_PAGE_ALIGN_UP'), 'prelude'),
        (('NV_RM_PAGE_SHIFT', 'NV_RM_PAGE_SIZE'), 'nv_header'),
        (('NV_REG_STR_RM_GSP_STATUS_QUEUE_SIZE',), 'registry'),
        (('RPC_TASK_RM_QUEUE_IDX', 'RPC_QUEUE_COUNT'), 'queue_public')):
        constants += [macro(raw[key], name) for name in names]
    tag = re.findall(r'^\s*(NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_58\s*=\s*\d+U),', raw['desc_header'], re.M)
    require(len(tag) == 1, 'One actual allocation tag value required')
    constants.append('enum { ' + tag[0] + ' };')
    abi = []
    for name in ('nv_alloc_pages', 'nv_alias_pages'):
        declarations = re.findall(r'^NV_STATUS\s+NV_API_CALL\s+' + name +
                                  r'\s*(\([^\n]+\));$', raw['nv_header'], re.M)
        require(len(declarations) == 1, 'One exact original OS allocation ABI required: ' + name)
        typedef = 'fixture_' + name + '_abi'
        abi.append('typedef NV_STATUS (NV_API_CALL *' + typedef + ')' + declarations[0] + ';')
        abi.append('_Static_assert(__builtin_types_compatible_p(__typeof__(&' + name +
                   '),' + typedef + '), "Actual original OS allocation endpoint ABI");')
    start = raw['queue_header'].index('typedef struct GSP_MSG_QUEUE_ENCRYPTION_TAG')
    stop = raw['queue_header'].index('\nstatic NV_INLINE', start)
    queue_structs = raw['queue_header'][start:stop]
    md_names = ('memdescGetContiguity', 'memdescGetPageSize', 'memdescSetPageSize',
                'memdescGetAdjustedPageSize')
    os_names = ('osGetPagesInfo', 'osAllocPagesInternal')
    queue_names = ('_getMsgQueueParams', '_gspMsgQueueCleanup', 'GspMsgQueuesCleanup', 'GspMsgQueuesInit')
    bodies = {
        'MEMDESC_BODIES': '\n\n'.join(function(raw['memdesc'], name) for name in md_names),
        'OS_BODIES': '\n\n'.join(function(raw['os'], name) for name in os_names),
        'QUEUE_BODIES': '\n\n'.join(function(queue, name) for name in queue_names),
    }
    tokens = dict(HEADERS='\n'.join('#include "' + str(p) + '"' for p in headers),
                  CONSTANTS='\n'.join(constants), QUEUE_STRUCTS=queue_structs,
                  ABI_ASSERTIONS='\n'.join(abi), **bodies)
    text = (HERE / 'tests/check_queue.c.inc').read_text()
    for name, value in tokens.items():
        marker = '@' + name + '@'
        require(text.count(marker) == 1, 'Exact queue fixture marker required: ' + name)
        text = text.replace(marker, value)
    inputs = {str(p): sha(p) for p in (*files.values(), *headers, SHARED)}
    extracted = {name: hashlib.sha256(body.encode()).hexdigest() for name, body in bodies.items()}
    return text, inputs, extracted, sdk


def dependencies(path):
    return {str(Path(name).resolve(strict=True)): sha(Path(name).resolve(strict=True))
            for name in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1])}


def run(args):
    require(args.host_control, 'Explicit --host-control is required for CPU-only resource endpoints')
    require(sha(SHARED) == SHARED_SHA256, 'Reviewed exact shared function-span parser changed')
    source = args.input_source.resolve(strict=True)
    output = args.output.absolute()
    require(not output.exists(), 'Fresh GSP base-page CPU control output required')
    prepare = module()
    original = {name: (source / name).read_text() for name in prepare.ORIGINAL_INPUTS}
    selected = prepare.original_transforms(original)
    if args.composed_source:
        composed = args.composed_source.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected.items()),
                'Composed queue differs from the exact base-page transform')
    refused = []
    for values in ({}, dict(original, extra='unreviewed'),
                   dict(original, **{prepare.QUEUE: original[prepare.QUEUE] + '\n'})):
        try:
            prepare.original_transforms(values)
        except ValueError:
            refused.append('missing-extra-or-rehashed-source-refused')
        else:
            raise ValueError('An altered GSP queue source was accepted')
    helpers = {str(p.relative_to(ROOT)): sha(p) for p in
               (HERE / 'prepare.py', *(HERE / p for p in prepare.SOURCE_FILES))}
    output.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    compiler = args.cc.expanduser().absolute()
    compiler_target = compiler.resolve(strict=True)
    require(compiler_target.is_file() and os.access(compiler, os.X_OK), 'Executable C compiler required')
    variants, commands = {}, []
    endpoint_inputs = {}
    extracted_bodies = {}

    def execute(label, queue, baseline=False, sanitized=False, negative=False):
        text, inputs, extracted, sdk = fixture(source, queue)
        endpoint_inputs.update(inputs)
        extracted_bodies[label] = extracted
        path = output / (label + '.c')
        path.write_text(text)
        binary = output / label
        dep = output / (label + '.d')
        argv = [str(compiler), '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-function', '-Wno-unused-parameter',
                '-Wno-gnu-variable-sized-type-not-at-end', '-I' + str(sdk),
                '-DBASELINE=' + str(int(baseline))]
        if sanitized:
            argv += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer']
        argv += ['-MD', '-MF', str(dep), str(path), '-o', str(binary)]
        built = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        (output / (label + '-compile.log')).write_text(built.stdout + built.stderr)
        require(built.returncode == 0, 'Actual GSP queue C bodies failed to compile: ' +
                label + '\n' + built.stderr[-7000:])
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1')
        result = subprocess.run([str(binary)], capture_output=True, text=True, env=env, timeout=30)
        (output / (label + '-run.log')).write_text(result.stdout + result.stderr)
        row = dict(source_sha256=sha(path), binary_sha256=sha(binary), returncode=result.returncode,
                   dependency_sha256=dependencies(dep), sanitized=sanitized, negative_control=negative)
        if negative:
            require(result.returncode != 0, 'Actual GSP queue mutant survived: ' + label)
            row['killed'] = True
        else:
            require(result.returncode == 0, 'Actual GSP queue CPU case failed: ' +
                    label + '\n' + result.stderr[-3500:])
            row.update(json.loads(result.stdout))
        variants[label] = row
        commands.append(argv)

    for baseline, queue in ((True, original[prepare.QUEUE]), (False, selected[prepare.QUEUE])):
        name = 'baseline' if baseline else 'selected'
        execute(name, queue, baseline=baseline)
        execute(name + '_sanitized', queue, baseline=baseline, sanitized=True)
        require(variants[name]['checks'] == variants[name + '_sanitized']['checks'],
                'Plain and sanitized queue controls differ')
    queue = selected[prepare.QUEUE]
    line = '    memdescSetPageSize(pMQCollection->pSharedMemDesc, AT_GPU, RM_PAGE_SIZE);'
    allocation = '''    memdescTagAlloc(nvStatus, NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_58,
                    pMQCollection->pSharedMemDesc);'''
    mutations = {
        'request_huge_pages_again': (line, line.replace('RM_PAGE_SIZE);', 'RM_PAGE_SIZE_HUGE);')),
        'omit_explicit_page_selection': (line, '    (void)pMQCollection->pSharedMemDesc;'),
        'retry_same_failed_base_pages': (allocation, allocation + '''
    if (nvStatus == NV_ERR_NO_MEMORY) {
        memdescTagAlloc(nvStatus, NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_58,
                        pMQCollection->pSharedMemDesc);
    }'''),
        'reinterpret_unsupported_as_no_memory': (allocation, allocation +
            '\n    if (nvStatus == NV_ERR_NOT_SUPPORTED) nvStatus = NV_ERR_NO_MEMORY;'),
        'omit_page_table_own_PTE': (
            '    numPtes += NV_DIV_AND_CEIL(numPtes * sizeof(RmPhysAddr), RM_PAGE_SIZE);',
            '    numPtes += 0;'),
        'use_huge_PTE_stride': ('                    RM_PAGE_SIZE,               // stride',
                               '                    RM_PAGE_SIZE_HUGE,          // stride'),
        'drop_unprotected_request': ('        flags |= MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY;',
                                    '        (void)flags;'),
        'hide_allocation_failure': ('    NV_ASSERT_OK_OR_GOTO(nvStatus, nvStatus, error_ret);',
                                   '    NV_ASSERT_OK_OR_GOTO(nvStatus, NV_OK, error_ret);'),
        'shrink_command_queue': ('const NvLength defaultCommandQueueSize = 0x40000;',
                                'const NvLength defaultCommandQueueSize = 0x20000;'),
        'omit_shared_page_table_bytes': ('sharedBufSize = pMQCollection->pageTableSize +',
                                         'sharedBufSize = 0 +'),
    }
    for name, (before, after) in mutations.items():
        require(queue.count(before) == 1, 'One exact original mutation anchor required: ' + name)
        execute('mutant_' + name, queue.replace(before, after), negative=True)
    require(all(sha(Path(name)) == digest for name, digest in endpoint_inputs.items()),
            'An actual original body/header input changed during CPU controls')
    require(all((source / name).read_text() == text for name, text in original.items()),
            'The exact B6 queue input changed during CPU controls')
    require({str(p.relative_to(ROOT)): sha(p) for p in
             (HERE / 'prepare.py', *(HERE / p for p in prepare.SOURCE_FILES))} == helpers,
            'The queue transform/helper changed during CPU controls')
    report = dict(format=1, status='passed-actual-GSP-base-page-queue-and-OS-allocation-controls',
        exact_input_sha256={k: hashlib.sha256(v.encode()).hexdigest() for k, v in original.items()},
        exact_output_sha256={k: hashlib.sha256(v.encode()).hexdigest() for k, v in selected.items()},
        source_file_sha256=helpers, original_input_sha256=endpoint_inputs,
        extracted_body_sha256=extracted_bodies, exact_source_refusals=refused,
        variants=variants, commands=commands, compiler_invocation_path=str(compiler),
        compiler_resolved_path=str(compiler_target), compiler_sha256=sha(compiler_target),
        actual_functions=['_getMsgQueueParams', 'GspMsgQueuesInit', '_gspMsgQueueCleanup',
            'GspMsgQueuesCleanup', 'memdescGetContiguity', 'memdescGetPageSize',
            'memdescSetPageSize', 'memdescGetAdjustedPageSize', 'osGetPagesInfo',
            'osAllocPagesInternal'],
        modeled_endpoints=['resource allocation/destruction/mapping', 'NVOC properties',
            'strict 4 KiB OS allocation', 'separately owned unprotected-host admission',
            'message-queue protocol endpoint'],
        default_geometry=dict(command_bytes=262144, status_bytes=262144,
            page_table_bytes=4096, shared_bytes=528384, base_pages=129),
        sanitizer_policy=dict(address_and_undefined_fatal=True, leak_sanitizer_enabled=False,
            leak_sanitizer_reason='Disabled on the traced host, not reported as passed.'),
        actual_original_bodies_executed_in_CPU_fixture=True,
        full_original_adapter_initialization_executed=False, IOKit_executed=False,
        native_Darwin_compilation=False, GPU_execution=False,
        whole_DMA_stop_proven=False, system_security_changed=False, github_workflows_started=0)
    (output / 'results.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-source', type=Path, required=True)
    parser.add_argument('--composed-source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], cases=result['variants']['selected']['cases'],
        checks=result['variants']['selected']['checks'],
        sanitized_checks=result['variants']['selected_sanitized']['checks'],
        mutants_killed=sum(bool(v.get('killed')) for v in result['variants'].values()))))
