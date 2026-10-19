#!/usr/bin/env python3
"""Generate a prospective statusful adapter patch from the pinned source.

This does not approve a new source profile, change the frozen ten-patch audit,
or establish that an original void engine destructor is safe to retry.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

OSINIT = 'src/nvidia/arch/nvalloc/unix/src/osinit.c'
OSAPI = 'src/nvidia/arch/nvalloc/unix/src/osapi.c'
HEADER = 'src/nvidia/arch/nvalloc/unix/include/osapi.h'
PINNED_HASHES = {
    OSINIT: 'dda3b014833c2e94680e5adea152011ffce72c8067782aceeecaefc28b7394d3',
    OSAPI: 'e4336f0e3bb55122680e0d344f970c123664122c2415134b7a6b517c98fcbe75',
    HEADER: '1c547039ccfa61deff34bc39bd0e733c0c33344cef6f2af5fc3775c80ee92cfd',
}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Pinned source context is not unique: ' + old[:90])
    return text.replace(old, new, 1)


def function(text, start, end):
    a = text.index(start)
    b = text.index(end, a)
    return a, b, text[a:b]


def adapt(original):
    result = dict(original)
    text = original[OSINIT]
    a, b, mapping = function(text, 'static void\nosInitNvMapping(', 'static NV_STATUS\nosInitScalability(')
    # Adapter admission is serialized by the API lock. This record covers the
    # interval where GPUMGR owns a device but NV_INIT_FLAG_GPUMGR_ATTACH has not
    # transferred that ownership to nv_priv yet. Failed cleanup is quarantined;
    # it must not be overwritten, forgotten, or retried by checked shutdown.
    pending = ('static struct {\n'
        '    nv_state_t *owner;\n    NvU32 gpuInstance;\n    NvU32 deviceInstance;\n'
        '} s540RmPendingDevice;\n\n'
        'static nv_state_t *s540RmGspAttemptOwner;\n\n'
        'static NV_STATUS s540RmCleanupPendingDevice(nv_state_t *nv)\n{\n'
        '    if (s540RmPendingDevice.owner != nv) return NV_ERR_INVALID_STATE;\n'
        '    NV_STATUS status = gpumgrDestroyDevice(s540RmPendingDevice.deviceInstance);\n'
        '    if (status != NV_OK) return status;\n'
        '    rmGpuLockFree(s540RmPendingDevice.gpuInstance);\n'
        '    portMemSet(&s540RmPendingDevice, 0, sizeof(s540RmPendingDevice));\n'
        '    return NV_OK;\n}\n\n')
    mapping = replace_once(mapping, '    // allocate the next available gpu device number',
        '    if (s540RmPendingDevice.owner != NULL) {\n'
        '        status->rmStatus = NV_ERR_STATE_IN_USE;\n'
        '        RM_SET_ERROR(*status, RM_INIT_GPU_GPUMGR_CREATE_DEV_FAILED);\n'
        '        return;\n    }\n\n'
        '    // allocate the next available gpu device number')
    mapping = replace_once(mapping, '    // init attach state',
        '    s540RmPendingDevice.owner = nv;\n'
        '    s540RmPendingDevice.gpuInstance = *pDeviceReference;\n'
        '    s540RmPendingDevice.deviceInstance = deviceInstance;\n\n'
        '    // init attach state')
    mapping = replace_once(mapping,
        '        // RM_BASIC_LOCK_MODEL: free GPU lock\n'
        '        rmGpuLockFree(*pDeviceReference);\n        return;\n    }\n\n'
        '    portMemSet(gpuAttachArg, 0, sizeof(GPUATTACHARG));',
        '        status->rmStatus = NV_ERR_NO_MEMORY;\n'
        '        NV_STATUS cleanupStatus = s540RmCleanupPendingDevice(nv);\n'
        '        if (cleanupStatus != NV_OK) status->rmStatus = cleanupStatus;\n'
        '        return;\n    }\n\n'
        '    portMemSet(gpuAttachArg, 0, sizeof(GPUATTACHARG));')
    mapping = replace_once(mapping, '        gpumgrDestroyDevice(deviceInstance);',
        '        NV_STATUS cleanupStatus = s540RmCleanupPendingDevice(nv);\n'
        '        if (cleanupStatus != NV_OK) status->rmStatus = cleanupStatus;')
    mapping = replace_once(mapping,
        '        NV_PRINTF(LEVEL_ERROR, "*** Cannot attach gpu\\n");\n'
        '        // RM_BASIC_LOCK_MODEL: free GPU lock\n'
        '        rmGpuLockFree(*pDeviceReference);',
        '        NV_PRINTF(LEVEL_ERROR, "*** Cannot attach gpu\\n");')
    mapping = replace_once(mapping, '    nvp->flags |= NV_INIT_FLAG_GPUMGR_ATTACH;',
        '    nvp->flags |= NV_INIT_FLAG_GPUMGR_ATTACH;\n'
        '    portMemSet(&s540RmPendingDevice, 0, sizeof(s540RmPendingDevice));')
    text = text[:a] + pending + mapping + text[b:]
    text = replace_once(text,
        '        status.rmStatus = kgspInitRm(pGpu, GPU_GET_KERNEL_GSP(pGpu), &gspFw);',
        '        if (s540RmGspAttemptOwner != NULL) {\n'
        '            status.rmStatus = NV_ERR_STATE_IN_USE;\n'
        '            RM_SET_ERROR(status, RM_INIT_FIRMWARE_INIT_FAILED);\n'
        '            goto shutdown;\n        }\n'
        '        s540RmGspAttemptOwner = nv;\n'
        '        status.rmStatus = kgspInitRm(pGpu, GPU_GET_KERNEL_GSP(pGpu), &gspFw);')

    a, b, body = function(text, 'static void RmUnixFreeRmApi(', 'static NvBool RmUnixAllocRmApi(')
    checked = body.replace('static void RmUnixFreeRmApi(', 'static NV_STATUS RmUnixFreeRmApiChecked(', 1)
    checked = replace_once(checked,
        '    if (rmGpuLocksAcquire(GPUS_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY) == NV_OK)\n    {',
        '    NV_STATUS status = rmGpuLocksAcquire(GPUS_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY);\n'
        '    if (status != NV_OK) return status;\n    {')
    checked = replace_once(checked,
        '            pRmApi->Free(pRmApi, nv->rmapi.hClient, nv->rmapi.hClient);',
        '            status = pRmApi->Free(pRmApi, nv->rmapi.hClient, nv->rmapi.hClient);\n'
        '            if (status != NV_OK) {\n'
        '                rmGpuLocksRelease(GPUS_LOCK_FLAGS_NONE, NULL);\n'
        '                return status;\n            }')
    checked = checked.rstrip()[:-1] + '    return NV_OK;\n}\n\n'
    text = text[:a] + checked + text[b:]
    a, b, allocation = function(text, 'static NvBool RmUnixAllocRmApi(', 'static NV_STATUS RmFetchGspRmImages')
    allocation = replace_once(allocation, '        return status;', '        return NV_FALSE;')
    allocation = replace_once(allocation, '    RmUnixFreeRmApi(nv);\n    return NV_FALSE;',
        '    // The sole RmInitAdapter caller owns the one checked shutdown.\n'
        '    // Preserve partial handles here; never perform a hidden first Free.\n'
        '    return NV_FALSE;')
    text = text[:a] + allocation + text[b:]
    a, b, dma = function(text, 'static void\nRmTeardownDeviceDma(', 'static void\nRmEnableDeviceClks(')
    dma = dma.replace('static void\nRmTeardownDeviceDma(', 'static NV_STATUS\nRmTeardownDeviceDma(', 1)
    dma = replace_once(dma,
        '        if (NV_OK == vmmGetVaspaceFromId(pVmm, nv->iovaspace_id, IO_VASPACE_A, &pIOVAS))\n        {\n            vmmDestroyVaspace(pVmm, pIOVAS);\n        }',
        '        NV_STATUS status = vmmGetVaspaceFromId(pVmm, nv->iovaspace_id, IO_VASPACE_A, &pIOVAS);\n'
        '        if (status != NV_OK) return status;\n'
        '        vmmDestroyVaspace(pVmm, pIOVAS);')
    dma = dma.rstrip()[:-1] + '    return NV_OK;\n}\n\n'
    text = text[:a] + dma + text[b:]

    a, b, body = function(text, 'void RmShutdownAdapter(', 'void RmPartiallyDisableAdapter(')
    body = body.replace('void RmShutdownAdapter(', 'NV_STATUS RmShutdownAdapterChecked(', 1)
    body = replace_once(body, '    NV_STATUS rmStatus;', '    NV_STATUS rmStatus = NV_OK;\n    NvBool gpuDetached = NV_FALSE;')
    body = replace_once(body, '\n    if ((pGpu != NULL)',
        '\n    if (s540RmPendingDevice.owner == nv) return NV_ERR_INVALID_STATE;\n'
        '    if (s540RmGspAttemptOwner == nv && !(nvp->flags & NV_INIT_FLAG_GPU_STATE))\n'
        '        return NV_ERR_NOT_READY;\n'
        '\n    if ((pGpu != NULL)')
    body = replace_once(body, '        NV_ASSERT_OK(gpumgrThreadEnableExpandedGpuVisibility());',
        '        rmStatus = gpumgrThreadEnableExpandedGpuVisibility();\n'
        '        if (rmStatus != NV_OK) return rmStatus;')
    body = replace_once(body, '        RmUnixFreeRmApi(nv);',
        '        rmStatus = RmUnixFreeRmApiChecked(nv);\n'
        '        if (rmStatus != NV_OK) goto visibility_done;')
    body = replace_once(body, '        if (!nv->is_external_gpu || serverLockAllClients(&g_resServ) == NV_OK)',
        '        if (nv->is_external_gpu) {\n'
        '            rmStatus = serverLockAllClients(&g_resServ);\n'
        '            if (rmStatus != NV_OK) goto visibility_done;\n        }\n        ')
    body = replace_once(body, '            if (rmGpuLocksAcquire(GPUS_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY) == NV_OK)',
        '            rmStatus = rmGpuLocksAcquire(GPUS_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY);\n'
        '            if (rmStatus == NV_OK)')
    body = replace_once(body, '                        teardownCoreLogic(pOS, pGpu);',
        '                        rmStatus = teardownCoreLogic(pOS, pGpu);\n'
        '                        if (rmStatus != NV_OK) goto gpu_unlock;\n'
        '                        nvp->flags &= ~NV_INIT_FLAG_CORE_LOGIC;')
    body = replace_once(body, '                        osTeardownScalability(pGpu);',
        '                        rmStatus = osTeardownScalability(pGpu);\n'
        '                        if (rmStatus != NV_OK) goto gpu_unlock;\n'
        '                        nvp->flags &= ~NV_INIT_FLAG_SCALABILITY;')
    body = replace_once(body, '                    NV_ASSERT(rmStatus == NV_OK);\n                }\n\n                if (nvp->flags & NV_INIT_FLAG_GPU_STATE)',
        '                    if (rmStatus != NV_OK) goto gpu_unlock;\n'
        '                    nvp->flags &= ~NV_INIT_FLAG_GPU_STATE_LOAD;\n'
        '                }\n\n                if (nvp->flags & NV_INIT_FLAG_GPU_STATE)')
    body = replace_once(body, '                    NV_ASSERT(rmStatus == NV_OK);\n                }\n\n                if (IS_DCE_CLIENT(pGpu))',
        '                    if (rmStatus != NV_OK) goto gpu_unlock;\n'
        '                    nvp->flags &= ~NV_INIT_FLAG_GPU_STATE;\n'
        '                }\n\n                if (IS_DCE_CLIENT(pGpu))')
    body = replace_once(body, '                        NV_PRINTF(LEVEL_ERROR, "DCE firmware RM Shutdown failure\\n");',
        '                        NV_PRINTF(LEVEL_ERROR, "DCE firmware RM Shutdown failure\\n");\n'
        '                        goto gpu_unlock;')
    body = replace_once(body, '                gpumgrDetachGpu(gpuInstance);\n                gpumgrDestroyDevice(deviceInstance);',
        '                rmStatus = gpumgrDetachGpu(gpuInstance);\n'
        '                if (rmStatus != NV_OK) goto gpu_unlock;\n'
        '                gpuDetached = NV_TRUE;\n'
        '                nvp->pGpu = NULL;\n'
        '                nvp->flags &= ~NV_INIT_FLAG_GPUMGR_ATTACH;\n'
        '                rmStatus = gpumgrDestroyDevice(deviceInstance);\n'
        '                if (rmStatus != NV_OK) goto gpu_unlock;')
    body = replace_once(body, '                    RmTeardownDeviceDma(nv);',
        '                    rmStatus = RmTeardownDeviceDma(nv);\n'
        '                    if (rmStatus != NV_OK) goto gpu_unlock;\n'
        '                    nvp->flags &= ~NV_INIT_FLAG_DMA;')
    body = replace_once(body, '                // UNLOCK: release GPUs lock', 'gpu_unlock:\n                // UNLOCK: release GPUs lock')
    body = replace_once(body, '                rmGpuLockFree(deviceInstance);',
        '                if (gpuDetached) rmGpuLockFree(deviceInstance);')
    body = replace_once(body, '        gpumgrThreadDisableExpandedGpuVisibility();',
        'visibility_done:\n        gpumgrThreadDisableExpandedGpuVisibility();')
    body = replace_once(body, '    else\n    {\n        RmClearPrivateState(nv);\n    }',
        '    else\n    {\n'
        '        if (pGpu != NULL || (nvp->flags & ~NV_INIT_FLAG_DMA) ||\n'
        '                nv->rmapi.hClient != 0) return NV_ERR_INVALID_STATE;\n'
        '        if (nvp->flags & NV_INIT_FLAG_DMA) {\n'
        '            rmStatus = RmTeardownDeviceDma(nv);\n'
        '            if (rmStatus != NV_OK) return rmStatus;\n'
        '            nvp->flags &= ~NV_INIT_FLAG_DMA;\n        }\n'
        '        RmClearPrivateState(nv);\n    }')
    body = replace_once(body, '    RmTeardownRegisters(nv);',
        '    if (rmStatus != NV_OK) return rmStatus;\n'
        '    rmStatus = RmTeardownRegisters(nv);\n'
        '    if (rmStatus == NV_OK && s540RmGspAttemptOwner == nv)\n'
        '        s540RmGspAttemptOwner = NULL;\n'
        '    return rmStatus;')
    body += 'void RmShutdownAdapter(nv_state_t *nv)\n{\n    (void)RmShutdownAdapterChecked(nv);\n}\n\n'
    text = text[:a] + body + text[b:]
    text = replace_once(text, '    RmShutdownAdapter(nv);\n\n failed:',
        '    // Preserve partial GPU/DMA/register ownership when cleanup fails.\n'
        '    if (s540GspCancellationBeginCleanupState(nv) != NV_OK) goto failed;\n'
        '    (void)RmShutdownAdapterChecked(nv);\n\n failed:')

    a, b, body = function(text, 'void RmDisableAdapter(', 'NV_STATUS RmGetAdapterStatus(')
    body = body.replace('void RmDisableAdapter(', 'NV_STATUS RmDisableAdapterChecked(', 1)
    body = replace_once(body, '    NV_STATUS  rmStatus;', '    NV_STATUS  rmStatus = NV_OK;')
    body = replace_once(body, '    if (pGpu == NULL)',
        '    if (s540RmGspAttemptOwner == nv && !(nvp->flags & NV_INIT_FLAG_GPU_STATE))\n'
        '        return NV_ERR_NOT_READY;\n\n    if (pGpu == NULL)')
    body = replace_once(body, '        return;', '        return NV_OK;')
    body = replace_once(body, '    if (!nv->is_external_gpu || serverLockAllClients(&g_resServ) == NV_OK)',
        '    if (nv->is_external_gpu) {\n'
        '        rmStatus = serverLockAllClients(&g_resServ);\n'
        '        if (rmStatus != NV_OK) goto instance_done;\n    }\n    ')
    body = replace_once(body, '        if (rmGpuLocksAcquire(GPUS_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY) == NV_OK)',
        '        rmStatus = rmGpuLocksAcquire(GPUS_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY);\n'
        '        if (rmStatus == NV_OK)')
    body = replace_once(body, '                teardownCoreLogic(pOS, pGpu);',
        '                rmStatus = teardownCoreLogic(pOS, pGpu);\n'
        '                if (rmStatus != NV_OK) goto disable_gpu_unlock;')
    body = replace_once(body, '                NV_ASSERT(rmStatus == NV_OK);\n                nvp->flags &= ~NV_INIT_FLAG_GPU_STATE_LOAD;',
        '                if (rmStatus == NV_OK) nvp->flags &= ~NV_INIT_FLAG_GPU_STATE_LOAD;')
    body = replace_once(body, '            // UNLOCK: release GPUs lock',
        'disable_gpu_unlock:\n            // UNLOCK: release GPUs lock')
    body = replace_once(body, '    gpumgrSetCurrentGpuInstance(NV_U32_MAX);',
        'instance_done:\n    gpumgrSetCurrentGpuInstance(NV_U32_MAX);\n    return rmStatus;')
    body += 'void RmDisableAdapter(nv_state_t *nv)\n{\n    (void)RmDisableAdapterChecked(nv);\n}\n\n'
    body += ('NvBool s540RmAdapterHasResources(nv_state_t *nv)\n{\n'
        '    nv_priv_t *nvp = NV_GET_NV_PRIV(nv);\n'
        '    return s540RmPendingDevice.owner == nv || s540RmGspAttemptOwner == nv ||\n'
        '        (nvp != NULL && (nvp->pGpu != NULL || nvp->flags != 0)) ||\n'
        '        nv->rmapi.hClient != 0 || (nv->regs != NULL && nv->regs->map != NULL);\n}\n\n')
    text = text[:a] + body + text[b:]
    result[OSINIT] = text

    text = original[HEADER]
    text = replace_once(text, 'void       RmShutdownAdapter      (nv_state_t *);',
        'NV_STATUS  s540GspCancellationBeginCleanupState(const void *);\n'
        'NV_STATUS  RmShutdownAdapterChecked(nv_state_t *);\n'
        'NV_STATUS  RmDisableAdapterChecked(nv_state_t *);\n'
        'void       RmShutdownAdapter      (nv_state_t *);')
    result[HEADER] = text

    text = original[OSAPI]
    a, b, body = function(text, 'void NV_API_CALL rm_disable_adapter(', 'NV_STATUS NV_API_CALL rm_exclude_adapter(')
    for name, upper in [('disable', 'Disable'), ('shutdown', 'Shutdown')]:
        body = replace_once(body, f'void NV_API_CALL rm_{name}_adapter(', f'NV_STATUS NV_API_CALL s540Rm{upper}AdapterChecked(')
    body = body.replace('    void      *fp;', '    void      *fp;\n    NV_STATUS  status = NV_OK;')
    body = body.replace('    threadStateInit(&threadState, THREAD_STATE_FLAGS_NONE);',
        '    threadStateInit(&threadState, THREAD_STATE_FLAGS_NONE);\n'
        '    status = s540GspCancellationBeginCleanupState(pNv);\n'
        '    if (status != NV_OK) goto runtime_done;')
    body = body.replace('    NV_ASSERT_OK(os_flush_work_queue(pNv->queue, NV_TRUE));',
        '    status = os_flush_work_queue(pNv->queue, NV_TRUE);\n'
        '    if (status != NV_OK) goto runtime_done;')
    body = body.replace('    if (rmapiLockAcquire(API_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY) == NV_OK)',
        '    status = rmapiLockAcquire(API_LOCK_FLAGS_NONE, RM_LOCK_MODULES_DESTROY);\n'
        '    if (status == NV_OK)')
    body = replace_once(body, '            RmPartiallyDisableAdapter(pNv);', '            status = NV_ERR_NOT_SUPPORTED;')
    body = replace_once(body, '            RmDisableAdapter(pNv);', '            status = RmDisableAdapterChecked(pNv);')
    body = replace_once(body, '        RmShutdownAdapter(pNv);', '        status = RmShutdownAdapterChecked(pNv);')
    # Do not replace the first failure with a later successful queue flush.
    body = replace_once(body, '    status = os_flush_work_queue(pNv->queue, NV_TRUE);\n    if (status != NV_OK) goto runtime_done;\n    threadStateFree',
        '    if (status == NV_OK) status = os_flush_work_queue(pNv->queue, NV_TRUE);\n'
        '    threadStateFree')
    body = body.replace('    threadStateFree(&threadState, THREAD_STATE_FLAGS_NONE);',
        'runtime_done:\n    threadStateFree(&threadState, THREAD_STATE_FLAGS_NONE);')
    # shutdown has no early queue failure, but shares the return discipline.
    body = body.replace('    NV_EXIT_RM_RUNTIME(sp,fp);\n}', '    NV_EXIT_RM_RUNTIME(sp,fp);\n    return status;\n}')
    body += ('void NV_API_CALL rm_disable_adapter(nvidia_stack_t *sp, nv_state_t *nv)\n'
        '{\n    (void)s540RmDisableAdapterChecked(sp, nv);\n}\n\n'
        'void NV_API_CALL rm_shutdown_adapter(nvidia_stack_t *sp, nv_state_t *nv)\n'
        '{\n    (void)s540RmShutdownAdapterChecked(sp, nv);\n}\n\n')
    text = text[:a] + body + text[b:]
    result[OSAPI] = text
    return result


def generate(upstream, output):
    paths = (OSINIT, OSAPI, HEADER)
    original = {p: (upstream / p).read_text() for p in paths}
    for path, data in original.items():
        if hashlib.sha256(data.encode()).hexdigest() != PINNED_HASHES[path]:
            raise ValueError('The pinned adapter source bytes changed: ' + path)
    modified = adapt(original)
    patch = ''.join(''.join(difflib.unified_diff(original[p].splitlines(True),
        modified[p].splitlines(True), fromfile='a/' + p, tofile='b/' + p)) for p in paths)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'adapter-status-unwind-prospective.patch').write_text(patch)
    sha = lambda data: hashlib.sha256(data.encode()).hexdigest()
    audit = {'format': 1, 'approved_profile': False, 'executable': False,
        'upstream_commit': '1a82fbfda8f321b056eb3568850f9316c5e465c5',
        'patch_sha256': sha(patch), 'sources': [{'path': p,
            'upstream_sha256': sha(original[p]), 'prospective_sha256': sha(modified[p])} for p in paths],
        'pending_device_ownership': {
            'serialization_requirement': 'Selected single-adapter init and shutdown under the original API lock.',
            'record': 'Exact nv_state owner, GPU instance and GPUMGR device instance between successful create and attach transfer.',
            'failed_destroy': 'Retain record and GPU lock; reject overwrite and checked shutdown; observer reports resources.',
            'retry_after_partial_destructive_failure_allowed': False},
        'rmapi_allocation': {
            'gpu_lock_failure_boolean': 'NV_FALSE, never a nonzero NV_STATUS success conversion.',
            'partial_handle_cleanup_owner': 'Sole RmInitAdapter caller performs one checked shutdown; allocator performs no hidden Free.'},
        'partial_gsp_attempt': {
            'record_point': 'Immediately before actual kgspInitRm; reject any existing attempt record.',
            'incomplete_gpu_state': 'Checked shutdown returns NOT_READY before freeing any RMAPI/core/GPU/DMA/register resources.',
            'record_clear_requirement': 'Complete checked shutdown success together with the separate required GSP status source profile.',
            'adapter_patch_alone_admits_gsp_shutdown': False,
            'failed_partial_attempt_retry_allowed': False},
        'limitations': ['Partial destructive cleanup is quarantined, not retryable.',
            'Original void engine destructors and DMA quiescence still require independent review.',
            'This patch alone does not establish safe PM completion or target-kernel admission.']}
    (output / 'ADAPTER-STATUS-AUDIT.json').write_text(json.dumps(audit, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.upstream, args.output)
