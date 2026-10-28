#!/usr/bin/env python3
"""Bind and transform the original PCI producers and pre-GSP validity check."""
from pathlib import Path
import hashlib
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CHIPSET = 'src/nvidia/src/kernel/platform/chipset/chipset.c'
PCIE = 'src/nvidia/src/kernel/platform/chipset/chipset_pcie.c'
OS = 'src/nvidia/arch/nvalloc/unix/src/os.c'
OSINIT = 'src/nvidia/arch/nvalloc/unix/src/osinit.c'
GSP = 'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c'
INPUTS = (CHIPSET, PCIE, OS, OSINIT, GSP)
BASE_SHA256 = {
    CHIPSET: '91f9bb3b15dc30260ff84afa9990cb8200fe640b2b916a9b2d03a54ebfe656d8',
    PCIE: '8cdef61abba6a4e8fa732cc666f1963db90508996f8c3adb5c7d629f109e9ef5',
    OS: '9e0907d3a54fd71ef6ff01966b6c443ea8f7711d00d151bd7ba1f5171268abd5',
    OSINIT: 'e53129b6bb1f9a32fc62e2590383d16fe25a035e39521ed3988ecb3b602dd6c2',
    GSP: '2d026d3f55bc10b972c072ad6d02a79117ac3338d24e3bf548eb4cd806b88a81',
}
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact original PCI topology anchor changed: ' + before[:110])
    return text.replace(before, after)


