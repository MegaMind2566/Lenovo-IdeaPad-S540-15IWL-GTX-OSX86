#!/usr/bin/env python3
"""Compile fault controls around exact bodies emitted by the candidate generator.

Dependencies are explicit models; no original GPU/engine code or hardware runs.
This is prospective-patch control flow validation, not profile approval.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
GENERATOR = ROOT / 'packages/nvidia-gsp-bootstrap/adapter/generate_checked_unwind.py'
FIXTURE = Path(__file__).with_suffix('.c')


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def exact_function(text, prefix):
    start = text.index(prefix)
    brace = text.index('{', start)
    depth = 1
    pos = brace + 1
    while depth:
        if text[pos] == '{':
            depth += 1
        elif text[pos] == '}':
            depth -= 1
        pos += 1
    return text[start:pos] + '\n'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--checked-source', required=True, type=Path)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a fresh body-control output directory.')
    sys.path.insert(0, str(ROOT / 'builders'))
    import compile_nvidia_global_rm as original
    original.validate_checked_source(args.upstream, args.checked_source)
    generator_hash = digest(GENERATOR)
    fixture_hash = digest(FIXTURE)
    generator = module(GENERATOR)
    inputs = {p: (args.checked_source / p).read_text()
              for p in (generator.OSINIT, generator.OSAPI, generator.HEADER)}
    modified = generator.adapt(inputs)
    pending_start = modified[generator.OSINIT].index('static struct {\n    nv_state_t *owner;')
    pending_end = modified[generator.OSINIT].index('static void\nosInitNvMapping(', pending_start)
    pending = modified[generator.OSINIT][pending_start:pending_end]
    mapping = exact_function(modified[generator.OSINIT], 'static void\nosInitNvMapping(')
    mapping_prefix = mapping[:mapping.index('    pGpu = gpumgrGetGpu(*pDeviceReference);')]
    # The post-attach function tail is unchanged and requires actual GPU
    # objects. Retain the exact changed prefix through ownership transfer;
    # this is explicitly a prefix control, not a full mapping-function run.
    mapping_prefix += '}\n'
    init = exact_function(modified[generator.OSINIT], 'NvBool RmInitAdapter(')
    branch_start = init.index('    if (IS_GSP_CLIENT(pGpu))')
    branch_end = init.index('    else if (IS_DCE_CLIENT(pGpu))', branch_start)
    gsp_branch = ('static NV_STATUS s540TestExactGspInitBranch(nv_state_t *nv)\n{\n'
        '    OBJGPU *pGpu = NV_GET_NV_PRIV_PGPU(nv);\n'
        '    UNIX_STATUS status = {0};\n    int gspFw = 0;\n' +
        init[branch_start:branch_end] + '\nshutdown:\n    return status.rmStatus;\n}\n')
    selected = [(generator.OSINIT, prefix) for prefix in (
        'static NV_STATUS\nRmTeardownDeviceDma(',
        'static NV_STATUS RmUnixFreeRmApiChecked(', 'static NvBool RmUnixAllocRmApi(',
        'NV_STATUS RmShutdownAdapterChecked(',
        'NV_STATUS RmDisableAdapterChecked(', 'NvBool s540RmAdapterHasResources(')]
    selected += [(generator.OSAPI, prefix) for prefix in (
        'NV_STATUS NV_API_CALL s540RmDisableAdapterChecked(',
        'NV_STATUS NV_API_CALL s540RmShutdownAdapterChecked(')]
    bodies = pending + mapping_prefix + gsp_branch + ''.join(
        exact_function(modified[source], prefix) for source, prefix in selected)
    args.output.mkdir(parents=True)
    included = args.output / 'exact-prospective-bodies.inc'
    included.write_text(bodies)
    results = {}
    for name, flags in [('plain', []), ('sanitized', ['-fsanitize=address,undefined,function',
                        '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])]:
        binary = args.output / ('unwind-bodies-' + name)
        command = [args.cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-function', '-Wno-unused-variable', '-O1', '-g', *flags,
                   '-I', str(args.output), str(FIXTURE), '-o', str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True)
        (args.output / (name + '-compile.log')).write_text(compiled.stdout + compiled.stderr)
        compiled.check_returncode()
        executed = subprocess.run([str(binary)], capture_output=True, text=True)
        (args.output / (name + '-run.log')).write_text(executed.stdout + executed.stderr)
        executed.check_returncode()
        results[name] = json.loads(executed.stdout)
        assert results[name]['status'] == 'passed'
        assert results[name]['actual_changed_bodies'] and results[name]['modeled_dependencies']
        assert not results[name]['kernel_execution'] and not results[name]['gpu_access']
    if digest(GENERATOR) != generator_hash or digest(FIXTURE) != fixture_hash:
        raise ValueError('The generator or control fixture changed during the run.')
    report = {'format': 1, 'component': 'nvidia-prospective-adapter-unwind-body-controls',
              'status': 'passed', 'approved_profile': False, 'kernel_execution': False,
              'gpu_access': False, 'checked_input_profile': original.CHECKED_PROFILE,
              'generator_sha256': generator_hash, 'fixture_sha256': fixture_hash,
              'extracted_bodies_sha256': digest(included),
              'mapping_exact_changed_prefix': True,
              'mapping_post_attach_tail_executed': False,
              'exact_gsp_init_call_branch': True,
              'checked_input_sha256': {p: hashlib.sha256(text.encode()).hexdigest()
                                       for p, text in inputs.items()},
              'emitted_source_sha256': {p: hashlib.sha256(text.encode()).hexdigest()
                                        for p, text in modified.items()}, 'variants': results}
    (args.output / 'unwind-body-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
