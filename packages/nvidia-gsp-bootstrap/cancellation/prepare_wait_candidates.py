#!/usr/bin/env python3
"""Isolated prospective edits; never mutates the checked original profile.

The generated fixture includes complete actual wait bodies with explicit
hardware/event fixtures. It does not emulate an adapter or prove PM admission.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

SOURCES = {
    'src/nvidia/src/kernel/gpu/gpu_timeout.c':
        '44846405878a31c8b9ee48be8d201f1f08d3a8383d26f3303284fa253c86a6ce',
    'src/nvidia/src/kernel/gpu/falcon/arch/turing/kernel_falcon_tu102.c':
        'a4d4f25fc0fb4a686194ddb292649421ba7732144c6e1e6c820ab1928579c41c',
    'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c':
        'ed6d7020a8a1772bc44608178aa13a77a72b8bf0eabe3293c12bc9d2b122c6c9',
    'src/nvidia/src/kernel/gpu/gsp/message_queue_cpu.c':
        'de4371a1734b72dd6109da1f055ea170f4b0bd6778d13c62f5b430ac13052f51',
}

def function_span(text: str, name: str) -> tuple[int, int]:
    for match in re.finditer(r'\b' + re.escape(name) + r'\s*\(', text):
        # A function definition's close parenthesis is followed by its body.
        depth = 1
        end = match.end()
        while depth:
            depth += (text[end] == '(') - (text[end] == ')')
            end += 1
        while text[end].isspace(): end += 1
        if text[end] != '{': continue
        begin, depth = end, 1
        token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
        for item in token.finditer(text, begin + 1):
            if item.group() == '{': depth += 1
            if item.group() == '}': depth -= 1
            if not depth: return match.start(), item.end()
    raise ValueError('Original function definition missing: ' + name)

def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('Prospective boundary changed: ' + old[:100])
    return text.replace(old, new, 1)

def edit_function(text: str, name: str, changes: list[tuple[str, str]]) -> str:
    start, end = function_span(text, name)
    body = text[start:end]
    for old, new in changes: body = replace_once(body, old, new)
    return text[:start] + body + text[end:]

def prepare(upstream: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    originals = {}
    for rel, expected in SOURCES.items():
        raw = (upstream / rel).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Pinned original digest mismatch: ' + rel)
        originals[rel] = raw.decode()
    proposed = dict(originals)
    timeout, falcon, gsp, queue = SOURCES
    proposed[timeout] = edit_function(proposed[timeout], 'timeoutCondWait', [(
        '    while (!pCondFunc(pGpu, pCondData))\n    {',
        '    for (;;)\n    {\n'
        '        status = s540GspCancellationCheckGpu(pGpu);\n'
        '        if (status != NV_OK) break;\n'
        '        if (pCondFunc(pGpu, pCondData)) break;')])
    proposed[falcon] = edit_function(proposed[falcon], 'kflcnWaitForHalt_TU102', [(
        '    while (!FLD_TEST_DRF(_PFALCON, _FALCON, _CPUCTL_HALTED, _TRUE,\n'
        '                         kflcnRegRead_HAL(pGpu, pKernelFlcn, NV_PFALCON_FALCON_CPUCTL)))\n    {',
        '    for (;;)\n    {\n'
        '        status = s540GspCancellationCheckGpu(pGpu);\n'
        '        if (status != NV_OK) break;\n'
        '        if (FLD_TEST_DRF(_PFALCON, _FALCON, _CPUCTL_HALTED, _TRUE,\n'
        '                kflcnRegRead_HAL(pGpu, pKernelFlcn, NV_PFALCON_FALCON_CPUCTL))) break;'), (
        '        if (status == NV_ERR_TIMEOUT)', '        if (status != NV_OK)')])
    proposed[gsp] = edit_function(proposed[gsp], '_kgspRpcDrainEvents', [(
        '    while (nvStatus == NV_OK)\n    {',
        '    while (nvStatus == NV_OK)\n    {\n'
        '        nvStatus = s540GspCancellationCheckGpu(pGpu);\n'
        '        if (nvStatus != NV_OK) return nvStatus;')])
    proposed[gsp] = edit_function(proposed[gsp], 'kgspRecvPoll_IMPL', [(
        '        timeoutStatus = gpuCheckTimeout(pGpu, &timeout);',
        '        rpcStatus = s540GspCancellationCheckGpu(pGpu);\n'
        '        if (rpcStatus != NV_OK) goto done;\n'
        '        timeoutStatus = gpuCheckTimeout(pGpu, &timeout);')])
    proposed[gsp] = edit_function(proposed[gsp], '_kgspBootGspRm', [(
        '    *pbRetry = NV_FALSE;',
        '    *pbRetry = NV_FALSE;\n'
        '    status = s540GspCancellationCheckGpu(pGpu);\n'
        '    if (status != NV_OK) return status;'), (
        '    if (status != NV_OK && !pGpu->pGpuArch->bGpuArchIsZeroFb)',
        '    if (status != NV_OK && status != NV_ERR_OPERATION_ABORTED &&\n'
        '        !pGpu->pGpuArch->bGpuArchIsZeroFb)')])
    proposed[gsp] = edit_function(proposed[gsp], 'kgspInitRm_IMPL', [(
        '    do\n    {\n        // Reset the thread state timeout',
        '    do\n    {\n'
        '        status = s540GspCancellationCheckGpu(pGpu);\n'
        '        if (status != NV_OK) goto done;\n'
        '        // Reset the thread state timeout'), (
        '    } while (bRetry && (pKernelGsp->bootAttempts < maxGspBootAttempts));',
        '    } while (status != NV_ERR_OPERATION_ABORTED && bRetry &&\n'
        '             (pKernelGsp->bootAttempts < maxGspBootAttempts));')])
    proposed[queue] = edit_function(proposed[queue], 'GspStatusQueueInit', [(
        '    for (nRetries = 0; ; nRetries++)\n    {',
        '    for (nRetries = 0; ; nRetries++)\n    {\n'
        '        nvStatus = s540GspCancellationCheckGpu(pGpu);\n'
        '        if (nvStatus != NV_OK) break;')])
    patch = []
    for rel, text in proposed.items():
        first_include = text.index('#include ')
        text = text[:first_include] + '#include "S540NvidiaGspCancellationOriginal.h"\n' + text[first_include:]
        proposed[rel] = text
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
        patch.extend(difflib.unified_diff(originals[rel].splitlines(True),
            text.splitlines(True), fromfile='a/' + rel, tofile='b/' + rel))
    (output / 'wait-cancellation-prospective.patch').write_text(''.join(patch))
    fixtures = []
    for rel, name, result in [(timeout, 'timeoutCondWait', 'NV_STATUS'),
            (falcon, 'kflcnWaitForHalt_TU102', 'NV_STATUS'),
            (gsp, '_kgspRpcDrainEvents', 'static NV_STATUS'),
            (queue, 'GspStatusQueueInit', 'NV_STATUS')]:
        begin, end = function_span(proposed[rel], name)
        fixtures.append(result + '\n' + proposed[rel][begin:end] + '\n')
    (output / 'original_wait_bodies.inc').write_text('\n'.join(fixtures))
    record = {'format': 1, 'profile': 'isolated-prospective-not-composed',
        'upstream_commit': '1a82fbfda8f321b056eb3568850f9316c5e465c5',
        'original_sha256': SOURCES,
        'prospective_sha256': {rel: hashlib.sha256(text.encode()).hexdigest()
                               for rel, text in proposed.items()},
        'fixture_functions': ['timeoutCondWait', 'kflcnWaitForHalt_TU102',
                             '_kgspRpcDrainEvents', 'GspStatusQueueInit'],
        'original_entry_admission': False, 'kernel_execution': 'not_tested'}
    (output / 'wait-cancellation-prospective.json').write_text(json.dumps(record, indent=2) + '\n')
    return record

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.upstream, args.output), indent=2))
