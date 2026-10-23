#!/usr/bin/env python3
"""Observe genuine selected lock ownership on the immutable first RM master."""
from pathlib import Path
import hashlib
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIGINAL = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original/S540NvidiaGspFirstTransactionOriginal.c'
INPUTS = (ORIGINAL,)
ORIGINAL_INPUTS = ()
BASE_SHA256 = {ORIGINAL: '745606a08523de91ab8408d3e438a3ba7922f2f204f90a84ea2a879d8dedfa75'}
COMPANIONS = {}
PROJECT_UNITS = ()
EXPORTS = {}
# The original-C compiler profile already defines the sealed no-legacy profile.
# Do not duplicate it as a per-source macro: the strict command verifier requires
# each selected definition to have one actual owner in the command line.
COMPILE_DEFINITIONS = {}
INCLUDE_DIRECTORIES = ()
SOURCE_FILES = ('check.py', 'tests/check_locks.c', 'SOURCE-CONTRACT.json')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact first-lock source anchor changed: ' + before[:100])
    return text.replace(before, after)


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exact first-lock bridge input required')
    text = values[ORIGINAL]
    if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[ORIGINAL]:
        raise ValueError('Reviewed first-lock bridge source changed')
    text = once(text, '#include "core/locks.h"',
        '#include "core/locks.h"\n#include "core/system.h"\n#include "S540ProspectiveRmLockOwnership.h"')
    begin, end = function_span(text, 's540FirstTxnOriginalLocksReleased')
    text = text[:begin] + (HERE / 'locks-released.c.inc').read_text().rstrip() + text[end:]
    return {ORIGINAL: text}
