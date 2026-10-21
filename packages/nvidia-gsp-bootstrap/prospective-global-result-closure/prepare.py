#!/usr/bin/env python3
"""Preserve the actual returned global error in the public result structure.

The original core status remains in the permanent epoch. This successor only
aligns startupStatus with the stronger status already returned by the wrapper.
The complete KERNEL refusal prefix is preserved byte for byte.
"""
from pathlib import Path
import hashlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LIFECYCLE = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
INPUTS = (LIFECYCLE,)
INPUT_SHA256 = 'ccf6483a792dd9b0b22624ffb86e509199ebb971c9273408a7c6d9e931555f44'
EXPORTS = {}
COMPANIONS = {}
PROJECT_UNITS = ()
COMPILE_DEFINITIONS = {}
INCLUDE_DIRECTORIES = ()
KERNEL_REFUSAL = '''#if defined(KERNEL)
    /* Final kernel stack/native/entry admission has not been established.
     * This immutable successor supplies the owner protocol, not that proof. */
    return out->startupStatus=NV_ERR_NOT_READY;
#endif'''


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def closed_prefix(text):
    first = text.index('NV_STATUS s540GlobalRmInitialize(')
    end = text.index(KERNEL_REFUSAL, first)+len(KERNEL_REFUSAL)
    return text[first:end]


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exact global-result lifecycle input required')
    before = values[LIFECYCLE]
    if digest(before) != INPUT_SHA256:
        raise ValueError('Reviewed closed global lifecycle bytes changed')
    anchor = 'return recordStatus!=NV_OK?recordStatus:status;'
    if before.count(anchor) != 3:
        raise ValueError('Exactly three actual record/original return boundaries required')
    after = before.replace(anchor, 'return out->startupStatus=recordStatus!=NV_OK?recordStatus:status;')
    if closed_prefix(after) != closed_prefix(before):
        raise ValueError('Global result successor changed the closed KERNEL prefix')
    return {LIFECYCLE: after}
