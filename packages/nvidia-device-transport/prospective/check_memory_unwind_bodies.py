#!/usr/bin/env python3
"""Fault controls for exact complete pinned/candidate memory function bodies."""
from pathlib import Path
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cc', default='clang')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a fresh output directory.')
    spec = importlib.util.spec_from_file_location('memory_unwind', HERE / 'generate_memory_unwind.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    original = generator.load_pinned(args.upstream)
    modified = {generator.PHYSICAL: generator.adapt_physical(original[generator.PHYSICAL]),
                generator.VIRTUAL: generator.adapt_virtual(original[generator.VIRTUAL]),
                generator.PEER_BAR: generator.adapt_peer_bar(original[generator.PEER_BAR])}
    patches = {}
    for source, patch in ((generator.PHYSICAL, 'physical-import-publication-prospective.patch'),
                          (generator.VIRTUAL, 'indirect-peer-map-unwind-prospective.patch'),
                          (generator.PEER_BAR, 'peer-bar-borrowed-owner-prospective.patch')):
        expected = ''.join(difflib.unified_diff(original[source].splitlines(True),
            modified[source].splitlines(True), fromfile='a/' + source, tofile='b/' + source))
        if (HERE / patch).read_text() != expected:
            raise ValueError(f'Prospective patch differs from tested source: {patch}')
        patches[patch] = digest(HERE / patch)
    external = 'src/nvidia/src/kernel/mem_mgr/gpu_vaspace.c'
    external_text = (args.upstream / external).read_text()
    if hashlib.sha256(external_text.encode()).hexdigest() != '091272a127f93c1beaa56adaf5aa66d42213c6a6ca5a9b569fef9d5d0e5a165f':
        raise ValueError('External-root caller differs from pinned original.')
    # Verify that the actual outer catch destroys the unconditionally published
    # pointer, including after the real error goto of the import call.
    whole = generator.exact_function(external_text, 'NV_STATUS\ngvaspaceExternalRootDirCommit_IMPL\n(')
    assert 'NV_ASSERT_OR_GOTO(NV_OK == status, catch);' in whole
    catch = '        memdescDestroy(pRootMemNew);\n        pRootMemNew = NULL;'
    assert whole.count(catch) == 1
    catch_wrapper = ('\nstatic void exactExternalRootCatch(MEMORY_DESCRIPTOR **out)\n{\n'
        '    MEMORY_DESCRIPTOR *pRootMemNew = *out;\n' + catch + '\n    *out = pRootMemNew;\n}\n')
    prefixes = {generator.PHYSICAL: 'static NV_STATUS\nosCreateOsDescriptorFromPhysAddr\n(',
                generator.VIRTUAL: 'NV_STATUS\nvirtmemMapTo_IMPL\n(',
                generator.PEER_BAR: 'RmPhysAddr\nkbusSetupPeerBarAccess_IMPL\n('}
    args.output.mkdir(parents=True)
    results = {}
    for version, inputs in [('baseline', original), ('candidate', modified)]:
        directory = args.output / version
        directory.mkdir()
        included = directory / 'exact-memory-unwind-bodies.inc'
        included.write_text('\n\n'.join(generator.exact_function(inputs[p], prefix)
                            for p, prefix in prefixes.items()) + catch_wrapper)
        results[version] = {'extracted_bodies_sha256': digest(included), 'variants': {}}
        for mode, flags in [('plain', []), ('fatal-sanitizers', [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
            '-fno-omit-frame-pointer'])]:
            binary = directory / mode
            command = [args.cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter', *flags, '-I', str(directory),
                str(HERE / 'check_memory_unwind_bodies.c'), '-o', str(binary)]
            compilation = subprocess.run(command, capture_output=True, text=True)
            (directory / (mode + '-compile.log')).write_text(compilation.stdout + compilation.stderr)
            compilation.check_returncode()
            execution = subprocess.run([str(binary)], capture_output=True, text=True,
                env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
            (directory / (mode + '-run.log')).write_text(execution.stdout + execution.stderr)
            output = json.loads(execution.stdout)
            if version == 'candidate':
                execution.check_returncode()
                assert output['failures'] == 0 and output['status'] == 'passed'
            else:
                assert execution.returncode == 1 and output['failures'] > 0
            results[version]['variants'][mode] = output
    report = {'format': 1, 'component': 'nvidia-prospective-memory-unwind-body-controls',
        'status': 'passed', 'approved_profile': False, 'execution': 'native-user-space',
        'kernel_execution': 'not_tested', 'gpu_access': False,
        'original_source_sha256': {**generator.PINNED, external: hashlib.sha256(external_text.encode()).hexdigest()},
        'generator_sha256': digest(HERE / 'generate_memory_unwind.py'),
        'fixture_sha256': digest(HERE / 'check_memory_unwind_bodies.c'),
        'patch_sha256': patches,
        'full_function_bodies': list(prefixes.values()),
        'outer_catch_exact_fragment': True, 'modeled_dependencies': True,
        'results': results}
    (args.output / 'memory-unwind-body-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
