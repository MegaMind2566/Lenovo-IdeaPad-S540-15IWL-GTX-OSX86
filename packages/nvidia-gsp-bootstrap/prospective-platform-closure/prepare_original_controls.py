#!/usr/bin/env python3
"""Exact pinned identity/disabled bodies and real original query callers."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def body(text, name):
    matches = list(re.finditer(r'^\s*(?:static\s+)?(?:NV_STATUS|NvBool|NvU32)(?:\s+NV_API_CALL)?\s+' +
                              re.escape(name) + r'\s*\(', text, re.M))
    if len(matches) != 1:
        raise ValueError('Expected one exact original function: ' + name)
    opening = text.index('{', matches[0].end())
    depth = 1
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for token in tokens.finditer(text, opening + 1):
        depth += (token[0] == '{') - (token[0] == '}')
        if not depth:
            return text[matches[0].start():token.end()]
    raise ValueError('Unclosed original function: ' + name)


def prepare(upstream, output):
    contract = json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    text = {}
    for relative, expected in contract['original_source_sha256'].items():
        raw = (upstream/relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Pinned original source changed: ' + relative)
        text[relative] = raw.decode()
    definitions = [('kernel-open/nvidia/os-interface.c', 'os_get_is_openrm'),
                   ('kernel-open/nvidia/os-interface.c', 'os_get_tegra_platform'),
                   ('kernel-open/nvidia/nv.c', 'nv_dynamic_power_available')]
    callers = [('_osGetTegraPlatform', 'control_osGetTegraPlatform'),
               ('osGetSimulationMode', 'control_osGetSimulationMode'),
               ('osGetIsOpenRM', 'control_osGetIsOpenRM')]
    pieces = ['#include "nv.h"\n#include "os-interface.h"\n#include "gpu/gpu.h"\n'
              '#if defined(NV_PM_RUNTIME_AVAILABLE) || NV_SUPPORTS_PLATFORM_DISPLAY_DEVICE\n'
              '#error "Original controls require the official disabled branches"\n#endif\n']
    for source, name in definitions:
        code = body(text[source], name)
        pieces.append(re.sub(r'\b'+re.escape(name)+r'\b', 'original_'+name, code))
    for name, renamed in callers:
        code = body(text['src/nvidia/arch/nvalloc/unix/src/os.c'], name)
        for old, new in callers:
            code = re.sub(r'\b'+re.escape(old)+r'\b', new, code)
        pieces.append(code)
    output.mkdir(parents=True, exist_ok=True)
    target = output/'original_controls.c'
    target.write_text('\n\n'.join(pieces)+'\n')
    return target, {'exact_original_identity_or_disabled_bodies': len(definitions),
        'exact_original_query_caller_bodies': len(callers),
        'only_function_name_prefixes_changed': True,
        'original_source_sha256': contract['original_source_sha256'],
        'fixture_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
