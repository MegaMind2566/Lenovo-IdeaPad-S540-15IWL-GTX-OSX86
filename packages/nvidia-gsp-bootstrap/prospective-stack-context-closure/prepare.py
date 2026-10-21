#!/usr/bin/env python3
"""Keep original allocator algorithms, specialize actual same-TU global paths.

Exported generic ABI wrappers and their dynamic callback fallback are retained.
Only source-local common bodies carry an explicit always-inline requirement;
actual machine evidence, rather than that request, decides whether a global
path has lost its context-dependent generic indirect branch.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MEMORY = 'src/nvidia/src/libraries/nvport/memory/memory_tracking.c'
BASE_SHA256 = 'c27d0ac3576137f9d5c42703f51f4d473d9cfb733781d849acf22099f5c8187e'
INPUTS = ()
ORIGINAL_INPUTS = (MEMORY,)
COMPANIONS = {}
PROJECT_UNITS = ()
EXPORTS = {}
COMPILE_DEFINITIONS = {}
INCLUDE_DIRECTORIES = ()
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Exact global specialization anchor changed: ' + old[:100])
    return text.replace(old, new)


def change_function(text, name, transform):
    start, end = function_span(text, name)
    return text[:start] + transform(text[start:end]) + text[end:]


def transforms(values):
    if values:
        raise ValueError('No existing project source is changed.')
    return {}


def original_transforms(values):
    if set(values) != {MEMORY} or sha(values[MEMORY]) != BASE_SHA256:
        raise ValueError('Exact reviewed final allocator source required.')
    text = values[MEMORY]
    helpers = []
    for name, helper, result, arguments in (
            ('_portMemAllocatorAlloc', 's540StackAllocatorAllocBody', 'void *',
             'pAlloc, length PORT_MEM_CALLERINFO_COMMA_PARAM'),
            ('_portMemAllocatorFree', 's540StackAllocatorFreeBody', 'void', 'pAlloc, pMem')):
        start, end = function_span(text, name)
        old = text[start:end]
        signature = old[:old.index('{')]
        # The original body is moved byte-for-byte; its checks, tracking,
        # padding, limits, locks, OOM behavior and dynamic targets stay intact.
        helpers.append('static __attribute__((always_inline)) inline ' + result + '\n' +
                       old.replace(name, helper, 1) + '\n')
        wrapper = signature + '{\n    ' + ('return ' if result != 'void' else '') + helper + '(' + arguments + ');\n}\n'
        text = text[:start] + wrapper + text[end:]
    text = once(text, 'void *\nportMemAllocPaged\n', '\n'.join(helpers) + '\nvoid *\nportMemAllocPaged\n')
    for name in ('portMemAllocNonPaged', 'portMemAllocPaged'):
        text = change_function(text, name, lambda body: once(body,
            'return _portMemAllocatorAlloc(pAlloc, length PORT_MEM_CALLERINFO_COMMA_PARAM);',
            'return s540StackAllocatorAllocBody(pAlloc, length PORT_MEM_CALLERINFO_COMMA_PARAM);'))
    text = change_function(text, 'portMemFree', lambda body: once(once(body,
        'PORT_FREE(pHead->fence.pAllocator, pMem);',
        's540StackAllocatorFreeBody(pHead->fence.pAllocator, pMem);'),
        'PORT_FREE(portMemAllocatorGetGlobalPaged(), pMem);',
        's540StackAllocatorFreeBody(portMemAllocatorGetGlobalPaged(), pMem);'))
    # Every moved original body must still be exact; only its function name is
    # changed. There is no separate handwritten implementation to drift.
    for old_name, helper in (('_portMemAllocatorAlloc', 's540StackAllocatorAllocBody'),
                             ('_portMemAllocatorFree', 's540StackAllocatorFreeBody')):
        a, b = function_span(values[MEMORY], old_name)
        c, d = function_span(text, helper)
        if values[MEMORY][a:b].replace(old_name, helper, 1) != text[c:d]:
            raise ValueError('Original allocator algorithm changed during specialization.')
    return {MEMORY: text}


def prepare(source, output):
    source, output = source.resolve(strict=True), output.resolve()
    if output.exists():
        raise ValueError('Fresh stack specialization output required.')
    text = original_transforms({MEMORY: (source / MEMORY).read_text()})[MEMORY]
    destination = output / 'source' / MEMORY
    destination.parent.mkdir(parents=True)
    destination.write_text(text)
    record = {'format': 1, 'status': 'source-only-global-allocator-specialization',
        'input_sha256': BASE_SHA256, 'output_sha256': sha(text),
        'original_algorithm_bodies_unchanged': True, 'exported_generic_abi_unchanged': True,
        'dynamic_allocator_and_oom_barriers_retained': True,
        'kernel_stack_bound_proven': False, 'original_entry_admission': False,
        'hardware_admission': False, 'native_ci_requested': False}
    (output / 'stack-context-source.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), sort_keys=True))
