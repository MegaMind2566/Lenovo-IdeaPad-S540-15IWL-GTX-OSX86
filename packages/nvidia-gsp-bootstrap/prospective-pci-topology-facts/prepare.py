#!/usr/bin/env python3
"""Bind real retained PCI ancestor facts and refuse unverified GSP topology."""
from pathlib import Path
import hashlib
import importlib.util
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-pci-topology-facts'
HEADER = 'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp'
SESSION = 'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.cpp'
DARWIN = 'packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp'
SERVICES = 'packages/nvidia-device-transport/src/S540NvidiaDeviceServices.cpp'
INPUTS = (HEADER, SESSION, DARWIN, SERVICES)
spec = importlib.util.spec_from_file_location('retained_pci_topology_original_transforms', HERE / 'original_transforms.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
ORIGINAL_INPUTS = original.INPUTS
COMPANIONS = {DIRECTORY + '/' + name: HERE / name for name in (
    'S540PciTopologyFacts.h', 'S540PciTopology.hpp', 'S540PciTopology.cpp', 'sdk_import_reference.cpp')}
PROJECT_UNITS = ({'source': DIRECTORY + '/S540PciTopology.cpp', 'kind': 'cpp'},)
EXPORTS = {SERVICES: ('s540PciTopologyValidateForGsp', 's540PciTopologyRecordFailure',
                     's540PciTopologyUsesOsConfig')}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'original_transforms.py',
    'preboot-topology.c.inc', 'device-topology.cpp.inc',
    'darwin-topology-fields.inc', 'darwin-topology-includes.inc',
    'darwin-topology.cpp.inc', 'darwin-topology-helpers.cpp.inc',
    'session-topology-declarations.inc', 'session-topology.cpp.inc',
    'check.py', 'engine_mutations.py', 'gpu_edge_mutations.py', 'check_system_info.py',
    'tests/check_topology.cpp.inc', 'tests/check_original.c.inc',
    'tests/check_facade.cpp.inc', 'tests/check_gpu_edge.cpp.inc', 'tests/check_system_info.c.inc')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    result = {}
    for row in (HERE / 'BASE-SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', row)
        if match is None or match[2] in result:
            raise ValueError('Exact unique PCI topology preceding-prefix hashes required')
        result[match[2]] = match[1]
    if set(result) != set(INPUTS):
        raise ValueError('Exactly four project PCI topology source hashes required')
    return {**result, **original.BASE_SHA256}


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact PCI topology project anchor changed: ' + before[:120])
    return text.replace(before, after)


def edit(text, name, before, after):
    start, end = function_span(text, name)
    return text[:start] + once(text[start:end], before, after) + text[end:]


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exact four PCI topology project inputs required')
    for name, value in values.items():
        if hashlib.sha256(value.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Frozen PCI topology project prefix changed: ' + name)
    outputs = dict(values)
    include = '#include "../../nvidia-gsp-bootstrap/prospective-pci-topology-facts/'
    header = once(values[HEADER], '#include "../../nvidia-gsp-bootstrap/src/S540NvidiaGspDmaStop.h"',
        '#include "../../nvidia-gsp-bootstrap/src/S540NvidiaGspDmaStop.h"\n' + include + 'S540PciTopologyFacts.h"')
    outputs[HEADER] = once(header, '    NV_STATUS setPciSegment(NvU32 segment);',
        '    NV_STATUS setPciSegment(NvU32 segment);\n' +
        (HERE / 'session-topology-declarations.inc').read_text().rstrip())
    session = once(values[SESSION], '#include "S540NvidiaDeviceTransport.hpp"',
        '#include "S540NvidiaDeviceTransport.hpp"\n' + include + 'S540PciTopology.hpp"')
    session = edit(session, 'Session::setPciSegment',
        '    return NV_OK;',
        '    // Ordinary pre-original discovery on this exact retained session.\n'
        '#if defined(KERNEL)\n    return prepareTopology();\n#else\n    return NV_OK;\n#endif')
    start, end = function_span(session, 'Session::setPciSegment')
    outputs[SESSION] = session[:end] + '\n' + (HERE / 'session-topology.cpp.inc').read_text().rstrip() + '\n' + session[end:]
    darwin = once(values[DARWIN], '#include "S540NvidiaDeviceTransport.hpp"',
        '#include "S540NvidiaDeviceTransport.hpp"\n' + include + 'S540PciTopology.hpp"')
    darwin = once(darwin, '#include <IOKit/pci/IOPCIDevice.h>',
        '#include <IOKit/pci/IOPCIDevice.h>\n' + (HERE / 'darwin-topology-includes.inc').read_text().rstrip())
    darwin = once(darwin, 'struct Platform {\n',
        'struct Platform {\n' + (HERE / 'darwin-topology-fields.inc').read_text().rstrip() + '\n')
    start, end = function_span(darwin, 'live')
    darwin = darwin[:end] + '\n' + (HERE / 'darwin-topology.cpp.inc').read_text().rstrip() + '\n' + darwin[end:]
    darwin = edit(darwin, 'stop', '    if (p->registers) { p->registers->release(); p->registers = nullptr; }',
        '    releaseDarwinTopology(p);\n    if (p->registers) { p->registers->release(); p->registers = nullptr; }')
    marker = 'void S540NvidiaDeviceTransport::destroyDarwinBackend(void *opaque)'
    darwin = once(darwin, marker, (HERE / 'darwin-topology-helpers.cpp.inc').read_text().rstrip() + '\n\n' + marker)
    outputs[DARWIN] = darwin
    services = once(values[SERVICES], '#include "nv_device_services.h"',
        '#include "nv_device_services.h"\n' + include + 'S540PciTopologyFacts.h"\n'
        '#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"')
    marker = 'namespace {\nNV_STATUS pciRead(void *handle, NvU32 offset, NvU32 width, NvU32 &value)'
    services = once(services, marker, (HERE / 'device-topology.cpp.inc').read_text().rstrip() + '\n' + marker)
    services = edit(services, 'pciRead',
        '''    if (!ordinary() || !binding.session || !handle || handle != binding.pciHandle)
        return NV_ERR_INVALID_STATE;
    return binding.session->readConfig(offset,width,value);''',
        '''    if (!ordinary() || !binding.session || !handle)
        return NV_ERR_INVALID_STATE;
    if (handle == binding.pciHandle)
        return binding.session->readConfig(offset,width,value);
    return binding.session->readTopology(handle,offset,width,value);''')
    services = edit(services, 's540Global_os_pci_init_handle',
        '''    if (!facts.segmentKnown || facts.segment != segment || facts.bus != bus ||
        facts.device != device || facts.function != function || !binding.session->accessible())
        return nullptr;
    if (vendor) *vendor = 0x10de;
    if (deviceId) *deviceId = 0x1f91;
    return binding.pciHandle;''',
        '''    if (!facts.segmentKnown || facts.segment != segment) return nullptr;
    if (facts.bus == bus && facts.device == device && facts.function == function) {
        if (!binding.session->accessible()) return nullptr;
        if (vendor) *vendor = 0x10de;
        if (deviceId) *deviceId = 0x1f91;
        return binding.pciHandle;
    }
    // Fixed retained candidates are matched before any live PCI read.
    return binding.session->topologyHandle(segment,bus,device,function,vendor,deviceId);''')
    outputs[SERVICES] = services
    return outputs


def original_transforms(values):
    return original.transforms(values)
