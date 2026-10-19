#!/usr/bin/env python3
"""Select the actual nonprimary VGA early return; refuse primary emulation."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / 'builders/check_nvidia_execution.py').is_file())
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

SOURCE = 'src/nvidia/arch/nvalloc/unix/src/vbioscall.c'
PROFILE = 'S540_NVIDIA_NONPRIMARY_X86_EMULATION'
EARLY = '''    if (!NV_PRIMARY_VGA(NV_GET_NV_STATE(pGpu)))     // not the primary GPU
        return NV_OK;'''

def sha(data): return hashlib.sha256(data).hexdigest()

def overlay(text):
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_text())
    if sha(text.encode()) != contract['original_source_sha256'][SOURCE]:
        raise ValueError('Nonprimary emulation requires its exact original complete source')
    first, last = function_span(text, 'RmInitX86EmuState')
    old = text[first:last]
    if old.count(EARLY) != 1 or sha(old.encode()) != contract['original_function_sha256']:
        raise ValueError('The original nonprimary early-return body changed')
    prefix = old[:old.index('{') + 1]
    replacement = prefix + '''
#if !defined(S540_NVIDIA_NONPRIMARY_X86_EMULATION) || S540_NVIDIA_NONPRIMARY_X86_EMULATION != 1
#error "Explicit nonprimary-only x86 emulation source profile required"
#endif
''' + EARLY + '''

    /* This selected driver owns no primary VGA/BIOS emulation endpoint.
     * Refuse before allocating stack, mapping legacy memory or publishing
     * emulator callbacks. No successful primary initialization is invented. */
    return NV_ERR_NOT_SUPPORTED;
}'''
    result = text[:first] + replacement + text[last:]
    if contract.get('proposed_source_sha256') not in (None, sha(result.encode())) or \
            contract.get('proposed_function_sha256') not in (None, sha(replacement.encode())):
        raise ValueError('The exact nonprimary-only source successor changed')
    return result
