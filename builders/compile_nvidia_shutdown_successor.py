#!/usr/bin/env python3
"""Compile a verified shutdown child source plan without linking or admission.

All project units are fresh. The optional original subset contains only this
child's changed make-declared C units, not the parent's subset or a full build.
The unchanged canonical mapping guard still supplies the original bridge ABI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys

import compose_nvidia_first_transaction as composer
import compile_nvidia_integrated_successor as previous
import link_nvidia_first_transaction as linker
import prepare_nvidia_shutdown_successor as preparation

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)


def include_flags(value: dict, output: Path) -> list[str]:
    return [*composer.include_flags(output), *[flag for relative in
        value['shutdown_successor']['include_directories']
        for flag in ('-I', str(output / 'project' / composer.checked_relative(relative)))]]


def dependencies(dep: Path, source: Path, cwd: Path, excluded: tuple[Path, ...]) -> dict:
    result = {}
    for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
        path = Path(name)
        path = previous.ordinary(path if path.is_absolute() else cwd / path)
        require(not any(path.is_relative_to(root) for root in excluded),
                'A dependency escaped the verified source companion: ' + str(path))
        result[str(path)] = composer.sha(path)
    require(str(source.resolve(strict=True)) in result, 'Compiler dependencies omitted the actual source')
    return result


def export_owners(before: dict, value: dict, groups: list[tuple[str, list, Path]]) -> dict:
    prior = before['fixed_source_profiles']['additional_project_exports']
    required = {name: owner for name, owner in value['fixed_source_profiles']['additional_project_exports'].items()
                if prior.get(name) != owner}
    require(required == value['shutdown_successor']['new_project_exports'],
            'New export ownership differs from the exact source plan')
    original_required = {name: owner for name, owner in value['fixed_source_profiles'].get(
        'additional_private_original_exports', {}).items() if before['fixed_source_profiles'].get(
            'additional_private_original_exports', {}).get(name) != owner}
    require(original_required == value['shutdown_successor'].get('new_original_exports', {}),
            'New private original exports differ from the exact source plan')
    occurrences, strong = {}, {}
    for scope, rows, objects in groups:
        for row in rows:
            strengths = previous.project_definition_strength(
                objects / composer.checked_relative(row['object']), row['source'])
            require(set(strengths) == set(row['definitions']), 'Recorded definitions differ from actual Mach-O nlist')
            row['weak_definitions'] = sorted(name for name, kind in strengths.items() if kind == 'weak')
            for name, kind in strengths.items():
                occurrences.setdefault(name, []).append((scope, row['source'], kind))
                if kind == 'strong':
                    require(name not in strong, 'Duplicate strong compiled definition: ' + name)
                    strong[name] = (scope, row['source'])
    for name, owner in required.items():
        require(occurrences.get(name) == [('project', owner, 'strong')],
                'A shutdown export lacks its sole declared strong owner: ' + name)
    for name, owner in original_required.items():
        require(occurrences.get(name) == [('source', owner, 'strong')],
                'A shutdown original export lacks its sole declared strong owner: ' + name)
    return {'project': required, 'source': original_required}


def original_delta_sources(value: dict) -> tuple[set[str], list[str]]:
    """Select the child edits, never the historical operational change list."""
    source_changes = {row['source'] for row in value['shutdown_successor']['changes'] if row['scope'] == 'source'}
    selected = {name for name in source_changes if name.endswith('.c')}
    headers = sorted(source_changes - selected)
    require(selected, 'The source plan declares no changed original C translation units')
    require(all(name in value['original_files'] for name in source_changes),
            'Changed original compilation requires declared C translation units')
    return selected, headers


def compile_changed_original(upstream: Path, output: Path, compiler: Path, value: dict,
                             excluded: tuple[Path, ...]) -> dict:
    selected, headers = original_delta_sources(value)
    objects = output / 'changed-original-objects'
    destination = output / 'changed-original-compilation.json'
    require(not objects.exists() and not destination.exists(), 'Original subset output must be fresh')
    source_root = output / 'source/src/nvidia'
    declared = composer.original.original_commands(upstream, objects, compiler)
    matches = {}
    for index, command in enumerate(declared):
        name = Path(command[command.index('-c') + 1])
        if name.is_absolute():
            continue
        relative = (source_root / name).resolve(strict=True).relative_to(output / 'source').as_posix()
        if relative in selected:
            require(relative not in matches, 'A changed original source is declared twice by make')
            matches[relative] = (index, command)
    require(set(matches) == selected, 'Changed original source set differs from the pinned make plan')
    objects.mkdir()
    rows = []
    report = dict(format=1, status='running', results=rows, host_control=True, host_system='Linux',
        native_darwin_compilation=False, full_profile_validated=False,
        changed_original_headers=headers, header_dependency_closure_proven=False,
        make_declared_translation_units=1100, original_subset_scope='shutdown-child-delta-only',
        composition_sha256=composer.sha(output / 'composition.json'),
        **preparation.DENIED)
    composer.write_json(destination, report)
    try:
        extra = ['-target', 'x86_64-macos-none', '-fPIC', '-mkernel', '-DKERNEL', '-D__KERNEL__',
            '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__', '-DNV_VERSION_STRING="615.78.08"',
            '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1', '-include', str(output / value['namespace']),
            *include_flags(value, output), '-Wframe-larger-than=4096', '-Werror=frame-larger-than', '-fstack-usage']
        for relative, (index, base) in sorted(matches.items()):
            source = output / 'source' / relative
            obj = Path(base[base.index('-o') + 1])
            dep = obj.with_suffix('.d')
            command = [*base, *extra, *composer.original_source_flags(value, relative), '-MD', '-MF', str(dep)]
            composer.original.execute(command, cwd=source_root, timeout=300,
                                      diagnostic_log=objects / ('compile-%04d.log' % index))
            defined, imports, sections = composer.original.macho_symbols(obj)
            escaped = {name for name in defined if not name.startswith(composer.original.PREFIX)}
            require(not escaped - composer.ORIGINAL_PROJECT_EXPORTS, 'Changed original defines an unreviewed project export')
            for name in escaped:
                require(composer.ORIGINAL_PROJECT_OWNERS[name] == relative, 'Original project export moved units')
            rows.append(dict(source=relative, source_sha256=composer.sha(source), object=obj.name,
                object_sha256=composer.sha(obj), definitions=sorted(defined), imports=sorted(imports),
                sections=sections, command=command, cwd=str(source_root),
                dependency_sha256=dependencies(dep, source, source_root, excluded),
                stack_usage=composer.stack.capture_usage(source, obj, command, cwd=source_root, native_apple=False)))
            composer.write_json(destination, report)
        composer.verify_compiled_rows(rows, objects)
        report.update(status='compiled-shutdown-original-subset-source-only', original_translation_units=len(rows))
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        composer.write_json(destination, report)


def compile_plan(canonical_parent: Path, integrated_base: Path, base: Path, output: Path, upstream: Path, sdk: Path,
                 cc: Path, cxx: Path, *, sdk_archive: Path | None = None, changed_original=False) -> dict:
    sys.path.insert(0, str(composer.FIRST / 'original'))
    import common
    canonical_parent, integrated_base, base, output, sdk = map(previous.ordinary,
        (canonical_parent, integrated_base, base, output, sdk))
    upstream = composer.original._pinned_upstream(previous.ordinary(upstream))
    before, value = preparation.verify_plan(canonical_parent, integrated_base, base, output)
    require(changed_original or not value['shutdown_successor']['new_original_exports'],
            'New original exports require --compile-changed-original for actual owner verification')
    cc, cxx = common.compiler(str(cc)), common.compiler(str(cxx))
    identity = common.execution_identity(cc, cxx, True)
    identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
    sdk_identity = common.validate_sdk(sdk, sdk_archive, True)
    require(sdk_identity.get('provided') is True, 'The clean pinned kernel SDK is required')
    flags, cpp = linker.kernel_flags(sdk)
    require(flags[:3] == ['-arch', 'x86_64', '-mmacosx-version-min=15.0'], 'Native SDK target flags changed')
    flags = ['-target', 'x86_64-apple-macos15', *flags[3:]]
    bridge = previous.relocate_flags(
        composer.composed_bridge_flags(upstream, canonical_parent, cc), canonical_parent, output)
    # include_flags adds only selected, inventoried companion directories to the
    # authenticated original bridge profile; the old mapping guard is untouched.
    additions = include_flags(value, output)[len(composer.include_flags(output)):]
    bridge += additions
    objects = output / 'project-objects'
    destination = output / 'project-compilation.json'
    require(not objects.exists() and not destination.exists(), 'Every shutdown project object must be fresh')
    if changed_original:
        require(not (output / 'changed-original-objects').exists() and
                not (output / 'changed-original-compilation.json').exists(), 'Original subset output must be fresh')
    bindings = {str(path): composer.sha(path) for path in (cc, cxx)}
    for name in ('prepare_nvidia_shutdown_successor.py', 'compile_nvidia_shutdown_successor.py',
                 'prepare_nvidia_operational_successor.py',
                 'compile_nvidia_integrated_successor.py', 'prepare_nvidia_integrated_successor.py',
                 'compose_nvidia_first_transaction.py', 'compile_nvidia_global_rm.py',
                 'link_nvidia_first_transaction.py', 'build_nvidia_execution.py', 'nvidia_stack_usage.py'):
        bindings[str(ROOT / 'builders' / name)] = composer.sha(ROOT / 'builders' / name)
    excluded = (canonical_parent, integrated_base, base, upstream, ROOT / 'packages')
    rows = []
    report = dict(format=1, status='running', **identity, **preparation.DENIED,
        composition_sha256=composer.sha(output / 'composition.json'), base_composition_sha256=preparation.BASE_SHA256,
        canonical_parent_composition_sha256=composer.sha(canonical_parent / 'composition.json'),
        integrated_base_composition_sha256=composer.sha(integrated_base / 'composition.json'),
        inherited_operational_record_scope='historical-base-only', original_subset_scope='child-delta-only',
        source_plan_verified=True, frozen_parent_mapping_guard_verified=True,
        compiler_and_builder_file_sha256=bindings, sdk=sdk_identity,
        kernel_flags=flags, kernel_cpp_flags=cpp, cross_compiled_macho=True,
        objects_reused=False, full_original_profile_validated=False, final_link='not_performed', results=rows)
    objects.mkdir()
    composer.write_json(destination, report)
    groups = [('project', rows, objects)]
    try:
        for index, row in enumerate(value['project_translation_units']):
            source = output / 'project' / composer.checked_relative(row['source'])
            require(composer.sha(source) == row['sha256'], 'A declared project source changed')
            obj = objects / ('project-%03d-' % index + source.stem + '.o')
            if row['kind'] == 'original-c':
                compiler = cc
                selected = [*bridge, '-target', 'x86_64-apple-macos15', '-mkernel', '-DKERNEL', '-D__KERNEL__',
                            '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1']
            elif row['kind'] == 'plain-c':
                compiler, selected = cc, [*flags, '-std=c11', *include_flags(value, output)]
            elif row['kind'] == 'cpp':
                compiler, selected = cxx, [*flags, *composer.execution.kernel_cpp_flags(cpp), *include_flags(value, output)]
            else:
                raise ValueError('Unsupported shutdown project source kind')
            if row.get('compile_definitions'):
                require(row['compile_definitions'] == value['fixed_source_profiles']['per_source_compile_definitions'].get(row['source']),
                        'Unbound source compile definitions')
                selected += ['-D' + name + '=' + definition for name, definition in sorted(row['compile_definitions'].items())]
            if row.get('original_include_directories'):
                require(row['source'] == composer.CONTROL_UNIT and row['original_include_directories'] == ['src/nvidia/src/libraries'],
                        'Unreviewed original include directory')
                selected += ['-I', str(output / 'source/src/nvidia/src/libraries')]
            dep = obj.with_suffix('.d')
            command = [str(compiler), *selected, '-Wframe-larger-than=4096', '-Werror=frame-larger-than',
                       '-fstack-usage', '-MD', '-MF', str(dep), '-c', str(source), '-o', str(obj)]
            composer.original.execute(command, cwd=output / 'project', timeout=300, diagnostic_log=obj.with_suffix('.log'))
            defined, imports, sections = composer.original.macho_symbols(
                obj, reviewed_project_initializers=row['source'] in previous.REVIEWED_INITIALIZERS)
            memory = composer.verify_fixed_project_symbols(row, defined, imports)
            rows.append({**row, 'object': obj.name, 'object_sha256': composer.sha(obj),
                'definitions': sorted(defined), 'imports': sorted(imports), 'sections': sections,
                'compiler_memory_imports': sorted(memory), 'command': command, 'cwd': str(output / 'project'),
                'dependency_sha256': dependencies(dep, source, output / 'project', excluded),
                'stack_usage': composer.stack.capture_usage(source, obj, command, cwd=output / 'project', native_apple=False)})
            composer.write_json(destination, report)
        if changed_original:
            subset = compile_changed_original(upstream, output, cc, value, excluded)
            groups.append(('source', subset['results'], output / 'changed-original-objects'))
            report['changed_original'] = dict(status=subset['status'], original_translation_units=len(subset['results']),
                report_sha256=composer.sha(output / 'changed-original-compilation.json'), full_profile_validated=False,
                changed_original_headers=subset['changed_original_headers'], header_dependency_closure_proven=False)
        after_base, after = preparation.verify_plan(canonical_parent, integrated_base, base, output)
        require(after == value, 'Source plan changed during compilation')
        require(after_base == before, 'Pinned base changed during compilation')
        for _, compiled, directory in groups:
            composer.verify_compiled_rows(compiled, directory)
        owners = export_owners(before, value, groups)
        for path, digest in bindings.items():
            require(composer.sha(Path(path)) == digest, 'A compiler or builder changed during compilation')
        require(common.validate_sdk(sdk, sdk_archive, True) == sdk_identity, 'The pinned SDK changed during compilation')
        report.update(status='compiled-shutdown-project-source-only', project_objects=len(rows),
            new_project_definition_owners=owners['project'], new_original_definition_owners=owners['source'],
            declared_new_export_count=len(owners['project']) + len(owners['source']),
            complete_symbol_closure_proven=False,
            stack_usage=composer.stack.usage_manifest([row['stack_usage'] for row in rows],
                                                      output / 'project-stack-usage-manifest.json'))
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        composer.write_json(destination, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('canonical-parent', 'integrated-base', 'base', 'composition', 'upstream', 'kernel-sdk', 'cc', 'cxx'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sdk-archive', type=Path)
    parser.add_argument('--compile-changed-original', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        preparation.verify(args.canonical_parent, args.integrated_base, args.base, args.composition)
        print('Shutdown source plan verified; no compiler executed.')
    else:
        result = compile_plan(args.canonical_parent, args.integrated_base, args.base, args.composition, args.upstream,
            args.kernel_sdk, args.cc, args.cxx, sdk_archive=args.sdk_archive, changed_original=args.compile_changed_original)
        print(json.dumps({name: result[name] for name in ('status', 'project_objects', 'native_darwin_compilation')}, sort_keys=True))


if __name__ == '__main__':
    main()
