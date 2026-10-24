#!/usr/bin/env python3
"""Use the reviewed Darwin backend's real base pages for the GSP shared queue."""
from pathlib import Path
import hashlib
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-gsp-base-pages'
QUEUE = 'src/nvidia/src/kernel/gpu/gsp/message_queue_cpu.c'
INPUTS = ()
ORIGINAL_INPUTS = (QUEUE,)
COMPANIONS = {}
PROJECT_UNITS = ()
EXPORTS = {}
INCLUDE_DIRECTORIES = ()
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'check.py',
                'tests/check_queue.c.inc')


def input_hashes():
    match = re.fullmatch(r'([0-9a-f]{64})  ' + re.escape(QUEUE) + r'\n',
                        (HERE / 'BASE-SHA256SUMS').read_text())
    if match is None:
        raise ValueError('The exact B6 GSP queue source hash is required')
    return {QUEUE: match[1]}


BASE_SHA256 = input_hashes()
BEFORE = '''    memdescSetPageSize(pMQCollection->pSharedMemDesc, AT_GPU, RM_PAGE_SIZE_HUGE);
    memdescTagAlloc(nvStatus, NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_58,
                    pMQCollection->pSharedMemDesc);

    if (nvStatus == NV_ERR_NO_MEMORY)
    {
        // TODO: Bug 5299603
        NV_PRINTF(LEVEL_ERROR, "Allocation failed with big page size, retrying with default page size\\n");
        memdescSetPageSize(pMQCollection->pSharedMemDesc, AT_GPU, RM_PAGE_SIZE);
        memdescTagAlloc(nvStatus, NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_58,
                        pMQCollection->pSharedMemDesc);
    }
'''
AFTER = '''    // The selected Darwin backend allocates real 4 KiB base pages. Request
    // that granularity before allocation; no 2 MiB allocation is claimed.
    // A failed base-page allocation keeps its original status and cleanup path.
    memdescSetPageSize(pMQCollection->pSharedMemDesc, AT_GPU, RM_PAGE_SIZE);
    memdescTagAlloc(nvStatus, NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_58,
                    pMQCollection->pSharedMemDesc);
'''


def original_transforms(values):
    if set(values) != set(ORIGINAL_INPUTS):
        raise ValueError('Exactly one reviewed B6 GSP queue source is required')
    text = values[QUEUE]
    if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[QUEUE]:
        raise ValueError('The frozen B6 GSP queue source changed')
    if text.count(BEFORE) != 1:
        raise ValueError('The exact huge-page-first GSP queue allocation anchor changed')
    return {QUEUE: text.replace(BEFORE, AFTER)}
