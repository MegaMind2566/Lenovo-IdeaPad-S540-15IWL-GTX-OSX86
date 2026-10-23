#!/usr/bin/env python3
"""Compile five selected complete TUs with real pinned NVIDIA/SDK headers.

This is a Linux Mach-O cross check. It neither links an image nor claims a
complete native matrix, aggregate stack bound, target execution or DMA stop.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shlex
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as composer
import compile_nvidia_integrated_successor as previous
import compile_nvidia_shutdown_successor as shutdown
import link_nvidia_first_transaction as linker


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def run(args):
    base, canonical, upstream, sdk, cc = map(previous.ordinary,
        (args.base, args.canonical_parent, args.upstream, args.kernel_sdk, args.cc))
    upstream = composer.original._pinned_upstream(upstream)
    if composer.sha(base / 'composition.json') != '72b7d5a5d93504218e8a7953d79c90c1609e4580c55922deb2ec5dab13de24d8':
        raise ValueError('Exact shutdown72b7 parent required')
    composer.verify_composition(base)
    if composer.sha(canonical / 'composition.json') != '1392052eda0733713e345e938033a06c539669d4b443ba5c3104c70ae171e298':
        raise ValueError('Exact public callback canonical parent required')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('Fresh isolated SDK controls directory required')
    sys.path.insert(0, str(composer.FIRST / 'original')); import common
    sdk_identity = common.validate_sdk(sdk, None, True)
    if not sdk_identity.get('provided'): raise ValueError('Pinned complete kernel SDK required')
    value = json.loads((base / 'composition.json').read_text())
    modules = [load('s540_sdk_' + name.replace('-', '_'), HERE.parent / name / 'prepare.py') for name in (
        'prospective-dma-stop-closure', 'prospective-first-lock-observation', 'prospective-checked-context-teardown')]
    changed = {}
    for module in modules:
        for scope, inputs, transform in [('project', module.INPUTS, module.transforms),
                ('source', module.ORIGINAL_INPUTS, getattr(module, 'original_transforms', None))]:
            if not inputs: continue
            for name, text in transform({name: (base / scope / name).read_text() for name in inputs}).items():
                changed[scope, name] = text
    bindings = {str(path): composer.sha(path) for path in (Path(__file__), cc,
        ROOT / 'builders/compose_nvidia_first_transaction.py', ROOT / 'builders/compile_nvidia_integrated_successor.py',
        ROOT / 'builders/compile_nvidia_shutdown_successor.py', ROOT / 'builders/link_nvidia_first_transaction.py',
        base / 'composition.json', canonical / 'composition.json')}
    for module in modules:
        for path in [module.HERE / 'prepare.py', *module.HERE.glob('*.inc'), *module.COMPANIONS.values()]:
            bindings[str(path)] = composer.sha(path)
    output.mkdir(parents=True)
    for scope in ('source', 'project'): shutil.copytree(base / scope, output / scope)
    shutil.copy2(base / value['namespace'], output / value['namespace'])
    for (scope, name), text in changed.items(): (output / scope / name).write_text(text)
    for module in modules:
        for name, path in module.COMPANIONS.items():
            destination = output / 'project' / name; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    objects = output / 'objects'; objects.mkdir()
    selected_includes = list(value['shutdown_successor']['include_directories'])
    for module in modules:
        for name in module.INCLUDE_DIRECTORIES:
            if name not in selected_includes: selected_includes.append(name)
    includes = [*composer.include_flags(output), *[flag for name in selected_includes
        for flag in ('-I', str(output / 'project' / name))]]
    bridge = previous.relocate_flags(composer.composed_bridge_flags(upstream, canonical, cc), canonical, output)
    bridge += includes[len(composer.include_flags(output)):]
    report = dict(format=1, status='running', base_composition_sha256=composer.sha(base / 'composition.json'),
        source_plan_scope='three exact transforms on shutdown parent; five selected complete TUs only',
        native_darwin_compilation=False, cross_compiled_macho=True, full_original_matrix=False,
        sdk=sdk_identity, source_bindings=bindings, results=[], module_loaded=False,
        original_entry_admission=False, hardware_admission=False, whole_dma_stop_proven=False,
        pm_acknowledgement_authorized=False, physical_reclamation_authorized=False)
    destination = output / 'results.json'
    def write(): composer.write_json(destination, report)
    write()
    try:
        for row in value['project_translation_units']:
            name = row['source']
            if ('project', name) not in changed: continue
            obj = objects / (Path(name).stem + '.o'); dep = obj.with_suffix('.d')
            source = output / 'project' / name
            flags = [*bridge, '-target', 'x86_64-apple-macos15', '-mkernel', '-DKERNEL', '-D__KERNEL__',
                '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1']
            flags += ['-D' + macro + '=' + definition for macro, definition in sorted(row.get('compile_definitions', {}).items())]
            command = [cc, *flags, '-Wframe-larger-than=4096', '-Werror=frame-larger-than', '-fstack-usage',
                '-MD', '-MF', dep, '-c', source, '-o', obj]
            compile_row(command, source, obj, output / 'project', report, write)
        source_root = output / 'source/src/nvidia'
        declared = composer.original.original_commands(upstream, objects, cc)
        selected = {name for scope, name in changed if scope == 'source'}
        matched = set()
        for command in declared:
            source_arg = Path(command[command.index('-c') + 1])
            if source_arg.is_absolute(): continue
            name = (source_root / source_arg).resolve(strict=True).relative_to(output / 'source').as_posix()
            if name not in selected: continue
            matched.add(name); source = output / 'source' / name
            obj = Path(command[command.index('-o') + 1]); dep = obj.with_suffix('.d')
            extra = ['-target', 'x86_64-macos-none', '-fPIC', '-mkernel', '-DKERNEL', '-D__KERNEL__',
                '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__', '-DNV_VERSION_STRING="615.78.08"',
                '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1', '-include', str(output / value['namespace']),
                *includes, *composer.original_source_flags(value, name), '-Wframe-larger-than=4096',
                '-Werror=frame-larger-than', '-fstack-usage', '-MD', '-MF', str(dep)]
            compile_row([*command, *extra], source, obj, source_root, report, write)
        if matched != selected or len(report['results']) != 5:
            raise ValueError('Selected actual make/project translation-unit inventory differs')
        context = next(row for row in report['results'] if row['source'].endswith('/S540NvidiaGspContext.c'))
        # The frozen macho_symbols API returns source spellings (one Mach-O
        # leading underscore removed), unlike raw nlist/disassembler labels.
        required = {'s540Global_s540RmDisableAdapterChecked', 's540Global_s540RmShutdownAdapterChecked'}
        forbidden = {'s540Global_rm_disable_adapter', 's540Global_rm_shutdown_adapter'}
        if not required <= set(context['imports']) or forbidden & set(context['imports']):
            raise ValueError('The actual Context Mach-O did not select only the checked private teardown imports')
        for path, expected in bindings.items():
            if composer.sha(Path(path)) != expected: raise ValueError('SDK control bound input changed')
        if common.validate_sdk(sdk, None, True) != sdk_identity: raise ValueError('Pinned SDK changed during controls')
        report.update(status='sdk-compiled-five-selected-complete-tus-cross-only',
            checked_context_private_imports=sorted(required))
        return report
    except Exception as error: report.update(status='failed', error=str(error)); raise
    finally: write()


def compile_row(command, source, obj, cwd, report, write):
    command = [str(value) for value in command]
    composer.original.execute(command, cwd=cwd, timeout=300, diagnostic_log=obj.with_suffix('.log'))
    defined, imports, sections = composer.original.macho_symbols(obj)
    report['results'].append(dict(source=str(source), source_sha256=composer.sha(source),
        object=str(obj), object_sha256=composer.sha(obj), command=command, cwd=str(cwd),
        definitions=sorted(defined), imports=sorted(imports), sections=sections,
        dependency_sha256=shutdown.dependencies(obj.with_suffix('.d'), source, cwd, ()),
        stack_usage=composer.stack.capture_usage(source, obj, command, cwd=cwd, native_apple=False)))
    write()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'canonical-parent', 'upstream', 'kernel-sdk', 'cc', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'complete_translation_units': len(result['results'])}))
