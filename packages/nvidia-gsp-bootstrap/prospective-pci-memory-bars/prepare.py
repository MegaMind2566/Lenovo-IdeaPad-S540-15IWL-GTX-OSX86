#!/usr/bin/env python3
"""Classify memory BARs and genuine PCIe endpoint types in the exact B4 producer."""
from pathlib import Path
import hashlib
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-pci-memory-bars'
PLATFORM = 'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPlatform.cpp'
INPUTS = (PLATFORM,)
ORIGINAL_INPUTS = ()
COMPANIONS = {}
PROJECT_UNITS = ()
EXPORTS = {}
INCLUDE_DIRECTORIES = ()
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'check.py',
                'tests/check_platform.cpp.inc', 'tests/target-registry-fixture.json',
                'tests/test_driver_alias.py')


def input_hashes():
    raw = (HERE / 'BASE-SHA256SUMS').read_text()
    match = re.fullmatch(r'([0-9a-f]{64})  ' + re.escape(PLATFORM) + r'\n', raw)
    if match is None:
        raise ValueError('One exact B4 platform source hash is required')
    return {PLATFORM: match[1]}


BASE_SHA256 = input_hashes()
BEFORE = '''        if (!low) continue;
        const NvU32 kind = low & 7U;
'''
AFTER = '''        if (!low) continue;
        // Legacy port I/O is not one of the RM's three memory apertures.
        if (low & 1U) continue;
        const NvU32 kind = low & 7U;
'''
ENDPOINT_BEFORE = '            express = ((flags >> 4) & 15U) == 0; // PCI Express endpoint\n'
ENDPOINT_AFTER = '''            const NvU16 type = (flags >> 4) & 15U;
            express = type == 0 || type == 1; // PCIe or legacy PCIe endpoint
'''


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('The exact pre-profile B4 platform source is required')
    original = values[PLATFORM]
    if hashlib.sha256(original.encode()).hexdigest() != BASE_SHA256[PLATFORM]:
        raise ValueError('The frozen B4 platform source changed')
    if original.count(BEFORE) != 1 or original.count(ENDPOINT_BEFORE) != 1:
        raise ValueError('The exact memory BAR or PCIe endpoint classification anchor changed')
    return {PLATFORM: original.replace(BEFORE, AFTER).replace(ENDPOINT_BEFORE, ENDPOINT_AFTER)}
