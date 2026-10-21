#!/usr/bin/env python3
"""Source-only, immutable original Context/Session IRQ installation successor."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT='packages/nvidia-gsp-bootstrap/prospective-irq-installation'
BOOT='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
HEADER=BOOT[:-3]+'hpp'
CONTEXT='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
CONTEXT_HEADER=CONTEXT[:-1]+'h'
BACKEND='packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp'
TRANSPORT='packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp'
INPUTS=(BOOT,HEADER,CONTEXT,CONTEXT_HEADER,BACKEND,TRANSPORT)
PRODUCTION_FILES=('prepare.py','S540NvidiaGspIrqIdentity.h','S540NvidiaGspIrqInstallation.hpp',
              'context-identity.c.inc','owner-methods.cpp.inc','backend-mode.cpp.inc')
SOURCE_FILES=(*PRODUCTION_FILES,'SOURCE-CONTRACT.json')
COMPANIONS={ROOT+'/'+name:HERE/name for name in ('S540NvidiaGspIrqIdentity.h','S540NvidiaGspIrqInstallation.hpp')}
PROJECT_UNITS=()
EXPORTS={CONTEXT:('s540GspContextReadIrqIdentity','s540GspContextMatchIrqIdentity',
                 's540GspContextSelectMessageInterrupt'),
         BOOT:('s540GspIrqInstallationCheckContext',),BACKEND:('s540GspIrqReadBackendMode',)}
COMPILE_DEFINITIONS={key:{'S540_NVIDIA_IRQ_INSTALLATION':'1'} for key in (BOOT,CONTEXT,BACKEND)}
INCLUDE_DIRECTORIES=(ROOT,)

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Exact IRQ installation anchor missing or ambiguous: '+old[:110])
    return text.replace(old,new)

def transforms(values):
    if set(values)!=set(INPUTS):raise ValueError('Exact IRQ installation source set required')
    for key,value in values.items():
        marker='(*selectMode)' if key==TRANSPORT else 'prospective-irq-installation/'
        if marker in value:raise ValueError('IRQ installation already selected: '+key)
    out=dict(values)
    boot=out[BOOT]
    boot=once(boot,'#include "S540NvidiaGspBootstrap.hpp"',
        '#include "S540NvidiaGspBootstrap.hpp"\n#include "../prospective-irq-installation/S540NvidiaGspIrqInstallation.hpp"')
    boot=once(boot,'Inspect, RetainDiagnosticLifetime, NativeActionCommand',
        'Inspect, RetainDiagnosticLifetime, InstallDiagnosticInterrupts, QuiesceDiagnosticInterrupts, NativeActionCommand')
    boot=once(boot,'    S540NvidiaDeviceTransport::Session transport;',
        '    S540NvidiaDeviceTransport::Session transport;\n    S540NvidiaGspIrq::Binding irqBinding;')
    boot=once(boot,'        case RetainDiagnosticLifetime: status = self->retainDiagnosticLifetime(); break;',
        '        case RetainDiagnosticLifetime: status = self->retainDiagnosticLifetime(); break;\n'
        '        case InstallDiagnosticInterrupts: status = self->installDiagnosticInterrupts(); break;\n'
        '        case QuiesceDiagnosticInterrupts: status = self->quiesceDiagnosticInterrupts(); break;')
    boot=once(boot,'        result.hardwareDmaGeneration = transport.hardwareDmaGeneration();',
        '        result.hardwareDmaGeneration = transport.hardwareDmaGeneration();\n        result.irqInstallation = irqBinding.snapshot();')
    boot=once(boot,'    NV_STATUS initialize() {',(HERE/'owner-methods.cpp.inc').read_text()+'\n    NV_STATUS initialize() {')
    boot=once(boot,'        if (diagnosticLifetimeHeld || transport.hardwareDmaLifetimeHeld()) {\n'
        '            state.quarantined = true; state.cleanupStatus = NV_ERR_IN_USE;',
        '        if (diagnosticLifetimeHeld || transport.hardwareDmaLifetimeHeld()) {\n'
        '            // Revoke/drain the actual IRQ producers on their retained owner worker.\n'
        '            // Full mask refusal is retained; it cannot acknowledge PM or release storage.\n'
        '            if (irqBinding.snapshot().installationAttempted) {\n'
        '                const NV_STATUS irq = irqBinding.quiesce();\n'
        '                if (irq != NV_OK) { state.quarantined = true; state.cleanupStatus = irq; return irq; }\n'
        '            }\n'
        '            state.quarantined = true; state.cleanupStatus = NV_ERR_IN_USE;')
    boot=once(boot,'NV_STATUS Owner::initialize() {',
        'NV_STATUS Owner::installDiagnosticInterrupts() {\n'
        '    return impl_ ? impl_->dispatcher.invoke(InstallDiagnosticInterrupts) : NV_STATUS(NV_ERR_INVALID_STATE);\n}\n'
        'NV_STATUS Owner::quiesceDiagnosticInterrupts() {\n'
        '    return impl_ ? impl_->dispatcher.invoke(QuiesceDiagnosticInterrupts) : NV_STATUS(NV_ERR_INVALID_STATE);\n}\n'
        'NV_STATUS Owner::initialize() {')
    boot+='\nextern "C" NV_STATUS s540GspIrqInstallationCheckContext(S540GspContext *context) {\n'
    boot+='    return S540NvidiaGspIrq::Binding::checkInstalled(context);\n}\n'
    out[BOOT]=boot
    header=out[HEADER]
    header=once(header,'#include "../../nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp"',
        '#include "../../nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp"\n'
        '#include "../prospective-irq-installation/S540NvidiaGspIrqIdentity.h"')
    header=once(header,'    NvU64 hardwareDmaGeneration;','    NvU64 hardwareDmaGeneration;\n    S540GspIrqInstallationSnapshot irqInstallation;')
    header=once(header,'    NV_STATUS retainDiagnosticLifetime();','    NV_STATUS retainDiagnosticLifetime();\n'
        '    // Explicit worker operations; they do not admit Owner::initialize or original entry.\n'
        '    NV_STATUS installDiagnosticInterrupts();\n    NV_STATUS quiesceDiagnosticInterrupts();')
    out[HEADER]=header
    context=out[CONTEXT]
    context=once(context,'#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n#include "../prospective-irq-installation/S540NvidiaGspIrqIdentity.h"')
    context=once(context,'    profile = s540GlobalRmFeatureProfilePreflight(&context->nv);',
        '    profile = s540GspIrqInstallationCheckContext(context);\n    if (profile != NV_OK) return profile;\n'
        '    profile = s540GlobalRmFeatureProfilePreflight(&context->nv);')
    context+='\n'+(HERE/'context-identity.c.inc').read_text()
    out[CONTEXT]=context
    out[CONTEXT_HEADER]=once(out[CONTEXT_HEADER],'#include "S540NvidiaGspDmaStop.h"',
        '#include "S540NvidiaGspDmaStop.h"\n#include "../prospective-irq-installation/S540NvidiaGspIrqIdentity.h"')
    out[TRANSPORT]=once(out[TRANSPORT],
        '    const void *originalState; // exact immutable nv_state_t, required by IRQ participant',
        '    const void *originalState; // exact immutable nv_state_t, required by IRQ participant\n'
        '    NV_STATUS (*selectMode)(void *context); // pulls actual registered backend facts before registration\n'
        '    NV_STATUS (*validateBinding)(void *context); // exact immutable Context/original identity')
    backend=out[BACKEND]
    backend=once(backend,'#include "S540NvidiaDeviceTransport.hpp"',
        '#include "S540NvidiaDeviceTransport.hpp"\n'
        '#include "../../nvidia-gsp-bootstrap/prospective-irq-installation/S540NvidiaGspIrqIdentity.h"')
    backend=once(backend,'    InterruptContract interrupt;','    InterruptContract interrupt;\n    S540GspIrqModeFacts originalMode;')
    backend=once(backend,'void bottomHalf(void *parameter) {',(HERE/'backend-mode.cpp.inc').read_text()+'\nvoid bottomHalf(void *parameter) {')
    backend=once(backend,'        if(work&1U) {',
        '        const NV_STATUS binding=p->interrupt.validateBinding(p->interrupt.context);\n'
        '        if(binding!=NV_OK) {\n'
        '            s540FirstTxnObserveServiceRefusal(11,4,binding);\n'
        '            __atomic_fetch_or(&p->pending,work,__ATOMIC_RELEASE);\n'
        '            (void)s540FirstTxnIrqLeave(p,S540_FIRST_IRQ_BOTTOM);\n'
        '            __atomic_store_n(&p->bottomStage,0U,__ATOMIC_RELEASE);return;\n'
        '        }\n        if(work&1U) {')
    backend=once(backend,'            bool locked=false,unlocked=false;',
        '            const NV_STATUS binding=p->interrupt.validateBinding(p->interrupt.context);\n'
        '            if(binding==NV_OK) {\n            bool locked=false,unlocked=false;')
    backend=once(backend,'            (void)s540FirstTxnIrqLeave(p,S540_FIRST_IRQ_TOP);',
        '            } else s540FirstTxnObserveServiceRefusal(11,5,binding);\n'
        '            (void)s540FirstTxnIrqLeave(p,S540_FIRST_IRQ_TOP);')
    backend=once(backend,'       !contract.maskHardware||!contract.readyToArm)return NV_ERR_NOT_SUPPORTED;',
        '       !contract.maskHardware||!contract.readyToArm||!contract.selectMode||!contract.validateBinding)return NV_ERR_NOT_SUPPORTED;')
    backend=once(backend,'    int type=0;\n    if(p->provider->getInterruptType(0,&type)!=kIOReturnSuccess)return NV_ERR_NOT_SUPPORTED;',
        '    S540GspIrqModeFacts mode{};\n    NV_STATUS modeStatus=readOriginalMode(p,mode);\n'
        '    if(modeStatus!=NV_OK)return modeStatus;')
    backend=once(backend,'    __atomic_store_n(&registeredIrqBackend,p,__ATOMIC_RELEASE);',
        '    mode.nv=contract.originalState;mode.generation=p->irqGeneration;p->originalMode=mode;\n'
        '    __atomic_store_n(&registeredIrqBackend,p,__ATOMIC_RELEASE);\n'
        '    const NV_STATUS selected=contract.selectMode(contract.context);\n'
        '    if(selected!=NV_OK){rememberIrqBackend(p);return selected;}')
    backend=once(backend,'extern "C" NV_STATUS s540FirstTxnIrqReadContext(',
        'extern "C" NV_STATUS s540GspIrqReadBackendMode(const void *nv,S540GspIrqModeFacts *out) {\n'
        '    Platform *p=__atomic_load_n(&registeredIrqBackend,__ATOMIC_ACQUIRE);\n'
        '    if(!out||!nv||!p||p->interrupt.originalState!=nv||p->originalMode.nv!=nv) return NV_ERR_INVALID_STATE;\n'
        '    *out=p->originalMode;return NV_OK;\n}\n\n'
        'extern "C" NV_STATUS s540FirstTxnIrqReadContext(')
    out[BACKEND]=backend
    return out