def edit(text, function, before, after):
    start, end = function_span(text, function)
    return text[:start] + once(text[start:end], before, after) + text[end:]


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exactly five original PCI topology inputs required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Frozen original PCI topology prefix changed: ' + name)
    output = dict(values)
    output[CHIPSET] = edit(values[CHIPSET], 'clFindFHBAndGetChipsetInfoIndex_IMPL',
        '''    pCl->FHBAddr.valid  = 0x1;
    pCl->FHBAddr.handle = NULL;''',
        '''    // Missing topology has no valid address or handle.
    pCl->FHBAddr.valid  = 0x0;
    pCl->FHBAddr.handle = NULL;''')
    output[PCIE] = edit(values[PCIE], 'objClInitGpuPortData',
        '''        pGpu->gpuClData.upstreamPort.addr.valid  = 0x1;
        pGpu->gpuClData.upstreamPort.addr.handle = NULL;''',
        '''        // A later real cache lookup must not accept this missing port.
        pGpu->gpuClData.upstreamPort.addr.valid  = 0x0;
        pGpu->gpuClData.upstreamPort.addr.handle = NULL;''')
    output[PCIE] = edit(output[PCIE], 'clStoreBusTopologyCache_IMPL',
        '''                if (!handle)
                {
                    if (func == 0)
                    {
                        // If a read to function zero of a specified bus/device master aborts,
                        // then it is assumed that no such device exists on the bus since
                        // devices are required to implement function number zero.
                        // In this case reads to the remaining functions are not necessary.
                        break;
                    }
                    else
                    {
                        continue;
                    }
                }''',
        '''                if (!handle)
                {
                    // A missing allowlisted function is not a physical
                    // absence result for its unlisted function-zero sibling.
                    // Unlisted DBDFs require no hardware access.
                    continue;
                }''')
    output[PCIE] = edit(output[PCIE], '_objClScanPcieBusDfs',
        '''    NvU8  multifunction;
    NvU8  headerType;
''', '')
    output[PCIE] = edit(output[PCIE], '_objClScanPcieBusDfs',
        '''            handle = osPciInitHandle(domain, bus, dev, 0, &vendorID, &deviceID);
            if (!handle || (!PCI_IS_VENDORID_VALID(vendorID)))
                continue;

            secBus = osPciReadByte(handle, PCI_TYPE_1_SECONDARY_BUS_NUMBER);

            // Check for PCI-to-PCI bridge
            classCode = osPciReadByte(handle, PCI_HEADER_TYPE0_BASECLASS);
            if (classCode == PCI_CLASS_BRIDGE_DEV) 
            {
                if (secBus != 0) 
                {
                    // DFS behavior: push child bus
                    _objClPushBus(pCl, secBus);
                }
            }

            headerType = osPciReadByte(handle, PCI_HEADER_TYPE0_HEADER_TYPE);
            multifunction = headerType & PCI_MULTIFUNCTION;

            for (func = 0; func < (multifunction ? PCI_MAX_FUNCTIONS : 1); func++) 
''',
        '''            // Probe the bounded allowlist independently for every
            // function: the physical function-zero sibling may be unlisted.
            for (func = 0; func < PCI_MAX_FUNCTIONS; func++)
''')
    output[PCIE] = edit(output[PCIE], '_objClScanPcieBusDfs',
        '''                if ((!handle) || (!PCI_IS_VENDORID_VALID(vendorID)))
                    continue;

                // Add device to the list''',
        '''                if ((!handle) || (!PCI_IS_VENDORID_VALID(vendorID)))
                    continue;

                // Use this actual matched function's child-bus data.
                secBus = osPciReadByte(handle, PCI_TYPE_1_SECONDARY_BUS_NUMBER);
                classCode = osPciReadByte(handle, PCI_HEADER_TYPE0_BASECLASS);
                if ((classCode == PCI_CLASS_BRIDGE_DEV) && (secBus != 0))
                    _objClPushBus(pCl, secBus);

                // Add device to the list''')
    os = once(values[OS], '#include <nv.h>', '#include "S540PciTopologyFacts.h"\n#include <nv.h>')
    for suffix, ctype, endpoint, operation in (
        ('Byte', 'NvU8', 'byte', 'READ_BYTE'), ('Word', 'NvU16', 'word', 'READ_WORD'),
        ('Dword', 'NvU32', 'dword', 'READ_DWORD')):
        os = edit(os, 'osPciRead' + suffix,
            f'''    {ctype} val;
    os_pci_read_{endpoint}(pHandle, Offset, &val);
    return val;''',
            f'''    {ctype} val = ({ctype})~({ctype})0;
    NV_STATUS status = os_pci_read_{endpoint}(pHandle, Offset, &val);
    if (status != NV_OK)
    {{
        s540PciTopologyRecordFailure(S540_PCI_TOPOLOGY_{operation}, status);
        return ({ctype})~({ctype})0;
    }}
    return val;''')
    for suffix, endpoint, operation in (
        ('Byte', 'byte', 'WRITE_BYTE'), ('Word', 'word', 'WRITE_WORD'),
        ('Dword', 'dword', 'WRITE_DWORD')):
        os = edit(os, 'osPciWrite' + suffix,
            f'    os_pci_write_{endpoint}(pHandle, Offset, Value);',
            f'''    NV_STATUS status = os_pci_write_{endpoint}(pHandle, Offset, Value);
    if (status != NV_OK)
        s540PciTopologyRecordFailure(S540_PCI_TOPOLOGY_{operation}, status);''')
    output[OS] = os
    osinit = once(values[OSINIT], '#include <nv.h>', '#include "S540PciTopologyFacts.h"\n#include <nv.h>')
    output[OSINIT] = edit(osinit, 'osInitScalability',
        '''    if (pCl != NULL)
    {
        return clInitPcie(pGpu, pCl);
    }''',
        '''    if (pCl != NULL)
    {
        OBJOS *pOs = SYS_GET_OS(pSys);
        // This selected bound transport offers OS configuration access, not
        // arbitrary direct PCIe/MCFG mappings. It is not a physical OS fact.
        if (pOs == NULL || !s540PciTopologyUsesOsConfig(pGpu->pOsGpuInfo))
            return NV_ERR_NOT_SUPPORTED;
        pOs->setProperty(pOs, PDB_PROP_OS_DOES_NOT_ALLOW_DIRECT_PCIE_MAPPINGS, NV_TRUE);
        return clInitPcie(pGpu, pCl);
    }''')
    gsp = once(values[GSP], '#include "gpu/gsp/kernel_gsp.h"',
        '#include "gpu/gsp/kernel_gsp.h"\n#include "platform/chipset/chipset.h"\n'
        '#include "S540PciTopologyFacts.h"')
    start, unused_end = function_span(gsp, 'kgspInitRm_IMPL')
    start = gsp.rfind('\n', 0, start) + 1
    # Keep the original declaration and preceding return type together.
    if gsp[:start].endswith('NV_STATUS\n'):
        start -= len('NV_STATUS\n')
    gsp = gsp[:start] + (HERE / 'preboot-topology.c.inc').read_text().rstrip() + '\n\n' + gsp[start:]
    gsp = once(gsp, 'static NV_STATUS\n_kgspPrepareSystemInfo\n(',
        'static NV_STATUS _s540RequirePciTopology(OBJGPU *pGpu);\n\n'
        'static NV_STATUS\n_kgspPrepareSystemInfo\n(')
    gsp = edit(gsp, '_kgspPrepareSystemInfo',
        '    pKernelGsp->encodedSystemInfoKeyLimit = 65536 / sizeof(NvU64);',
        '''    // Do not build a publication buffer from an already failed epoch.
    status = _s540RequirePciTopology(pGpu);
    if (status != NV_OK)
        goto s540_topology_failure;

    pKernelGsp->encodedSystemInfoKeyLimit = 65536 / sizeof(NvU64);''')
    gsp = edit(gsp, '_kgspPrepareSystemInfo',
        '''                                   &pKernelGsp->encodedSystemInfoCount);
    if (status != NV_OK)
    {
        NV_PRINTF''',
        '''                                   &pKernelGsp->encodedSystemInfoCount);
    // The encoder can observe a failed scalar PCI read yet return NV_OK.
    // Revalidate authority and real identities before allowing publication.
    if (status == NV_OK)
        status = _s540RequirePciTopology(pGpu);
    if (status != NV_OK)
    {
s540_topology_failure:
        NV_PRINTF''')
    output[GSP] = edit(gsp, 'kgspInitRm_IMPL',
        '    pKernelGsp->bInInit = NV_TRUE;',
        '''    // Refuse unverified topology before FWSEC/FRTS and GSP boot.
    status = _s540RequirePciTopology(pGpu);
    if (status != NV_OK)
        return status;

    pKernelGsp->bInInit = NV_TRUE;''')
    return output


