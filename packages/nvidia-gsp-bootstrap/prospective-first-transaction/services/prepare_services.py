#!/usr/bin/env python3
"""Build isolated real service copies by exact source substitutions.

This never edits the repository or the approved prospective profile. Input and
output hashes are recorded beside the overlays, with no fuzz or silent edits.
"""
from pathlib import Path
import argparse, difflib, hashlib, json

HERE = Path(__file__).resolve().parent
REPO = next(x for x in HERE.parents if (x/'builders/check_nvidia_execution.py').is_file())
SERVICE = REPO / 'packages/nvidia-darwin-services/src'

def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Expected exactly one anchored substitution: ' + old[:100])
    return source.replace(old, new, 1)

def queue_overlay(source):
    source = replace(source, '#include "S540NvidiaDarwinInternal.hpp"',
        '#include "S540NvidiaDarwinInternal.hpp"\n'
        '#include "S540NvidiaFirstTxnServices.h"\n'
        '#include "S540NvidiaGspFirstTransaction.h"')
    source = replace(source, '    void *items[64];',
        '    const void *transactionNv;\n'
        '    NvU64 transactionGeneration;\n'
        '    NvU64 itemLeases[64];\n'
        '    void *retainedItems[65];\n'
        '    NvU64 retainedLeases[65];\n'
        '    NvU32 retainedCount;\n'
        '    NV_STATUS transactionFault;\n'
        '    bool callbackReturned, stopCompleted;\n'
        '    NvU64 stageSequence, stageThread;\n'
        '    NvU32 stage;\n'
        '    const void *stageData;\n'
        '    void *items[64];')
    source = replace(source, 'os_work_queue *globalQueue;', '''os_work_queue *globalQueue;
os_work_queue *transactionQueues[2];
void contextStage(os_work_queue *queue, NvU32 stage, const void *data) {
    // Writers hold the real queue guard. A synchronous hook's pull query must
    // not re-lock it. Atomic sequence rejects a torn/concurrent observation.
    __atomic_fetch_add(&queue->stageSequence, 1ULL, __ATOMIC_ACQ_REL);
    __atomic_store_n(&queue->stageThread, stage ? identity() : 0, __ATOMIC_RELAXED);
    __atomic_store_n(&queue->stageData, data, __ATOMIC_RELAXED);
    __atomic_store_n(&queue->stage, stage, __ATOMIC_RELAXED);
    __atomic_fetch_add(&queue->stageSequence, 1ULL, __ATOMIC_RELEASE);
}''')
    source = replace(source, '    if (!queue->accepting) { queue->guard.unlock(token); return NV_ERR_NOT_READY; }', '''    if (!queue->accepting) {
        if (queue->transactionNv) {
            contextStage(queue, S540_FIRST_SERVICE_ADMIT, data);
            (void)s540FirstTxnWorkRejected(queue->transactionNv, queue, data, NV_ERR_NOT_READY);
            contextStage(queue, 0, nullptr);
        }
        queue->guard.unlock(token); return NV_ERR_NOT_READY;
    }''')
    source = replace(source, '''    if (queue->count == 64 || queue->accepted == ~NvU64{0}) {
        queue->guard.unlock(token);''', '''    if (queue->count == 64 || queue->accepted == ~NvU64{0}) {
        if (queue->transactionNv) {
            contextStage(queue, S540_FIRST_SERVICE_ADMIT, data);
            (void)s540FirstTxnWorkRejected(queue->transactionNv, queue, data, NV_ERR_NO_MEMORY);
            contextStage(queue, 0, nullptr);
        }
        queue->guard.unlock(token);''')
    source = replace(source, '''extern "C" NV_STATUS s540DarwinUnbindGlobalWorkQueue(os_work_queue *queue) {
    if (queue == nullptr || !ordinary()) return NV_ERR_INVALID_ARGUMENT;''', '''extern "C" NV_STATUS s540DarwinUnbindGlobalWorkQueue(os_work_queue *queue) {
    if (queue == nullptr || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    if (queue->transactionNv) return NV_ERR_IN_USE;''')
    source = replace(source, '    queue->workerThread = identity();',
        '    queue->workerThread = identity();\n'
        '    queue->callbackReturned = false;')
    source = replace(source, '''        void *data = queue->items[queue->head];
        queue->items[queue->head] = nullptr;''', '''        void *data = queue->items[queue->head];
        const NvU64 lease = queue->itemLeases[queue->head];
        queue->itemLeases[queue->head] = 0;
        queue->items[queue->head] = nullptr;''')
    source = replace(source, '''        queue->guard.unlock(token);
        queue->action(queue->context, data);
        token = queue->guard.lock();
        ++queue->completed;''', '''        NV_STATUS status = queue->transactionFault;
        contextStage(queue, S540_FIRST_SERVICE_ENTER, data);
        if (status == NV_OK && queue->transactionNv)
            status = s540FirstTxnWorkEnter(queue->transactionNv, queue, data, lease);
        contextStage(queue, 0, nullptr);
        queue->guard.unlock(token);
        bool invoked = false;
        if (status == NV_OK) {
            // The original wrapper owns data. Its real return is the boundary:
            // it may have freed data, so completion never dereferences it.
            invoked = true;
            queue->action(queue->context, data);
        }
        token = queue->guard.lock();
        if (status == NV_OK && queue->transactionNv) {
            contextStage(queue, S540_FIRST_SERVICE_RETURNED, nullptr);
            status = s540FirstTxnWorkReturned(queue->transactionNv, queue, lease);
            contextStage(queue, 0, nullptr);
        }
        if (status != NV_OK) {
            // A failed entry keeps the original item. After an action return
            // only its pointer value is diagnostic: original done may have
            // retired it. Never dereference/free a presumed live payload.
            // Ring64 plus the one action already removed from its ring slot.
            if (queue->retainedCount == 65) violation("retained work capacity");
            queue->retainedItems[queue->retainedCount] = data;
            queue->retainedLeases[queue->retainedCount++] = lease;
            if (queue->transactionFault == NV_OK) queue->transactionFault = status;
            queue->accepting = false;
            if (queue->transactionNv) {
                contextStage(queue, invoked ? S540_FIRST_SERVICE_RETURNED : S540_FIRST_SERVICE_ENTER, data);
                (void)s540FirstTxnWorkRetain(queue->transactionNv, queue, lease, status);
                contextStage(queue, 0, nullptr);
            }
        } else ++queue->completed;''')
    source = replace(source, '    queue->scheduled = false;\n    queue->guard.wake(queue);',
        '    queue->scheduled = false;\n'
        '    queue->callbackReturned = true;\n'
        '    queue->guard.wake(queue);')
    source = replace(source, '    queue->accepting = true;',
        '    queue->accepting = true;\n    queue->callbackReturned = true;')
    source = replace(source, '    queue->items[(queue->head + queue->count) % 64] = data;', '''    NvU64 lease = 0;
    if (queue->transactionNv) {
        contextStage(queue, S540_FIRST_SERVICE_ADMIT, data);
        const NV_STATUS status = s540FirstTxnWorkAdmit(queue->transactionNv, queue, data, &lease);
        contextStage(queue, 0, nullptr);
        if (status != NV_OK) { queue->guard.unlock(token); return status; }
    }
    // Nothing after successful record admission can reject publication.
    queue->itemLeases[(queue->head + queue->count) % 64] = lease;
    queue->items[(queue->head + queue->count) % 64] = data;''')
    source = replace(source, '''    while (queue->completed < target) {
        if (!queue->guard.wait''', '''    while (queue->completed < target) {
        if (queue->transactionFault != NV_OK) {
            if (unload) --queue->unloadFlushes;
            const NV_STATUS status = queue->transactionFault;
            queue->guard.unlock(token); return status;
        }
        if (!queue->guard.wait''')
    source = replace(source, '''    (void)thread_call_cancel_wait(queue->call);
#endif
    return NV_OK;
}''', '''    (void)thread_call_cancel_wait(queue->call);
#endif
    token = queue->guard.lock();
    queue->stopCompleted = true;
    queue->guard.unlock(token);
    return NV_OK;
}''')
    source = replace(source, '''    if (queue == nullptr) return;
    if (__atomic_load_n(&globalQueue''', '''    if (queue == nullptr) return;
    // No transaction-final release/receipt exists in this candidate. Preserve
    // the exact queue identity and its callback text owner, even after drain.
    if (queue->transactionNv) return;
    if (__atomic_load_n(&globalQueue''')
    source += '''
/* These private operations authenticate the queue's actual binding. They do
 * not accept a caller-provided "drained" flag. No RM lock may be held while
 * Stop blocks. The strong transaction record enforces that caller boundary. */
extern "C" NV_STATUS s540FirstTxnQueueBind(os_work_queue *queue, const void *nv, NvU64 generation) {
    if (!queue || !nv || !generation || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    const auto token = queue->guard.lock();
    NV_STATUS status = NV_ERR_IN_USE;
    if (!queue->transactionNv && queue->accepting && !queue->accepted && !queue->scheduled) {
        // Publish immutable fields before the registry identity. A concurrent
        // rejected pull query must not race their initialization.
        queue->transactionNv = nv; queue->transactionGeneration = generation;
        for (NvU32 index = 0; index != 2; ++index) {
            os_work_queue *empty = nullptr;
            if (__atomic_compare_exchange_n(&transactionQueues[index], &empty, queue,
                    false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
                status = NV_OK; break;
            }
        }
    }
    queue->guard.unlock(token); return status;
}
extern "C" NV_STATUS s540FirstTxnQueueSeal(os_work_queue *queue, const void *nv, NvU64 generation) {
    if (!queue || !nv || !generation || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    const auto token = queue->guard.lock();
    NV_STATUS status = NV_ERR_INVALID_STATE;
    if (queue->transactionNv == nv && queue->transactionGeneration == generation) {
        queue->accepting = false; status = NV_OK;
    }
    queue->guard.unlock(token); return status;
}
extern "C" NV_STATUS s540FirstTxnQueueValidateStopped(os_work_queue *queue, const void *nv, NvU64 generation) {
    if (!queue || !nv || !generation || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    const auto token = queue->guard.lock();
    NV_STATUS status = NV_ERR_INVALID_STATE;
    if (queue->transactionNv == nv && queue->transactionGeneration == generation &&
        !queue->accepting && !queue->scheduled && !queue->workerThread &&
        queue->stopCompleted && queue->callbackReturned && !queue->count && !queue->retainedCount &&
        queue->transactionFault == NV_OK && queue->completed == queue->accepted)
        status = NV_OK;
    queue->guard.unlock(token); return status;
}
extern "C" NV_STATUS s540FirstTxnServicesReadQueueContext(const void *identity,
    S540FirstTxnServiceContext *output) {
    if (!identity || !output) return NV_ERR_INVALID_ARGUMENT;
    os_work_queue *queue = nullptr;
    for (NvU32 index = 0; index != 2; ++index) {
        auto *candidate = __atomic_load_n(&transactionQueues[index], __ATOMIC_ACQUIRE);
        if (candidate == identity) queue = candidate;
    }
    if (!queue) return NV_ERR_INVALID_STATE;
    const NvU64 sequence = __atomic_load_n(&queue->stageSequence, __ATOMIC_ACQUIRE);
    if (sequence & 1) return NV_ERR_IN_USE;
    S540FirstTxnServiceContext result = {};
    result.stage = __atomic_load_n(&queue->stage, __ATOMIC_RELAXED);
    result.thread = __atomic_load_n(&queue->stageThread, __ATOMIC_RELAXED);
    result.data = __atomic_load_n(&queue->stageData, __ATOMIC_RELAXED);
    result.generation = queue->transactionGeneration;
    if (!result.stage || !result.thread ||
        __atomic_load_n(&queue->stageSequence, __ATOMIC_ACQUIRE) != sequence)
        return NV_ERR_INVALID_STATE;
    *output = result; return NV_OK;
}
'''
    return source

def prepare(output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    source = (SERVICE/'S540NvidiaDarwinWork.cpp').read_text()
    if hashlib.sha256(source.encode()).hexdigest() != 'a7ca18cb6f9073d9a10d4ea0e04789c8f9009be820c1859ac66ad4e84c70e832':
        raise ValueError('Real queue input differs from pinned checkpoint')
    result = queue_overlay(source)
    out = output/'S540NvidiaDarwinWork.cpp'; out.write_text(result)
    patch = ''.join(difflib.unified_diff(source.splitlines(True),result.splitlines(True),
        fromfile='a/packages/nvidia-darwin-services/src/S540NvidiaDarwinWork.cpp',
        tofile='b/packages/nvidia-darwin-services/src/S540NvidiaDarwinWork.cpp'))
    (output/'work-first-transaction.patch').write_text(patch)
    (output/'source-hashes.json').write_text(json.dumps({
        'input_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'output_sha256':hashlib.sha256(result.encode()).hexdigest(),
        'production_modified':False,'hardware_admission':False},indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output)

if __name__ == '__main__': main()
