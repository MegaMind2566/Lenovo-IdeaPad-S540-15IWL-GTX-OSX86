#!/usr/bin/env python3
"""Capture actual attach/constructor failures without changing their outcomes."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-attach-failure-witness'
GPU = 'src/nvidia/src/kernel/gpu/gpu.c'
MANAGER = 'src/nvidia/src/kernel/gpu_mgr/gpu_mgr.c'
INPUTS = ()
ORIGINAL_INPUTS = (GPU, MANAGER)
HEADER = DIRECTORY + '/S540AttachFailureWitness.h'
UNIT = DIRECTORY + '/S540AttachFailureWitness.c'
COMPANIONS = {HEADER: HERE / 'S540AttachFailureWitness.h',
              UNIT: HERE / 'S540AttachFailureWitness.c'}
PROJECT_UNITS = ({'source': UNIT, 'kind': 'plain-c'},)
EXPORTS = {UNIT: ('s540AttachWitnessBegin', 's540AttachWitnessProgress',
    's540AttachWitnessChildProgress', 's540AttachWitnessChildFailure',
    's540AttachWitnessAttachFailure', 's540AttachWitnessComplete', 's540AttachWitnessRead')}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'check.py',
                'tests/check_witness.c.inc')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    result = {}
    for row in (HERE / 'BASE-SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', row)
        if match is None or match[2] in result:
            raise ValueError('Exact unique B7 original source hashes required')
        result[match[2]] = match[1]
    if set(result) != set(ORIGINAL_INPUTS):
        raise ValueError('Exactly the B7 GPU and manager sources are required')
    return result


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('The exact B7 witness source anchor changed: ' + before[:110])
    return text.replace(before, after)


def transformed_function(text, name, transform):
    first, last = function_span(text, name)
    return text[:first] + transform(text[first:last]) + text[last:]


def gpu_function(body):
    body = once(body, '    NV_STATUS                   status;',
        '    NV_STATUS                   status;\n'
        '    NvU32 witnessStage = S540_CTOR_CLASS_INFO;\n'
        '    NvU32 witnessMask = S540_ATTACH_OBS_GSP_CLIENT;\n'
        '    NvBool witnessMissing = NV_FALSE;')
    note = ('s540AttachWitnessChildFailure((pGpu ? pGpu->pOsGpuInfo : NULL), classId, instanceID, '
            'witnessStage, status, witnessMask, witnessMissing, IS_GSP_CLIENT(pGpu))')
    progress = ('s540AttachWitnessChildProgress((pGpu ? pGpu->pOsGpuInfo : NULL), classId, instanceID, witnessStage);')
    before = '''    NV_ASSERT_OK_OR_RETURN(
        _gpuChildNvocClassInfoGet(pGpu, classId, &pClassInfo));'''
    after = '''    s540AttachWitnessChildProgress((pGpu ? pGpu->pOsGpuInfo : NULL), classId, instanceID, witnessStage);
    status = _gpuChildNvocClassInfoGet(pGpu, classId, &pClassInfo);
    if (status != NV_OK)
        s540AttachWitnessChildFailure((pGpu ? pGpu->pOsGpuInfo : NULL), classId, instanceID,
            witnessStage, status, witnessMask, witnessMissing, IS_GSP_CLIENT(pGpu));
    NV_ASSERT_OK_OR_RETURN(status);'''
    body = once(body, before, after)
    body = once(body, '    status = objCreateDynamic(&pConcreteChild, pGpu, pClassInfo);',
        '    witnessStage = S540_CTOR_DYNAMIC_CREATE;\n    ' + progress + '\n'
        '    status = objCreateDynamic(&pConcreteChild, pGpu, pClassInfo);')
    body = once(body, '''    if (status != NV_OK)
    {
        return status;
    }
    NV_ASSERT_OR_RETURN(pConcreteChild != NULL, NV_ERR_INVALID_STATE);''',
        '''    if (status != NV_OK)
    {
        ''' + note + ''';
        return status;
    }
    witnessStage = S540_CTOR_CONCRETE_CHECK;
    ''' + progress + '''
    if (pConcreteChild == NULL)
        s540AttachWitnessChildFailure((pGpu ? pGpu->pOsGpuInfo : NULL), classId, instanceID,
            witnessStage, NV_ERR_INVALID_STATE, witnessMask, witnessMissing, IS_GSP_CLIENT(pGpu));
    NV_ASSERT_OR_RETURN(pConcreteChild != NULL, NV_ERR_INVALID_STATE);''')
    for stage, anchor in (
        ('S540_CTOR_CHILD_CAST', '    *ppChildPtr = objDynamicCastById(pConcreteChild, classId);'),
        ('S540_CTOR_ENGSTATE_CAST', '    pEngstate = dynamicCast(*ppChildPtr, OBJENGSTATE);'),
        ('S540_CTOR_BASE', '    status = engstateConstructBase(pEngstate, pGpu, engDesc);'),
        ('S540_CTOR_ENGINE', '    engstateLogStateTransitionPre(pEngstate, ENGSTATE_STATE_CONSTRUCT, &engTransitionData);')):
        body = once(body, anchor, '    witnessStage = ' + stage + ';\n    ' + progress + '\n' + anchor)
    body = once(body, '    status = engstateConstructEngine(pGpu, pEngstate, engDesc);',
        '    status = engstateConstructEngine(pGpu, pEngstate, engDesc);\n'
        '    if (status != NV_OK)\n        ' + note + ';')
    body = once(body, '    if (pEngstate->getProperty(pEngstate, PDB_PROP_ENGSTATE_IS_MISSING))',
        '    witnessStage = S540_CTOR_MISSING;\n    ' + progress + '\n'
        '    witnessMissing = pEngstate->getProperty(pEngstate, PDB_PROP_ENGSTATE_IS_MISSING);\n'
        '    witnessMask |= S540_ATTACH_OBS_MISSING;\n'
        '    if (witnessMissing)')
    body = once(body, '''    if (status != NV_OK)
    {
        (void)s540FirstTxnRequestDeferredCleanupGpu(pGpu, status);''',
        '''    if (status != NV_OK)
    {
        ''' + note + ''';
        (void)s540FirstTxnRequestDeferredCleanupGpu(pGpu, status);''')
    body = once(body, '    return status;\n}',
        '    s540AttachWitnessChildProgress((pGpu ? pGpu->pOsGpuInfo : NULL), classId, instanceID, S540_CTOR_COMPLETE);\n'
        '    return status;\n}')
    return body


def manager_function(body):
    nv = 'pAttachArg->pOsAttachArg'
    body = once(body, '    NvBool firstTxnVisibilityCaptured = NV_FALSE;',
        '    NvBool firstTxnVisibilityCaptured = NV_FALSE;\n'
        '    NvU32 witnessStage = S540_ATTACH_GPU_CREATE;')
    body = once(body, '    // create the new OBJGPU',
        '    s540AttachWitnessBegin(' + nv + ');\n\n    // create the new OBJGPU')
    for stage, anchor in (
        ('S540_ATTACH_GPU_CREATE', '    if ((status = _gpumgrCreateGpu(gpuInstance, pAttachArg)) != NV_OK)'),
        ('S540_ATTACH_DPC', '    if ((status = osDpcAttachGpu(pGpu, pAttachArg->pOsAttachArg)) != NV_OK)'),
        ('S540_ATTACH_OS', '    if ((status = osAttachGpu(pGpu, pAttachArg->pOsAttachArg)) != NV_OK)'),
        ('S540_ATTACH_CAPS', '    status = _gpumgrRegisterRmCapsForGpu(pGpu);'),
        ('S540_ATTACH_POST_CONSTRUCT', '    if ((status = gpuPostConstruct(pGpu, pAttachArg)) != NV_OK)'),
        ('S540_ATTACH_CONF_COMPUTE', '    status = _gpumgrDetermineConfComputeCapabilities(pGpuMgr, pGpu);')):
        body = once(body, anchor, '    witnessStage = ' + stage + ';\n'
            '    s540AttachWitnessProgress(' + nv + ', witnessStage);\n' + anchor)
    body = once(body, '''    gpumgrSetCurrentGpuInstance(prevGpuInst);

    return status;''',
        '''    gpumgrSetCurrentGpuInstance(prevGpuInst);
    s540AttachWitnessProgress(''' + nv + ''', S540_ATTACH_COMPLETE);
    s540AttachWitnessComplete(''' + nv + ''');

    return status;''')
    body = once(body, '    (void)s540FirstTxnOriginalGpuAttachFailed(pAttachArg->pOsAttachArg, status);',
        '    s540AttachWitnessAttachFailure(' + nv + ', witnessStage, status);\n'
        '    (void)s540FirstTxnOriginalGpuAttachFailed(pAttachArg->pOsAttachArg, status);')
    body = once(body, '''    if (firstTxnVisibilityCaptured)
        gpumgrSetCurrentGpuInstance(prevGpuInst);
    return status;''',
        '''    if (firstTxnVisibilityCaptured)
        gpumgrSetCurrentGpuInstance(prevGpuInst);
    s540AttachWitnessComplete(''' + nv + ''');
    return status;''')
    return body


def original_transforms(values):
    if set(values) != set(ORIGINAL_INPUTS):
        raise ValueError('Exactly the two reviewed B7 original inputs are required')
    result = {}
    for name, body in values.items():
        if hashlib.sha256(body.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('The exact B7 original input changed: ' + name)
        result[name] = once(body, '#include "S540NvidiaGspFirstTransactionOriginal.h"',
            '#include "S540NvidiaGspFirstTransactionOriginal.h"\n#include "S540AttachFailureWitness.h"')
    result[GPU] = transformed_function(result[GPU], 'gpuCreateObject', gpu_function)
    result[MANAGER] = transformed_function(result[MANAGER], 'gpumgrAttachGpu', manager_function)
    return result
