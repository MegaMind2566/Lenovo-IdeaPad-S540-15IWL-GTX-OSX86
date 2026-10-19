#!/usr/bin/env python3
"""Generate an isolated Host overlay from the exact production baseline."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

HOST='packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp'
PIN='a9202786c8a66cb1b89bdc6d2513edeb0e893330a560071035f8707615cbb377'
CRYPTO='packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c'
MEMORY='packages/nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c'
EXTRA_PINS={CRYPTO:'90cca5923e8dfa56f694aaaad402b7d75f0eb89c1fe2af3f9c599828863f1a67',
            MEMORY:'81cff7c5c893dc924bc6d6de23cb0f5b90f73782e4bcb9574a43f394f13eadd8'}
HERE=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected unique Host source anchor')
    return text.replace(old,new)
def adapt(text):
    text=once(text,'#include "S540NvidiaGlobalRm.h"',
        '#include "S540NvidiaGlobalRm.h"\n#include "S540NvidiaGlobalRmHostRetention.h"\n'
        '#include "S540NvidiaGlobalCrypto.h"\n#include "nv_unsupported_memory.h"')
    text=once(text,'struct Allocation { void *pointer; NvU64 bytes; bool original; };',
        '''struct Allocation {
    void *pointer; NvU64 bytes; bool original;
    S540FirstTxnHostIdentity identity;
    NvU64 serial;
    bool pending, retired, released;
};
NvU64 nextAllocationSerial = 0;
S540GlobalRmHostRetentionSnapshot retention = {};''')
    text=once(text,'Allocation records[kCapacity] = {};',(HERE/'host-lifetime.inc').read_text()+'\nAllocation records[kCapacity] = {};')
    first=text.index('extern "C" NV_STATUS s540GlobalRmHostInitialize(')
    last=text.index('static void *allocateTracked(',first)
    text=text[:first]+(HERE/'initialize-shutdown.inc').read_text()+text[last:]
    text=once(text,'void release(void *p, NvU64) { std::free(p); }',
        '''void (*freeObserver)(NvU32, const void *, NvU64, const S540FirstTxnHostIdentity *, S540FirstTxnHostFreePermit) = nullptr;
void release(void *p, NvU64 bytes) {
    auto observer = __atomic_load_n(&freeObserver, __ATOMIC_ACQUIRE);
    if (observer) observer(1, p, bytes, nullptr, 0);
    std::free(p);
    if (observer) observer(2, p, bytes, nullptr, 0);
}''')
    start=text.index('static void *allocateTracked(');end=text.index('extern "C" void *s540GlobalRmHostAllocate(',start)
    text=text[:start]+(HERE/'tracked-allocation-body.inc').read_text()+text[end:]
    text=once(text,'extern "C" void s540GlobalRmRecordUnavailable(NvU32)\n{',
        'extern "C" void s540GlobalRmRecordUnavailable(NvU32 service)\n{\n'
        '    s540FirstTxnObserveServiceRefusal(1, service, NV_ERR_NOT_SUPPORTED);')
    begin=text.index('extern "C" void s540GlobalRmRecordUnavailable(')
    end=text.index('\nextern "C" void s540GlobalRmRecordService(',begin)
    block=text[begin:end]
    block=once(block,'__ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}\n}',
        '__ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}\n    s540FirstTxnObserveServiceRefusal(1, service, NV_ERR_NOT_SUPPORTED);\n}')
    text=text[:begin]+block+text[end:]
    text=once(text,'    if (guard) lock();\n    out->liveBytes = counters.liveBytes;',
        '    HostUse use;\n    if (!use) { *out = {}; out->unavailableCalls = __atomic_load_n(&counters.unavailableCalls, __ATOMIC_ACQUIRE);\n'
        '        out->invalidFrees = __atomic_load_n(&counters.invalidFrees, __ATOMIC_ACQUIRE); return; }\n'
        '    lock();\n    out->liveBytes = counters.liveBytes;')
    text=once(text,'    out->invalidFrees = counters.invalidFrees;',
        '    out->invalidFrees = __atomic_load_n(&counters.invalidFrees, __ATOMIC_ACQUIRE);')
    text=once(text,'    if (guard) unlock();\n}\n\nextern "C" void s540GlobalRmRecordUnavailable(',
        '    unlock();\n}\n\nextern "C" void s540GlobalRmRecordUnavailable(')
    text=once(text,'    return counters.initialized ? &platformFacts : nullptr;',
        '    HostUse use;\n    return use && counters.initialized ? &platformFacts : nullptr;')
    text=once(text,'    failureOrdinal = ordinal;',
        '    HostUse use;\n    if (!use) return;\n    lock(); failureOrdinal = ordinal; unlock();')
    text += '\n'+(HERE/'retention-observers.inc').read_text()
    return text
def prepare(repo,output):
    raw=(repo/HOST).read_bytes()
    if sha(raw)!=PIN:raise ValueError('Production Host baseline changed')
    new=adapt(raw.decode()).encode()
    target=output/HOST;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(new)
    for relative in ['packages/nvidia-global-rm/src/S540NvidiaGlobalRm.h',
        'packages/nvidia-darwin-services/src/S540NvidiaDarwinServices.h',
        'packages/nvidia-os-adapter/upstream/include/nvtypes.h',
        'packages/nvidia-os-adapter/upstream/include/nvstatus.h',
        'packages/nvidia-os-adapter/upstream/include/nvstatuscodes.h',
        'packages/nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h',
        'packages/nvidia-os-adapter/upstream/include/cpuopsys.h']:
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((repo/relative).read_bytes())
    header=target=output/'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHostRetention.h'
    header.write_bytes((HERE/header.name).read_bytes())
    original={HOST:raw};changed={HOST:new}
    for name,expected in EXTRA_PINS.items():
        raw_extra=(repo/name).read_bytes()
        if sha(raw_extra)!=expected:raise ValueError('Refusal producer baseline changed: '+name)
        value=raw_extra.decode()
        if name==CRYPTO:
            value=once(value,'#include "S540NvidiaGlobalCrypto.h"',
                '#include "S540NvidiaGlobalCrypto.h"\n#include "S540NvidiaGspFirstTransaction.h"')
            value=once(value,'static void refuse(uint32_t symbol)\n{',
                'static void refuse(uint32_t symbol)\n{\n    s540FirstTxnObserveServiceRefusal(2, symbol, NV_ERR_NOT_SUPPORTED);')
            value=once(value,'__atomic_store_n(&counter_overflow, 1U, __ATOMIC_RELAXED);\n            return;',
                '__atomic_store_n(&counter_overflow, 1U, __ATOMIC_RELAXED);\n'
                '            s540FirstTxnObserveServiceRefusal(2, symbol, NV_ERR_NOT_SUPPORTED);\n            return;')
            value=once(value,'previous + 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED))\n            return;',
                'previous + 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {\n'
                '            s540FirstTxnObserveServiceRefusal(2, symbol, NV_ERR_NOT_SUPPORTED);\n            return;\n        }')
        else:
            value=once(value,'#include "nv_unsupported_memory.h"',
                '#include "nv_unsupported_memory.h"\n#include "S540NvidiaGspFirstTransaction.h"')
            value=once(value,'static NV_STATUS unavailable(void)\n{',
                'static NV_STATUS unavailable(void)\n{\n    s540FirstTxnObserveServiceRefusal(3, 0, NV_ERR_NOT_SUPPORTED);')
            value=once(value,'static __attribute__((noreturn)) void lifetimeUnavailable(const char *message)\n{',
                'static __attribute__((noreturn)) void lifetimeUnavailable(const char *message)\n{\n    s540FirstTxnObserveServiceRefusal(3, 1, NV_ERR_INVALID_STATE);')
            value=once(value,'bump(&statistics.unavailableOperationsEver);',
                'bump(&statistics.unavailableOperationsEver);\n    s540FirstTxnObserveServiceRefusal(3, 0, NV_ERR_NOT_SUPPORTED);')
            value=once(value,'bump(&statistics.lifetimeViolationsEver);',
                'bump(&statistics.lifetimeViolationsEver);\n    s540FirstTxnObserveServiceRefusal(3, 1, NV_ERR_INVALID_STATE);')
        original[name]=raw_extra;changed[name]=value.encode()
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(changed[name])
    patch=''.join(''.join(difflib.unified_diff(original[name].decode().splitlines(True),changed[name].decode().splitlines(True),
        fromfile='a/'+name,tofile='b/'+name)) for name in sorted(changed))
    (output/'host-heap-retention-prospective.patch').write_text(patch)
    manifest={'format':1,'profile':'isolated-host-heap-retention-not-admitted','original_sha256':{n:sha(v) for n,v in original.items()},
        'prospective_sha256':{n:sha(v) for n,v in changed.items()},'patch_sha256':sha(patch.encode()),'production_modified':False,
        'record_api':'strong exact owner/generation and atomic free permits',
        'capacity_records':8192,'single_limit_bytes':256*1024*1024,'total_limit_bytes':512*1024*1024,
        'pre_bind_retagging':False,'kernel_execution':'not_tested','original_entry_admission':False}
    (output/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh output directory')
    a.output.mkdir(parents=True);print(json.dumps(prepare(a.repo,a.output)))
