#!/usr/bin/env python3
"""Request real Darwin base pages and preserve the GSP retry status."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-gsp-boot-contracts'
KERNEL_GSP = 'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c'
GPU_MEMORY = 'src/nvidia/src/kernel/gpu/mem_mgr/mem_desc.c'
OS = 'src/nvidia/arch/nvalloc/unix/src/os.c'
TIMER = 'src/nvidia/src/kernel/core/thread_state.c'
INPUTS = ()
ORIGINAL_INPUTS = (KERNEL_GSP,)
COMPANIONS = {}
PROJECT_UNITS = ()
EXPORTS = {}
INCLUDE_DIRECTORIES = ()
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'README.md',
                'check.py', 'tests/check_boot.c.inc')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    match = re.fullmatch(r'([0-9a-f]{64})  ' + re.escape(KERNEL_GSP) + r'\n',
                        (HERE / 'BASE-SHA256SUMS').read_text())
    if match is None:
        raise ValueError('The exact preceding GSP bootstrap source hash is required')
    return {KERNEL_GSP: match[1]}


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('The exact GSP boot source anchor changed: ' + before[:110])
    return text.replace(before, after)


def original_transforms(values):
    if set(values) != set(ORIGINAL_INPUTS):
        raise ValueError('Exactly the preceding kernel_gsp.c source is required')
    text = values[KERNEL_GSP]
    if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[KERNEL_GSP]:
        raise ValueError('The preceding GSP bootstrap source identity changed')
    first, last = function_span(text, 'kgspCreateRadix3_IMPL')
    body = once(text[first:last],
        '    memdescSetPageSize(*ppMemdescRadix3, AT_GPU, RM_PAGE_SIZE_HUGE);',
        '    // The selected Darwin backend supplies real 4 KiB base pages.\n'
        '    // Select that geometry before allocation; never relabel a 2 MiB\n'
        '    // request or erase its unsupported status in the OS bridge.\n'
        '    memdescSetPageSize(*ppMemdescRadix3, AT_GPU, RM_PAGE_SIZE);')
    text = text[:first] + body + text[last:]
    first, last = function_span(text, 'kgspInitRm_IMPL')
    before = '''    do
    {
        status = s540GspCancellationCheckGpu(pGpu);
        if (status != NV_OK) goto done;
        // Reset the thread state timeout after failed attempts to prevent premature timeouts.
        if (status != NV_OK)
            threadStateResetTimeout(pGpu);'''
    after = '''    do
    {
        const NV_STATUS cancelStatus = s540GspCancellationCheckGpu(pGpu);
        if (cancelStatus != NV_OK)
        {
            status = cancelStatus;
            goto done;
        }
        // Reset the thread state timeout after failed attempts to prevent premature timeouts.
        if (status != NV_OK)
            threadStateResetTimeout(pGpu);'''
    body = once(text[first:last], before, after)
    return {KERNEL_GSP: text[:first] + body + text[last:]}
