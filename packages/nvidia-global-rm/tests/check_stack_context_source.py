#!/usr/bin/env python3
"""Compile/replay one ACPI TU per profile; never claim a complete RM graph."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'builders'))
import compose_nvidia_first_transaction as compose
import nvidia_stack_context_refinement as context


def control(upstream, prepared, output, compiler, decoder, fatal):
    value = compose.verify_composition(prepared)
    output.mkdir(parents=True, exist_ok=False)
    for name in ('source', 'project'):
        shutil.copytree(prepared/name, output/name)
    shutil.copyfile(prepared/value['namespace'], output/value['namespace'])
    # Verify the copied bytes independently before applying the optional exact
    # diagnostic successor. No compiled object from the input is copied.
    for field, directory in (('original_files', 'source'), ('project_files', 'project')):
        context.require(compose.inventory(output/directory) == value[field], 'Copied source inventory changed')
    context.require(compose.sha(output/value['namespace']) == value['namespace_sha256'], 'Copied namespace changed')
    overlay = None
    if fatal:
        package = ROOT/'packages/nvidia-gsp-bootstrap/prospective-fatal-assert-policy'
        spec = importlib.util.spec_from_file_location('stack_control_fatal_policy', package/'prepare.py')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        originals = {name: (output/'source'/name).read_text() for name in (policy.HEADER, policy.SOURCE)}
        changed = policy.overlay(originals)
        overlay = {name: {} for name in changed}
        for name, text in changed.items():
            path = output/'source'/name
            overlay[name]['before_sha256'] = compose.sha(path)
            path.write_text(text)
            overlay[name]['after_sha256'] = compose.sha(path)
    objects = output/'original-objects'
    objects.mkdir()
    source_root = output/'source/src/nvidia'
    source = source_root/'src/kernel/platform/acpi_common.c'
    commands = compose.original.original_commands(upstream, objects, compiler)
    rows = [command for command in commands
            if command[command.index('-c')+1] == 'src/kernel/platform/acpi_common.c']
    context.require(len(rows) == 1, 'Original make profile must declare the ACPI source exactly once')
    base = rows[0]
    obj = Path(base[base.index('-o')+1])
    dep = obj.with_suffix('.d')
    command = [*base, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__', '-DNV_VERSION_STRING="615.78.08"',
        '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1', '-include', str(output/value['namespace']),
        *compose.include_flags(output), '-Wframe-larger-than=4096', '-Werror=frame-larger-than',
        '-fstack-usage', '-target', 'x86_64-macos-none', '-fPIC',
        *(['-DS540_NVIDIA_FATAL_ASSERT_POLICY=1'] if fatal else []), '-MD', '-MF', str(dep)]
    compose.original.execute(command, cwd=source_root, timeout=180, diagnostic_log=obj.with_suffix('.log'))
    dependencies = {}
    for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
        path = Path(name)
        path = (source_root/path if not path.is_absolute() else path).resolve(strict=True)
        context.require(not path.is_relative_to(upstream), 'Raw upstream header escaped the copied source')
        dependencies[str(path)] = compose.sha(path)
    reference = context.stack.capture_usage(source, obj, command, cwd=source_root)
    report = output/'acpi-compilation.json'
    context.stack.write(report, {'format': 1, 'status': 'compiled-single-acpi-source-control', 'results': [{
        'source': str(source), 'source_sha256': compose.sha(source), 'object_sha256': compose.sha(obj),
        'command': command, 'cwd': str(source_root), 'dependency_sha256': dependencies, 'stack_usage': reference}],
        'full_profile_compilation': False, 'original_translation_units_compiled': 1})
    manifest = output/'single-acpi-stack-usage-manifest.json'
    context.stack.usage_manifest([reference], manifest)
    paths = context.binding.Paths([])
    units, missing = context.closure.project_manifest(manifest, paths, expected_count=1)
    context.require(not missing and len(units) == 1, 'Actual single-TU measured inputs required')
    work = output/'proof'
    work.mkdir()
    proof = context._prove_acpi(units[0], report, paths, work, trusted_compiler=compiler)
    graph = context.closure.fresh_graph(units[0], decoder)
    graphs, change = context._refine_verified([graph], proof['object_sha256'])
    roots = {'remap': context.REMAP, 'test': context.TEST}
    before = context.closure.selected_roots([graph], roots)
    after = context.closure.selected_roots(graphs, roots)
    for name in roots:
        context.require(before['roots'][name]['recursive_component_count'] == 1 and
                        after['roots'][name]['recursive_component_count'] == 0,
                        'The actual single-TU DSM cycle was not contextually removed')
        context.require(not after['roots'][name]['compiled_subgraph_complete'] and
                        after['roots'][name]['compiled_subgraph_upper_bound_bytes'] is None,
                        'The single-TU control must preserve unresolved external stack costs')
    paths.unchanged()
    return {'profile': 'isolated-fatal-assert-control' if fatal else 'copied-source-predecessor',
        'input_composition_sha256': compose.sha(prepared/'composition.json'), 'source_overlay': overlay,
        'proof': proof, 'transformation': change, 'before': before, 'after': after,
        'actual_compiled_translation_units': 1, 'full_profile_compilation': False,
        'full_original_graph_replayed': False, 'aggregate_stack_proven': False,
        'kernel_execution': 'not_tested', 'production_candidate_allowed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--composition', type=Path, required=True)
    parser.add_argument('--trusted-compiler', type=Path, required=True)
    parser.add_argument('--llvm-objdump', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-fatal-policy', action='store_true')
    args = parser.parse_args()
    upstream = compose.original._pinned_upstream(args.upstream)
    compiler = args.trusted_compiler.resolve(strict=True)
    prepared = args.composition.resolve(strict=True)
    output = args.output.resolve()
    context.require(not output.exists(), 'Fresh source-control output required')
    output.mkdir(parents=True)
    decoder = [str(args.llvm_objdump.resolve(strict=True)), '--macho', '--disassemble',
               '--no-show-raw-insn', '--no-symbolic-operands']
    rows = [control(upstream, prepared, output/'baseline', compiler, decoder, False)]
    if args.include_fatal_policy:
        rows.append(control(upstream, prepared, output/'fatal-policy', compiler, decoder, True))
    report = output/'stack-context-source-controls.json'
    context.stack.write(report, {'format': 1, 'status': 'actual-acpi-context-source-controls-passed',
        'controls': rows, 'full_profile_replay': 'pending', 'aggregate_stack_proven': False,
        'native_apple_execution': False, 'kernel_execution': 'not_tested'})
    print(json.dumps({'path': str(report), 'sha256': compose.sha(report), 'actual_acpi_TUs': len(rows),
                      'full_profile_replay': 'pending', 'aggregate_stack_proven': False}))


if __name__ == '__main__':
    main()
