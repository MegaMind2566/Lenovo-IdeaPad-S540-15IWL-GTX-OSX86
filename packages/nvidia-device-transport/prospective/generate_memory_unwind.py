#!/usr/bin/env python3
"""Emit separate, prospective memory unwind patches from pinned original text.

This does not modify or approve the active ten-overlay source profile.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

PHYSICAL = 'src/nvidia/arch/nvalloc/unix/src/osmemdesc.c'
VIRTUAL = 'src/nvidia/src/kernel/mem_mgr/virtual_mem.c'
PEER_BAR = 'src/nvidia/src/kernel/gpu/bus/kern_bus.c'
PINNED = {
    PHYSICAL: 'c1cbd0b0bb814d5ca1d0a022d59a4b91ae90ca2663ee5d48621f7527d85cd897',
    VIRTUAL: '7b9949bc423a29ba8cc16ee50590bb5e3eaaef394d6bdd8f531cbfc2fff0fb9a',
    PEER_BAR: 'f1c120125c79dc97877462994a68372b53e43e00dfae04b6dd57dc0a18e0d1bf',
}


def exact_function(text, prefix):
    start = text.index(prefix)
    brace = text.index('{', start)
    depth, pos = 1, brace + 1
    while depth:
        depth += (text[pos] == '{') - (text[pos] == '}')
        pos += 1
    return text[start:pos]


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one source anchor: {old!r}')
    return text.replace(old, new, 1)


def adapt_physical(text):
    prefix = 'static NV_STATUS\nosCreateOsDescriptorFromPhysAddr\n('
    body = exact_function(text, prefix)
    changed = once(body, '    MEMORY_DESCRIPTOR *pMemDesc;\n',
                   '    MEMORY_DESCRIPTOR *pMemDesc = NULL;\n    void *pPrivate = NULL;\n')
    changed = once(changed, 'rmStatus = memdescCreate(ppMemDesc,',
                   'rmStatus = memdescCreate(&pMemDesc,')
    changed = once(changed, '    pMemDesc = *ppMemDesc;\n\n', '')
    changed = once(changed,
                   '    if (pPhys_addrs == NULL)\n        goto cleanup_memdesc;',
                   '    if (pPhys_addrs == NULL)\n    {\n'
                   '        rmStatus = NV_ERR_NO_MEMORY;\n        goto cleanup_memdesc;\n    }')
    changed = once(changed, '    *ppPrivate = NULL;\n', '')
    changed = once(changed, '                                      ppPrivate);',
                   '                                      &pPrivate);')
    changed = changed.replace('memdescSetMemData(pMemDesc, *ppPrivate,',
                              'memdescSetMemData(pMemDesc, pPrivate,')
    changed = once(changed,
                   '    portMemFree(pPhys_addrs);\n\n    return NV_OK;',
                   '    portMemFree(pPhys_addrs);\n\n'
                   '    // Publish only the descriptor and backing that completed every stage.\n'
                   '    *ppMemDesc = pMemDesc;\n    *ppPrivate = pPrivate;\n\n    return NV_OK;')
    changed = once(changed,
                   '    if (*ppPrivate != NULL)\n    {\n'
                   '        nv_unregister_phys_pages(NV_GET_NV_STATE(pGpu), *ppPrivate);\n    }',
                   '    if (pPrivate != NULL)\n    {\n'
                   '        nv_unregister_phys_pages(NV_GET_NV_STATE(pGpu), pPrivate);\n    }')
    return once(text, body, changed)


def adapt_virtual(text):
    body = exact_function(text, 'NV_STATUS\nvirtmemMapTo_IMPL\n(')
    changed = once(body, '    NvBool      bIsIndirectPeer       = NV_FALSE;\n',
                   '    NvBool      bIsIndirectPeer       = NV_FALSE;\n'
                   '    NvBool      bIndirectPeerIommuMapped = NV_FALSE;\n')
    changed = once(changed,
                   '                NV_PRINTF(LEVEL_ERROR, "DMA map pages failed for requested GPU!\\n");\n'
                   '                goto done;\n            }\n',
                   '                NV_PRINTF(LEVEL_ERROR, "DMA map pages failed for requested GPU!\\n");\n'
                   '                goto done;\n            }\n'
                   '            bIndirectPeerIommuMapped = NV_TRUE;\n')
    changed = once(changed,
                   '            if (pDmaMappingInfo->pMemDesc != NULL && bIsIndirectPeer)\n',
                   '            if (pDmaMappingInfo->pMemDesc != NULL && bIndirectPeerIommuMapped)\n')
    return once(text, body, changed)


def adapt_peer_bar(text):
    body = exact_function(text, 'RmPhysAddr\nkbusSetupPeerBarAccess_IMPL\n(')
    changed = once(body, '    MEMORY_DESCRIPTOR *pMemDesc = *ppMemDesc;\n',
                   '    MEMORY_DESCRIPTOR *pMemDesc = *ppMemDesc;\n'
                   '    NvBool bMemDescCreated = NV_FALSE;\n')
    changed = once(changed,
                   '        memdescDescribe(pMemDesc, ADDR_SYSMEM, base, size);',
                   '        bMemDescCreated = NV_TRUE;\n'
                   '        memdescDescribe(pMemDesc, ADDR_SYSMEM, base, size);')
    changed = once(changed, '        if (status != NV_OK)\n',
                   '        if ((status != NV_OK) && bMemDescCreated)\n')
    return once(text, body, changed)


def load_pinned(upstream):
    inputs = {p: (upstream / p).read_text() for p in PINNED}
    for path, text in inputs.items():
        if hashlib.sha256(text.encode()).hexdigest() != PINNED[path]:
            raise ValueError(f'Not pinned original source: {path}')
    return inputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    inputs = load_pinned(args.upstream)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for path, adapt, name in (
        (PHYSICAL, adapt_physical, 'physical-import-publication-prospective.patch'),
        (VIRTUAL, adapt_virtual, 'indirect-peer-map-unwind-prospective.patch'),
        (PEER_BAR, adapt_peer_bar, 'peer-bar-borrowed-owner-prospective.patch'),
    ):
        modified = adapt(inputs[path])
        patch = ''.join(difflib.unified_diff(inputs[path].splitlines(True),
            modified.splitlines(True), fromfile='a/' + path, tofile='b/' + path))
        target = args.output / name
        target.write_text(patch)
        records.append({'patch': name, 'source': path,
            'original_sha256': PINNED[path],
            'modified_sha256': hashlib.sha256(modified.encode()).hexdigest(),
            'patch_sha256': hashlib.sha256(patch.encode()).hexdigest()})
    print(json.dumps({'format': 1, 'approved_profile': False, 'patches': records}, sort_keys=True))


if __name__ == '__main__':
    main()
