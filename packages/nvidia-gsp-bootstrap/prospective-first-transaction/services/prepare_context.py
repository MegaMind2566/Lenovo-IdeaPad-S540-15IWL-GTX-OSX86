#!/usr/bin/env python3
"""Typed context hooks, isolated from production and original source patches."""
from prepare_services import HERE, REPO, replace
import difflib, hashlib, json
from pathlib import Path

def prepare(output):
    original = REPO/'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
    source = original.read_text()
    if hashlib.sha256(source.encode()).hexdigest() != '9f8fee42cd2e9ffb2c86a0de368d259fa8879b70398becf7c508887dd941181f':
        raise ValueError('Real context input differs from pinned checkpoint')
    result = replace(source, '#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n#include "S540NvidiaFirstTxnContext.h"\n'
        '#include "S540NvidiaFirstTxnServices.h"')
    result = replace(result, '    NvU64 ownerThread;',
        '    NvU64 ownerThread;\n    NvU64 firstTxnGeneration;')
    for stack in ['DEVICE_WORK','GLOBAL_WORK']:
        old = f'    rm_execute_work_item(&context->stacks[{stack}], item);'
        result = replace(result, old, old+'''
    // Public original ABI is void. This notes only the actual wrapper return;
    // the strong record separately samples real failure counters.
    if (context->firstTxnGeneration)
        (void)s540FirstTxnWorkOriginalReturned(&context->nv, NV_OK);''')
    result = replace(result, '''    context->state.adapterAttempted = NV_TRUE;
    context->state.adapterInitialized = rm_init_adapter(&context->stacks[MAIN], &context->nv);''', '''    if (!context->firstTxnGeneration) return NV_ERR_NOT_SUPPORTED;
    profile = s540FirstTxnOriginalEnter(&context->nv);
    if (profile != NV_OK) { context->state.quarantined = NV_TRUE; return profile; }
    context->state.adapterAttempted = NV_TRUE;
    context->state.adapterInitialized = rm_init_adapter(&context->stacks[MAIN], &context->nv);
    // Only this outer C boundary can certify that the original public wrapper
    // has actually returned after its own ExitReady/unlock hook.
    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);
    if (profile != NV_OK) { context->state.quarantined = NV_TRUE; return profile; }''')
    result = replace(result, '''    if (!owner(context) || context->state.quarantined) return NV_ERR_INVALID_STATE;
    // Legacy destruction''', '''    if (!owner(context) || context->state.quarantined) return NV_ERR_INVALID_STATE;
    // This candidate intentionally has no final GSP/DMA/text release issuer.
    if (context->firstTxnGeneration) return NV_ERR_IN_USE;
    // Legacy destruction''')
    result += '''
NV_STATUS s540GspContextBindFirstTransaction(S540GspContext *context, S540GspCancellationToken token)
{
    S540FirstTxnSnapshot snapshot;
    NV_STATUS status;
    if (!owner(context) || !context->state.privateState || context->firstTxnGeneration ||
        context->state.adapterAttempted || context->state.quarantined)
        return NV_ERR_INVALID_STATE;
    status = s540FirstTxnBind(&context->nv, token);
    if (status != NV_OK) { context->state.quarantined = NV_TRUE; return status; }
    status = s540FirstTxnGetSnapshot(&context->nv, &snapshot);
    if (status != NV_OK) { context->state.quarantined = NV_TRUE; return status; }
    context->firstTxnGeneration = snapshot.generation;
    status = s540FirstTxnServicesBind(&context->nv, snapshot.generation,
        context->deviceQueue, context->globalQueue);
    if (status != NV_OK) context->state.quarantined = NV_TRUE;
    return status;
}
'''
    out = Path(output).resolve(); out.mkdir(parents=True,exist_ok=True)
    (out/'S540NvidiaGspContext.c').write_text(result)
    (out/'context-first-transaction.patch').write_text(''.join(difflib.unified_diff(
        source.splitlines(True),result.splitlines(True),
        fromfile='a/packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c',
        tofile='b/packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c')))
    (out/'context-source-hashes.json').write_text(json.dumps({
        'input_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'output_sha256':hashlib.sha256(result.encode()).hexdigest(),
        'production_modified':False,'owner_admission_integrated':False,
        'final_release_issuer':False},indent=2)+'\n')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output)
