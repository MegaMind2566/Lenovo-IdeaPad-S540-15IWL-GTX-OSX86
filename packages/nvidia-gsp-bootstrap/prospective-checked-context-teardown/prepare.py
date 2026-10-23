#!/usr/bin/env python3
"""Preserve checked original teardown status in the retained Context caller."""
from pathlib import Path
import hashlib

HERE = Path(__file__).resolve().parent
PREFIX = 'packages/nvidia-gsp-bootstrap/prospective-checked-context-teardown'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
INPUTS = (CONTEXT,)
ORIGINAL_INPUTS = ()
BASE_SHA256 = {CONTEXT: '3823304a498b872ee3c8df62d4e7b6880fb7f8cbd44203662dd2099e213b5cc5'}
COMPANIONS = {PREFIX + '/S540NvidiaCheckedContextTeardown.h': HERE / 'S540NvidiaCheckedContextTeardown.h'}
PROJECT_UNITS = ()
EXPORTS = {}
COMPILE_DEFINITIONS = {}
INCLUDE_DIRECTORIES = (PREFIX,)
SOURCE_FILES = ('check.py', 'tests/check_context.c', 'SOURCE-CONTRACT.json')


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact checked Context source anchor changed: ' + before[:100])
    return text.replace(before, after)


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exact checked Context input set required')
    text = values[CONTEXT]
    if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[CONTEXT]:
        raise ValueError('Reviewed IRQ-installed Context source changed')
    text = once(text, '#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n#include "../prospective-checked-context-teardown/S540NvidiaCheckedContextTeardown.h"')
    for operation in ('Disable', 'Shutdown'):
        old = '    rm_' + operation.lower() + '_adapter(&context->stacks[MAIN], &context->nv);'
        new = ('    NV_STATUS status = s540Rm' + operation + 'AdapterChecked(&context->stacks[MAIN], &context->nv);\n'
               '    if (status != NV_OK) { context->state.quarantined = NV_TRUE; return status; }')
        text = once(text, old, new)
    return {CONTEXT: text}
