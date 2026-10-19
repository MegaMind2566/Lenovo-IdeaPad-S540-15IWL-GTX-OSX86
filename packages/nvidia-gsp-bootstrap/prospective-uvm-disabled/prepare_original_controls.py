#!/usr/bin/env python3
"""Copy exact pinned disabled branches/forwarders into an isolated CPU fixture."""
import hashlib
import json
from pathlib import Path
import re

SOURCES = {
    'kernel-open/nvidia/nv.c': 'ce04946d288cf0251668a2d847acceb2a39af9dac2f13bb005f53759c774dbf7',
    'src/nvidia/arch/nvalloc/unix/src/os.c': '057b50fcb738be90a073b60f63e70559706864ddcec3bf703282563173e3dce4',
    'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c': 'ed6d7020a8a1772bc44608178aa13a77a72b8bf0eabe3293c12bc9d2b122c6c9',
    'src/nvidia/arch/nvalloc/unix/include/nv.h': '02ce4b371e0a8dd26f62a320e88c8382dcf31a21b727503a66abcaea9eecf09b',
    'src/nvidia/src/kernel/gpu/nvlink/kernel_nvlink.c': '89145e654dd6fd337120a08e367791f61aabb63e81de86e61a38e25407b31fd7',
}

def body(text, name):
    pattern = re.compile(r'^(?:void|NV_STATUS)(?: NV_API_CALL)?\s+' + re.escape(name) + r'\s*\(', re.M)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError('Expected one original definition: ' + name)
    start = matches[0].start()
    brace = text.index('{', matches[0].end())
    depth = 1
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for token in tokens.finditer(text, brace + 1):
        depth += (token[0] == '{') - (token[0] == '}')
        if depth == 0:
            return text[start:token.end()]
    raise ValueError('Unclosed original definition: ' + name)

def prepare(upstream: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    text = {}
    for relative, expected in SOURCES.items():
        raw = (upstream / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Pinned original source changed: ' + relative)
        text[relative] = raw.decode()
    disabled = []
    for name in ('nv_schedule_uvm_isr', 'nv_schedule_uvm_drain_p2p', 'nv_schedule_uvm_resume_p2p'):
        code = body(text['kernel-open/nvidia/nv.c'], name)
        disabled.append(re.sub(r'\b' + name + r'\b', 'original_disabled_' + name, code))
    forwarders = []
    names = ('osQueueMMUFaultHandler', 'osQueueDrainP2PHandler', 'osQueueResumeP2PHandler', 'gmcapiMmuFaultQueued')
    for name in names:
        source = 'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c' if name == names[-1] else 'src/nvidia/arch/nvalloc/unix/src/os.c'
        code = body(text[source], name)
        for rename in names:
            code = re.sub(r'\b' + rename + r'\b', 'prospective_' + rename, code)
        forwarders.append(code)
    header = '#include "nv.h"\n#include "gpu/gpu.h"\n#include "core/gmcapi_impl.h"\n#if defined(NV_UVM_ENABLE)\n#error "Fixture requires actual disabled branch"\n#endif\n'
    target = output / 'original_controls.c'
    target.write_text(header + '\n\n'.join(disabled + forwarders) + '\n')
    record = {'source_sha256': SOURCES, 'exact_disabled_bodies': 3,
        'exact_forwarding_bodies': 4, 'only_function_name_prefixes_changed': True,
        'fixture_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'original_full_tu_executed': False, 'hardware_rpc_executed': False}
    (output / 'original-controls.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return target, record
