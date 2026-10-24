#!/usr/bin/env python3
"""Select one genuine OS MSI source in the exact retained B5 transport."""
from pathlib import Path
import hashlib
import re
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DIRECTORY='packages/nvidia-gsp-bootstrap/prospective-irq-source-selection'
DEVICE='packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp'
TRANSPORT='packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp'
BOOT='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
HEADER='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.hpp'
RUNTIME='packages/nvidia-gsp-bootstrap/prospective-runtime-coordinator/S540ExperimentalRuntime.h'
INPUTS=(DEVICE,TRANSPORT,BOOT,HEADER,RUNTIME)
ORIGINAL_INPUTS=()
COMPANIONS={}
PROJECT_UNITS=()
EXPORTS={}
INCLUDE_DIRECTORIES=()
COMPILE_DEFINITIONS={}
SOURCE_FILES=('BASE-SHA256SUMS','SOURCE-CONTRACT.json','read-mode.cpp.inc',
    'check.py','tests/check_irq.cpp.inc')
sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span
ROUTE_FIELDS=('sourceProbeAttempted','sourceProbeReturned','sourceProbeStatus',
    'sourceCount','sourcesObserved','messagedSources','selectedSourceValid','selectedSource',
    'selectedInterruptType','selectedTypeValid','inventoryValid','msiCapable','msixCapable','msiVectors')
def input_hashes():
    values={}
    for row in (HERE/'BASE-SHA256SUMS').read_text().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',row)
        if not match or match[2] in values:raise ValueError('Exact unique B5 source hashes required')
        values[match[2]]=match[1]
    if set(values)!=set(INPUTS):raise ValueError('Exact five B5 source prerequisites required')
    return values
BASE_SHA256=input_hashes()
def once(text,before,after):
    if text.count(before)!=1:raise ValueError('IRQ source-selection anchor changed: '+before[:100])
    return text.replace(before,after)
def replace_function(text,name,replacement):
    first,last=function_span(text,name)
    first=text.rfind('\n',0,first)+1
    return text[:first]+replacement.rstrip()+text[last:]
