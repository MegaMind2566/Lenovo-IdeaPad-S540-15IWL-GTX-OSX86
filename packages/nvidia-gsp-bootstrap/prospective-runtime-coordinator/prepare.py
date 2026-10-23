#!/usr/bin/env python3
"""Separate retained experimental dispatch; legacy initialize remains closed."""
from pathlib import Path
import hashlib
import json
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DIRECTORY='packages/nvidia-gsp-bootstrap/prospective-runtime-coordinator'
BOOT='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
HEADER=BOOT[:-3]+'hpp'
LIFECYCLE='packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
ASSETS=DIRECTORY+'/S540ExperimentalAssets.cpp'
INPUTS=(BOOT,HEADER,LIFECYCLE)
ORIGINAL_INPUTS=()
COMPANIONS={DIRECTORY+'/'+name:HERE/name for name in
    ('S540ExperimentalRuntime.h','S540ExperimentalAssets.cpp')}
PROJECT_UNITS=({'source':ASSETS,'kind':'cpp'},)
EXPORTS={BOOT:('s540RuntimeRequireGlobalEntry',),
    ASSETS:('s540RuntimeReadCompiledProfile','s540RuntimeEmbeddedFirmware')}
COMPILE_DEFINITIONS={}
INCLUDE_DIRECTORIES=(DIRECTORY,)
SOURCE_FILES=('prepare.py','S540ExperimentalRuntime.h','S540ExperimentalAssets.cpp',
    'runtime-entry.cpp.inc','owner-methods.cpp.inc','facade-methods.cpp.inc',
    'profile.py','check.py','tests/check_runtime.cpp','tests/check_assets.cpp','SOURCE-CONTRACT.json')
KERNEL_REFUSAL='''#if defined(KERNEL)
    /* Final kernel stack/native/entry admission has not been established.
     * This immutable successor supplies the owner protocol, not that proof. */
    return out->startupStatus=NV_ERR_NOT_READY;
#endif'''
sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def once(text,before,after):
    if text.count(before)!=1:raise ValueError('Exact runtime coordinator anchor changed: '+before[:100])
    return text.replace(before,after)

def transforms(values):
    if set(values)!=set(INPUTS):raise ValueError('Exact runtime coordinator input set required')
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    expected=contract['input_sha256']
    if set(expected)!=set(INPUTS):raise ValueError('Frozen runtime coordinator input contract incomplete')
    if any(sha(values[name])!=expected[name] for name in INPUTS):
        raise ValueError('Frozen runtime coordinator prerequisite bytes changed')
    out=dict(values)
    boot=out[BOOT]
    start,end=function_span(boot,'initialize');closed_initialize=boot[start:end]
    boot=once(boot,'#include "S540NvidiaGspBootstrap.hpp"',
        '#include "S540NvidiaGspBootstrap.hpp"\n'
        '#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"\n'
        '#include "../prospective-first-transaction/services/S540NvidiaFirstTxnContext.h"')
    boot=once(boot,'enum Command : NvU32 { Prepare = 1, Initialize, Stop,',
        'enum Command : NvU32 { Prepare = 1, Initialize, ExperimentalInitialize, Stop,')
    boot=once(boot,'struct Owner::Impl {',
        'namespace {\n'+(HERE/'runtime-entry.cpp.inc').read_text()+'\n}\n\nstruct Owner::Impl {')
    boot=once(boot,'        case Initialize: status = self->initialize(); break;',
        '        case Initialize: status = self->initialize(); break;\n'
        '        case ExperimentalInitialize: status = self->experimentalInitialize(); break;')
    boot=once(boot,'    NV_STATUS initialize() {',
        (HERE/'owner-methods.cpp.inc').read_text()+'\n    NV_STATUS initialize() {')
    boot=once(boot,'NV_STATUS Owner::initialize() {',
        (HERE/'facade-methods.cpp.inc').read_text()+'\nNV_STATUS Owner::initialize() {')
    boot+='\nextern "C" NV_STATUS s540RuntimeRequireGlobalEntry(void) {\n'
    boot+='    return S540NvidiaGspBootstrap::runtimeGlobalEntry();\n}\n'
    start,end=function_span(boot,'initialize')
    if boot[start:end]!=closed_initialize:raise ValueError('Legacy initialize gate changed')
    out[BOOT]=boot
    header=out[HEADER]
    header=once(header,'class IOPCIDevice;',
        '#include "../prospective-runtime-coordinator/S540ExperimentalRuntime.h"\n\nclass IOPCIDevice;')
    header=once(header,'    NV_STATUS initialize();',
        '    // Explicit manual retained experiment; no production or release admission.\n'
        '    NV_STATUS experimentalInitialize(const S540ExperimentalRuntimeRequest &);\n'
        '    NV_STATUS cancelExperimental();\n'
        '    S540ExperimentalRuntimeSnapshot runtimeSnapshot() const;\n'
        '    NV_STATUS initialize();')
    out[HEADER]=header
    lifecycle=out[LIFECYCLE]
    lifecycle=once(lifecycle,'#include "S540NvidiaGspFirstTransaction.h"',
        '#include "S540NvidiaGspFirstTransaction.h"\n#include "S540ExperimentalRuntime.h"')
    lifecycle=once(lifecycle,KERNEL_REFUSAL,'''#if defined(KERNEL)
    /* Only the exact active retained experimental master can reach the same
     * original construction. Legacy Owner::initialize remains closed. */
    status=s540RuntimeRequireGlobalEntry();
    if(status!=NV_OK)return out->startupStatus=status;
#endif''')
    out[LIFECYCLE]=lifecycle
    return out