def cpu_system_info_fragments(selected):
    return {'actual-system-info.inc': _function(selected[GSP], '_s540RequirePciTopology') +
            '\n' + _function(selected[GSP], '_kgspPrepareSystemInfo')}


def _function(text, name):
    start, end = function_span(text, name)
    start = text.rfind('\n', 0, start) + 1
    prior = text[:start].rstrip('\n').rsplit('\n', 1)[-1]
    if prior in ('NV_STATUS', 'static NV_STATUS', 'NvBool', 'static NvBool',
                 'NvU32', 'static NvU32', 'void', 'static void'):
        start -= len(prior) + 1
    return text[start:end] + '\n'


def cpu_fragments(selected):
    """Actual selected bodies; typed CPU fixture supplies resource endpoints."""
    functions = [_function(selected[OS], 'osPci' + operation + width)
        for operation in ('Read', 'Write') for width in ('Byte', 'Word', 'Dword')]
    functions += [_function(selected[GSP], '_s540RequirePciTopology'),
                  _function(selected[OSINIT], 'osInitScalability')]
    chipset = _function(selected[CHIPSET], 'clFindFHBAndGetChipsetInfoIndex_IMPL')
    fhb_tail = chipset[chipset.index('    // This is bad, we didn\'t find the First Host Bridge device'):]
    require_end = fhb_tail.rfind('}')
    fhb_tail = fhb_tail[:require_end]
    pcie = _function(selected[PCIE], 'objClInitGpuPortData')
    marker = '    if (!handle)\n    {'
    start = pcie.index(marker)
    body = pcie.index('{', start)
    depth, end = 1, body + 1
    while depth and end < len(pcie):
        depth += (pcie[end] == '{') - (pcie[end] == '}')
        end += 1
    if depth:
        raise ValueError('Actual missing-upstream branch is incomplete')
    scans = [_function(selected[PCIE], name) for name in
             ('clFreeBusTopologyCache_IMPL', '_objClPushBus', '_objClPopBus', '_objClScanPcieBusDfs',
              'clStoreBusTopologyCache_IMPL')]
    return {'actual-original.inc': '\n'.join(functions),
            'actual-missing-fhb.inc': fhb_tail,
            'actual-missing-upstream.inc': pcie[start:end] + '\n',
            'actual-topology-scan.inc': '\n'.join(scans)}