def transforms(values):
    if set(values)!=set(INPUTS):raise ValueError('The exact five B5 generated source files are required')
    if any(hashlib.sha256(values[name].encode()).hexdigest()!=digest for name,digest in BASE_SHA256.items()):
        raise ValueError('Frozen B5 IRQ/runtime source changed')
    result=dict(values);device=result[DEVICE]
    device=once(device,'    S540GspIrqModeFacts originalMode;','    S540GspIrqModeFacts originalMode;\n'
        '    NvU32 irqSource,irqSourceCount;\n    bool irqSourceValid;')
    device=replace_function(device,'readOriginalMode',(HERE/'read-mode.cpp.inc').read_text())
    device=once(device,'void interrupt(OSObject *,void *opaque,IOService *,int) {',
        'void interrupt(OSObject *,void *opaque,IOService *provider,int source) {')
    device=once(device,'    if(__atomic_load_n(&p->accepting,__ATOMIC_ACQUIRE)) {',
        '    if(!p->irqSourceValid||provider!=p->provider||source<0||static_cast<NvU32>(source)!=p->irqSource) {\n'
        '        s540FirstTxnObserveServiceRefusal(11,6,NV_ERR_INVALID_DATA);\n'
        '        __atomic_sub_fetch(&p->callbacks,1,__ATOMIC_ACQ_REL);return;\n'
        '    }\n    if(__atomic_load_n(&p->accepting,__ATOMIC_ACQUIRE)) {')
    for action,suffix in (('registerInterrupt',',p->owner,interrupt,p'),('enableInterrupt',''),
        ('disableInterrupt',''),('unregisterInterrupt','')):
        device=once(device,'p->provider->'+action+'(0'+suffix+')',
            'p->provider->'+action+'(static_cast<int>(p->irqSource)'+suffix+')')
    device=once(device,'    if(!p->controllerAttached||s540FirstTxnIrqCheckArm(p)!=NV_OK)return NV_ERR_INVALID_STATE;',
        '    if(!p->controllerAttached||!p->irqSourceValid||s540FirstTxnIrqCheckArm(p)!=NV_OK)return NV_ERR_INVALID_STATE;\n'
        '    S540GspIrqModeFacts currentMode{};\n'
        '    NV_STATUS routeStatus=readOriginalMode(p,currentMode);\n'
        '    if(routeStatus!=NV_OK)return routeStatus;')
    old='''    return InterruptStatistics{
        __atomic_load_n(&p->statistics.controllerCallbacks,__ATOMIC_ACQUIRE),
        __atomic_load_n(&p->statistics.rmHandledCallbacks,__ATOMIC_ACQUIRE),
        __atomic_load_n(&p->statistics.lockedBottomHalves,__ATOMIC_ACQUIRE),
        __atomic_load_n(&p->statistics.unlockedBottomHalves,__ATOMIC_ACQUIRE)};'''
    new='    InterruptStatistics result{};\n'
    for name in ('controllerCallbacks','rmHandledCallbacks','lockedBottomHalves','unlockedBottomHalves'):
        new+='    result.'+name+'=__atomic_load_n(&p->statistics.'+name+',__ATOMIC_ACQUIRE);\n'
    for name in ROUTE_FIELDS:new+='    result.'+name+'=p->statistics.'+name+';\n'
    device=once(device,old,new+'    return result;')
    result[DEVICE]=device
    result[TRANSPORT]=once(result[TRANSPORT],'    NvU64 unlockedBottomHalves;\n};',
        '    NvU64 unlockedBottomHalves;\n    // Ordinary-worker diagnostic observations; no readiness authority.\n'+
        ''.join('    NvU32 '+name+';\n' for name in ROUTE_FIELDS)+'};')
    result[HEADER]=once(result[HEADER],'    S540GspIrqInstallationSnapshot irqInstallation;',
        '    S540GspIrqInstallationSnapshot irqInstallation;\n'
        '    S540NvidiaDeviceTransport::InterruptStatistics irqSourceObservation;')
    boot=once(result[BOOT],'        result.irqInstallation = irqBinding.snapshot();',
        '        result.irqInstallation = irqBinding.snapshot();\n'
        '        result.irqSourceObservation = transport.interruptStatistics();')
    boot=once(boot,'        runtimeState.stage=stage;publishRuntime();',
        '        runtimeState.stage=stage;\n'
        '        if(stage!=S540_RUNTIME_FAILED)runtimeState.lastStage=stage;\n'
        '        publishRuntime();')
    boot=once(boot,'        if(runtimeState.firstStatus==NV_OK)runtimeState.firstStatus=status;',
        '        if(runtimeState.firstStatus==NV_OK) {\n'
        '            runtimeState.firstStatus=status;runtimeState.firstFailureStage=runtimeState.stage;\n        }')
    for bit,field,expression in ((0,'globalStatus','s540GlobalRmInitialize(&global)'),
        (1,'contextStatus','s540GspContextPrepare(context)'),
        (2,'bindStatus','s540GspContextBindFirstTransaction(context,token)'),
        (3,'irqStatus','installDiagnosticInterrupts()'),
        (4,'originalStatus','s540GspContextInitializeAdapter(context)')):
        call='        runtimeState.'+field+'='+expression+';'
        boot=once(boot,call,'        runtimeState.attemptedMask|=1U<<'+str(bit)+';\n'+call+
            '\n        runtimeState.returnedMask|=1U<<'+str(bit)+';')
    result[BOOT]=boot
    result[RUNTIME]=once(result[RUNTIME],'    NvU32 format, bytes, stage, firstStatus;',
        '    NvU32 format, bytes, stage, firstStatus;\n'
        '    NvU32 lastStage, firstFailureStage, attemptedMask, returnedMask;')
    return result
