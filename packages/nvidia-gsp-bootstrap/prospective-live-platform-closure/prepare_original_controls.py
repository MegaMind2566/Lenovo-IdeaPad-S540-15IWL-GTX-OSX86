#!/usr/bin/env python3
"""Exact original temporary-file/BIF bodies and original public forwarders."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def body(text, name):
    matches = list(re.finditer(r'^\s*(?:static\s+)?(?:NV_STATUS|NvBool|void)(?:\s+NV_API_CALL)?\s+' +
                              re.escape(name)+r'\s*\(', text, re.M))
    if len(matches) != 1:
        raise ValueError('Expected one original definition: '+name)
    opening = text.index('{', matches[0].end()); depth = 1
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for token in tokens.finditer(text, opening+1):
        depth += (token[0]=='{')-(token[0]=='}')
        if not depth:
            return text[matches[0].start():token.end()]
    raise ValueError('Unclosed original function: '+name)


def prepare(upstream, output):
    contract = json.loads((HERE/'SOURCE-CONTRACT.json').read_text()); text = {}
    for relative, expected in contract['original_source_sha256'].items():
        raw = (upstream/relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Pinned original source changed: '+relative)
        text[relative] = raw.decode()
    definitions = ['os_is_bif_reset_supported', 'os_allocate_temporary_file', 'os_close_file',
                   'os_write_file', 'os_read_file']
    pieces = ['#include "nv.h"\n#include "os-interface.h"\n#include "gpu/gpu.h"\n#include "os/os.h"\n'
        '#include <errno.h>\n'
        '#if NV_FILESYSTEM_ACCESS_AVAILABLE\n#error "Fixture requires official disabled filesystem"\n#endif\n'
        'typedef struct fixtureLinuxStateTag { NvBool init_on_probe; } nv_linux_state_t;\n'
        'extern nv_linux_state_t *fixtureLinuxState(nv_state_t *);\n'
        '#define NV_GET_NVL_FROM_NV_STATE(nv) fixtureLinuxState(nv)\n'
        '#define ERR_PTR(error) ((void *)(NvSPtr)(error))\n'
        '#define IS_ERR(pointer) ((NvUPtr)(pointer) >= (NvUPtr)-4095)\n'
        '#define PTR_ERR(pointer) ((long)(NvSPtr)(pointer))\n']
    for name in definitions:
        code = body(text['kernel-open/nvidia/os-interface.c'], name)
        pieces.append(re.sub(r'\b'+name+r'\b', 'original_'+name, code))
    forwarders = ['osIsBifResetSupported', 'osModifyGpuSwStatePersistence', 'osAllocateTemporaryFile',
                  'osCloseFile', 'osWriteToFile', 'osReadFromFile']
    for name in forwarders:
        code = body(text['src/nvidia/arch/nvalloc/unix/src/os.c'], name)
        if name != 'osIsBifResetSupported':
            code = re.sub(r'\b'+name+r'\b', 'control_'+name, code)
        pieces.append(code)
    code = body(text['src/nvidia/arch/nvalloc/unix/src/osapi.c'], 'rm_get_uefi_console_status')
    pieces.append(re.sub(r'\brm_get_uefi_console_status\b', 'control_rm_get_uefi_console_status', code))
    output.mkdir(parents=True, exist_ok=True); target = output/'original_controls.c'
    target.write_text('\n\n'.join(pieces)+'\n')
    return target, {'official_bodies': len(definitions), 'actual_callers': len(forwarders)+1,
        'linux_private_layout_fixture': True, 'console_metadata_provider_fixture': True,
        'only_function_name_prefixes_changed': True,
        'fixture_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'original_source_sha256': contract['original_source_sha256']}
