#!/usr/bin/env python3
"""Compile the prospective adapter changes against a verified ten-overlay tree."""
import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'builders'))
import compile_nvidia_global_rm as original


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(args):
    native = sys.platform == 'darwin' and platform.machine() == 'x86_64'
    if not native and not args.cross_probe:
        raise ValueError('Authoritative compilation requires Intel macOS; cross probes are explicit.')
    baseline = original.validate_checked_source(args.upstream, args.checked_source)
    namespace = args.namespace.resolve(strict=True)
    if args.output.exists():
        raise ValueError('Use a fresh prospective output directory.')
    args.output.mkdir(parents=True)
    generator = ROOT / 'packages/nvidia-gsp-bootstrap/adapter/generate_checked_unwind.py'
    spec = importlib.util.spec_from_file_location('checked_unwind_generator', generator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = args.output / 'source'
    shutil.copytree(args.checked_source, source)
    paths = (module.OSINIT, module.OSAPI, module.HEADER)
    inputs = {p: (source / p).read_text() for p in paths}
    changed = module.adapt(inputs)
    for path, value in changed.items():
        (source / path).write_text(value)
    flags = original.original_bridge_flags(args.upstream, args.output, args.cc,
        namespace, checked_source=args.checked_source)
    flags = [f.replace(str(args.checked_source.resolve()), str(source.resolve())) for f in flags]
    flags += ['-Werror=implicit-function-declaration', '-Werror=return-type',
        '-Wframe-larger-than=4096', '-Werror=frame-larger-than']
    flags += (['-target', 'x86_64-macos-none', '-fPIC'] if args.cross_probe else
        ['-mkernel', '-arch', 'x86_64', '-mmacosx-version-min=15.0'])
    records = []
    for unit in ('osinit', 'osapi'):
        path = source / ('src/nvidia/arch/nvalloc/unix/src/' + unit + '.c')
        obj = args.output / (unit + '.o')
        command = [str(args.cc), *flags, '-c', str(path), '-o', str(obj)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=180)
        (args.output / (unit + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise ValueError(unit + ' prospective compilation failed: ' + result.stderr[-6000:])
        # The parser rejects original initializer/finalizer sections itself.
        defined, undefined, sections = original.macho_symbols(obj)
        records.append({'source': path.relative_to(source).as_posix(),
            'source_sha256': sha(path.read_bytes()), 'object': obj.name,
            'object_sha256': sha(obj.read_bytes()), 'command': command,
            'definitions': len(defined), 'imports': len(undefined), 'sections': sections})
    report = {'format': 1, 'status': 'passed', 'production_candidate_allowed': False,
        'approved_profile': False, 'native_apple_compiler': native and not args.cross_probe,
        'cross_compile_probe': args.cross_probe, 'kernel_execution': 'not_tested',
        'gpu_access': False, 'baseline_profile': baseline['profile'],
        'baseline_tree_sha256': baseline['tree_sha256'],
        'generator_sha256': sha(generator.read_bytes()),
        'modified_files': [{'path': p, 'baseline_sha256': sha(inputs[p].encode()),
            'prospective_sha256': sha(changed[p].encode())} for p in paths],
        'translation_units': records}
    (args.output / 'unwind-compile-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: two prospective adapter translation units; original profile approval remains unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('upstream', 'checked-source', 'namespace', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--cc', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--cross-probe', action='store_true')
    arguments = parser.parse_args()
    for key in ('upstream', 'checked_source', 'namespace', 'output', 'cc'):
        setattr(arguments, key, getattr(arguments, key).absolute())
    run(arguments)