# Mutation sites are in the actual selected fragments, not duplicate policy.
ORIGINAL_MUTATIONS = {
    'failed-byte-read-returned-clobber': ('actual-original.inc',
        '        return (NvU8)~(NvU8)0;', '        return val;'),
    'failed-word-read-lost-observation': ('actual-original.inc',
        's540PciTopologyRecordFailure(S540_PCI_TOPOLOGY_READ_WORD, status);', '(void)status;'),
    'failed-dword-write-lost-observation': ('actual-original.inc',
        's540PciTopologyRecordFailure(S540_PCI_TOPOLOGY_WRITE_DWORD, status);', '(void)status;'),
    'missing-fhb-fabricated-valid': ('actual-missing-fhb.inc',
        'pCl->FHBAddr.valid  = 0x0;', 'pCl->FHBAddr.valid  = 0x1;'),
    'missing-upstream-fabricated-valid': ('actual-missing-upstream.inc',
        'pGpu->gpuClData.upstreamPort.addr.valid  = 0x0;',
        'pGpu->gpuClData.upstreamPort.addr.valid  = 0x1;'),
    'os-config-ready-guard-bypassed': ('actual-original.inc',
        'pOs == NULL || !s540PciTopologyUsesOsConfig(pGpu->pOsGpuInfo)', 'pOs == NULL'),
    'os-config-property-not-selected': ('actual-original.inc',
        'pOs->setProperty(pOs, PDB_PROP_OS_DOES_NOT_ALLOW_DIRECT_PCIE_MAPPINGS, NV_TRUE);', '(void)pOs;'),
    'preboot-os-config-property-ignored': ('actual-original.inc',
        '!pOs->getProperty(pOs, PDB_PROP_OS_DOES_NOT_ALLOW_DIRECT_PCIE_MAPPINGS)', 'NV_FALSE'),
    'preboot-upstream-validity-ignored': ('actual-original.inc',
        '!pGpu->gpuClData.upstreamPort.addr.valid ||', 'NV_FALSE ||'),
    'preboot-fhb-identity-lost': ('actual-original.inc',
        'facts.fhb.vendor = pCl->FHBBusInfo.vendorID;', 'facts.fhb.vendor = 0U;'),
    'preboot-backend-error-lost': ('actual-original.inc',
        'return s540PciTopologyValidateForGsp(pGpu->pOsGpuInfo, &facts);',
        '(void)s540PciTopologyValidateForGsp(pGpu->pOsGpuInfo, &facts); return NV_OK;'),
    'linear-scan-function-zero-assumed': ('actual-topology-scan.inc',
        '''                    // Unlisted DBDFs require no hardware access.
                    continue;''',
        '''                    // Unlisted DBDFs require no hardware access.
                    if (func == 0) break;
                    continue;'''),
    'dfs-scan-only-function-zero': ('actual-topology-scan.inc',
        'for (func = 0; func < PCI_MAX_FUNCTIONS; func++)',
        'for (func = 0; func < 1; func++)'),
    'dfs-child-bus-not-traversed': ('actual-topology-scan.inc',
        '                    _objClPushBus(pCl, secBus);',
        '                    (void)secBus;'),
}
