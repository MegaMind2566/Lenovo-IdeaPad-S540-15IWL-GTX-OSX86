#!/usr/bin/env python3
"""Opt-in exact-anchor public callout successor; frozen inputs are never edited."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
WORK = 'packages/nvidia-darwin-services/src/S540NvidiaDarwinWork.cpp'
TIMER = 'packages/nvidia-darwin-services/src/S540NvidiaDarwinTimer.cpp'
INPUTS = (WORK, TIMER)
HEADER = 'packages/nvidia-darwin-services/src/S540NvidiaPublicCallout.hpp'

def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Public callback successor requires one exact anchor: ' + old[:100])
    return source.replace(old, new, 1)

def common(source):
    source = replace(source, '#include <kern/thread_call.h>', '#include "S540NvidiaPublicCallout.hpp"')
    source = replace(source, '    thread_call_t call;', '    S540PublicCallout call;')
    return source

def work_overlay(source):
    source = common(source)
    source = replace(source,
        'void workCallback(thread_call_param_t queue, thread_call_param_t) { execute(static_cast<os_work_queue *>(queue)); }',
        'void workCallback(void *queue) { execute(static_cast<os_work_queue *>(queue)); }')
    source = replace(source,
        '    queue->call = thread_call_allocate_with_options(workCallback, queue, THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE);\n'
        '    if (queue->call == nullptr) { destroy(queue); return NV_ERR_NO_MEMORY; }',
        '    if (!queue->call.initialize(workCallback, queue)) { destroy(queue); return NV_ERR_NO_MEMORY; }')
    source = replace(source,
        '        // Preallocated call and ring: enqueue never allocates or sleeps.\n'
        '        (void)thread_call_enter(queue->call);',
        '        // The preallocated workloop signaler never sleeps or allocates.\n'
        '        AbsoluteTime deadline = 0;\n'
        '        clock_get_uptime(&deadline);\n'
        '        if (!queue->call.schedule(deadline)) violation("workqueue public callout invariant");')
    source = replace(source,
        '    // The drain can finish just before the callback returns. Wait for that\n'
        '    // return before freeing callback-owned queue storage.\n'
        '    (void)thread_call_cancel_wait(queue->call);',
        '    // Admission is closed and Guard released before taking the gate.\n'
        '    if (!queue->call.drain()) return NV_ERR_OPERATING_SYSTEM;')
    source = replace(source,
        '    if (!thread_call_free(queue->call)) violation("workqueue call still pending");',
        '    if (!queue->call.retire()) violation("workqueue public callout retirement");')
    return source

def timer_overlay(source):
    source = common(source)
    source = replace(source,
        '    (void)thread_call_enter_delayed(timer->call, deadline);',
        '    if (!timer->call.schedule(deadline)) violation("timer public callout invariant");')
    source = replace(source,
        'void timerCallback(thread_call_param_t timer, thread_call_param_t) { execute(static_cast<S540DarwinTimer *>(timer)); }',
        'void timerCallback(void *timer) { execute(static_cast<S540DarwinTimer *>(timer)); }')
    source = replace(source,
        '    timer->call = thread_call_allocate_with_options(timerCallback, timer, THREAD_CALL_PRIORITY_KERNEL, THREAD_CALL_OPTIONS_ONCE);\n'
        '    if (timer->call == nullptr) { destroy(timer); return NV_ERR_NO_MEMORY; }',
        '    if (!timer->call.initialize(timerCallback, timer)) { destroy(timer); return NV_ERR_NO_MEMORY; }')
    source = replace(source,
        '    (void)thread_call_cancel_wait(timer->call);',
        '    // cancelling prevents rearm while no Guard is held across the gate.\n'
        '    if (!timer->call.drain()) {\n'
        '        token = timer->guard.lock();\n'
        '        timer->cancelling = false;\n'
        '        timer->guard.unlock(token);\n'
        '        return NV_ERR_OPERATING_SYSTEM;\n'
        '    }')
    source = replace(source,
        '    if (!thread_call_free(timer->call)) violation("timer call still pending");',
        '    if (!timer->call.retire()) violation("timer public callout retirement");')
    return source

def transforms(inputs):
    if set(inputs) != set(INPUTS):
        raise ValueError('Public callback successor requires the exact Timer/Work source set')
    result = {WORK: work_overlay(inputs[WORK]), TIMER: timer_overlay(inputs[TIMER])}
    for name, source in result.items():
        if 'thread_call_' in source:
            raise ValueError('A direct thread-call dependency remains in ' + name)
    return result

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def prepare(source_root, output):
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(source_root) or source_root.is_relative_to(output):
        raise ValueError('A fresh output disjoint from inputs is required')
    inputs = {name: (source_root/name).read_text() for name in INPUTS}
    results = transforms(inputs)
    output.mkdir(parents=True)
    for name, source in results.items():
        target = output/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    target = output/HEADER
    shutil.copyfile(HERE/'S540NvidiaPublicCallout.hpp', target)
    value = {'format':1, 'profile':'public-callback-closure', 'production_modified':False,
        'hardware_admission':False, 'original_entry_admission':False,
        'sources':{name:{'input_sha256':digest(inputs[name]),
            'output_sha256':digest(results[name])} for name in INPUTS},
        'header_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (output/'source-hashes.json').write_text(json.dumps(value,indent=2)+'\n')
    return value

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    prepare(args.source_root,args.output)
