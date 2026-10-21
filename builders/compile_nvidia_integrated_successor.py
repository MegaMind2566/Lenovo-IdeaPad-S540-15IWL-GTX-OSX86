#!/usr/bin/env python3
"""Cross-compile an exact integrated source successor; never link or admit it.

The frozen mapping guard is evaluated on the unchanged public-callback parent.
Only its authenticated compiler flags are relocated to the independently
replayed successor. This does not relax or replace that guard.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shlex
import struct
import sys

import compose_nvidia_first_transaction as composer
import link_nvidia_first_transaction as linker
import prepare_nvidia_integrated_successor as integrated

ROOT = Path(__file__).resolve().parents[1]
REVIEWED_INITIALIZERS = {
    'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp',
    'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp'}
CLOSED = dict(original_entry_admission=False, production_candidate_allowed=False,
              hardware_admission=False, gpu_access=False, kernel_execution='not_tested',
              final_link='not_performed', native_ci_requested=False,
              runtime_coordinator_installed=False, target_package_ready=False,
              kernel_stack_bound_proven=False, pm_30_second_shutdown_bound_proven=False,
              physical_reclamation_authorized=False)


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def ordinary(path: Path) -> Path:
    require(not any(item.is_symlink() for item in (path, *path.parents)),
            'Compilation refuses symlink paths: ' + str(path))
    return path.resolve(strict=True)


class OrderedSourceReplay:
    """Keep intermediate edit identities while checking only final file bytes."""

    def __init__(self, parent: Path, before: dict):
        self.parent = parent
        self.inventories = {'source': copy.deepcopy(before['original_files']),
                            'project': copy.deepcopy(before['project_files'])}
        self.overlays: dict[tuple[str, str], str] = {}
        self.edits = []

    def current(self, scope: str, relative: str) -> str:
        composer.checked_relative(relative)
        if (scope, relative) in self.overlays:
            return self.overlays[scope, relative]
        return (self.parent / scope / relative).read_text()

    def replace(self, scope: str, relative: str, text: str, profile: str) -> None:
        composer.checked_relative(relative)
        previous = self.inventories[scope].get(relative)
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        self.inventories[scope][relative] = {
            'sha256': digest, 'mode': previous['mode'] if previous else '100644'}
        self.overlays[scope, relative] = text
        self.edits.append(dict(scope=scope, source=relative, profile=profile,
                               input_sha256=previous['sha256'] if previous else None,
                               output_sha256=digest))

    def verify_final(self, output: Path) -> None:
        for (scope, relative), text in self.overlays.items():
            require((output / scope / relative).read_bytes() == text.encode('utf-8'),
                    'Successor differs from the final ordered transform: ' + relative)


def verify_provenance(parent: Path, output: Path) -> tuple[dict, dict]:
    """Replay exact edits in memory, including overlap order and whole manifest."""
    parent, output = ordinary(parent), ordinary(output)
    require(parent != output and not output.is_relative_to(parent) and
            not parent.is_relative_to(output), 'Parent and successor must be isolated')
    before = integrated.verify_parent(parent)
    actual = integrated.verify(output)
    require(not before.get('integrated_successor') and
            all(before['fixed_source_profiles'].get(name) is True for name in integrated.REQUIRED),
            'The unchanged eight-profile public-callback parent is required')
    modules = integrated.helpers()
    helper_hashes = integrated.helper_hashes(modules)
    expected = copy.deepcopy(before)
    replay = OrderedSourceReplay(parent, before)
    inventories, edits = replay.inventories, replay.edits
    current, replace = replay.current, replay.replace

    for name, module in modules.items():
        transforms = [('project', module.INPUTS, module.transforms)]
        if hasattr(module, 'ORIGINAL_INPUTS'):
            require(hasattr(module, 'original_transforms'), 'Original transform helper missing')
            transforms.append(('source', module.ORIGINAL_INPUTS, module.original_transforms))
        for scope, inputs, transform in transforms:
            values = {name: current(scope, name) for name in inputs}
            changed = transform(values)
            require(set(changed) == set(values), 'Transform changed its declared input set')
            for relative, text in changed.items():
                replace(scope, relative, text, name)
    lifetime = modules['session-lifetime']
    replace('project', lifetime.LOADER,
            lifetime.loader_transform(current('project', lifetime.LOADER)), 'session-lifetime-loader')
    public = integrated.GSP + 'prospective-public-callback-closure/S540NvidiaPublicCallout.hpp'
    for relative in (public, integrated.IRQ + 'S540NvidiaIrqClosure.h',
                     integrated.IRQ + 'rc/S540NvidiaIrqOriginal.h', integrated.IRQ_ORIGINAL):
        replace('project', relative, (ROOT / relative).read_text(), 'irq-companion')
    # Multiple profiles intentionally edit the same record/header. Earlier
    # bytes authenticate each history step; only the final overlay is emitted.
    replay.verify_final(output)

    expected['original_files'] = inventories['source']
    expected['original_tree_sha256'] = composer.tree_sha(inventories['source'])
    expected['project_files'] = inventories['project']
    profile = expected['fixed_source_profiles']
    for name in integrated.PROFILES:
        profile[name.replace('-', '_') + '_preparation'] = True
    profile['exact_source_replacements'].extend(edits)
    owners = profile['additional_project_exports']
    owners.update({name: integrated.RECORD for name in modules['retained-construction'].EXPORTS})
    for unit, symbols in modules['irq-callback'].EXPORTS.items():
        for symbol in symbols:
            require(symbol not in owners, 'Duplicate successor export: ' + symbol)
            owners[symbol] = unit
    owners['s540GspDiagnosticLifetimePinCount'] = lifetime.BOOT
    rows = {row['source']: row for row in expected['project_translation_units']}
    require(integrated.IRQ_ORIGINAL not in rows, 'Extra IRQ unit already exists in parent')
    rows[integrated.IRQ_ORIGINAL] = dict(source=integrated.IRQ_ORIGINAL, kind='original-c')
    for relative in (modules['irq-callback'].DEVICE, integrated.IRQ_ORIGINAL):
        definitions = dict(rows[relative].get('compile_definitions', {}))
        definitions['S540_NVIDIA_IRQ_CALLBACK_CLOSURE'] = '1'
        requirements = dict(profile['source_row_requirements'].get(relative, {}))
        requirements['compile_definitions'] = definitions
        profile['source_row_requirements'][relative] = requirements
        profile['per_source_compile_definitions'][relative] = definitions
        rows[relative].update(requirements)
    for relative, row in rows.items():
        row['sha256'] = inventories['project'][relative]['sha256']
    expected['project_translation_units'] = [rows[name] for name in sorted(rows)]
    expected['integrated_successor'] = dict(
        format=1, status='preparation-only-runtime-admission-closed',
        parent_composition_sha256=composer.sha(parent / 'composition.json'),
        helper_source_sha256=helper_hashes, ordered_profiles=list(integrated.PROFILES),
        changes=edits,
        unchanged_runtime_gates={name: before['project_files'][name]['sha256']
                                 for name in integrated.GATE_FILES},
        original_entry_admission=False, hardware_admission=False,
        kernel_stack_bound_proven=False, pm_30_second_shutdown_bound_proven=False,
        runtime_coordinator_installed=False, target_package_ready=False,
        native_ci_requested=False, physical_reclamation_authorized=False)
    expected['final_link'] = expected['original_full_compilation'] = 'not_performed'
    require(actual == expected, 'Integrated manifest differs from the complete parent-to-successor replay')
    require((output / actual['namespace']).read_bytes() == (parent / before['namespace']).read_bytes(),
            'The private namespace differs from the unchanged parent')
    require(integrated.helper_hashes(modules) == helper_hashes, 'Transform inputs changed during replay')
    return before, actual


def relocate_flags(flags: list[str], parent: Path, output: Path) -> list[str]:
    """Relocate only complete paths under the authenticated parent directory."""
    relocated = []
    for value in flags:
        path = Path(value)
        if path.is_absolute() and path.is_relative_to(parent):
            value = str(output / path.relative_to(parent))
        relocated.append(value)
    require(not any(str(parent) in value for value in relocated),
            'An unrelocated parent compiler flag remains')
    return relocated


def dependency_hashes(dep: Path, cwd: Path, upstream: Path, parent: Path, output: Path) -> dict:
    dependencies = {}
    for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
        path = Path(name)
        path = ordinary(path if path.is_absolute() else cwd / path)
        require(not any(path.is_relative_to(item) for item in (upstream, parent, ROOT / 'packages')),
                'A raw or parent dependency escaped the successor: ' + str(path))
        dependencies[str(path)] = composer.sha(path)
    require(any(Path(name).is_relative_to(output / 'project') for name in dependencies),
            'The compiler dependency list omitted its composed project source')
    return dependencies


def project_definition_strength(path: Path, source: str) -> dict[str, str]:
    """Read nlist strength with precisely the parent's two initializer reviews.

    composer.definition_strength is for original C and rejects all implicit
    initialization. Project compilation has these same two reviewed exceptions
    in the unchanged official compiler; preserve that policy before extraction.
    """
    composer.original.macho_symbols(path, reviewed_project_initializers=source in REVIEWED_INITIALIZERS)
    data = path.read_bytes()
    position, table = 32, None
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, position)
        if command == 2:
            table = struct.unpack_from('<4I', data, position + 8)
        position += size
    if table is None:
        return {}
    symbols, count, strings, string_size = table
    result = {}
    for index in range(count):
        name, kind, _, description, value = struct.unpack_from('<IBBHQ', data, symbols + index * 16)
        if kind & 0xe0 or not kind & 1 or not name or (kind & 0x0e == 0 and value == 0):
            continue
        end = data.index(b'\0', strings + name, strings + string_size)
        spelling = data[strings + name:end].decode().removeprefix('_')
        require(spelling not in result, 'Duplicate external nlist definition: ' + spelling)
        result[spelling] = 'weak' if description & 0x80 else 'strong'
    return result


def verify_new_export_owners(before: dict, value: dict, rows: list[dict], objects: Path) -> dict:
    """Prove new project export ownership from actual external nlist strength."""
    prior = before['fixed_source_profiles']['additional_project_exports']
    current = value['fixed_source_profiles']['additional_project_exports']
    required = {name: owner for name, owner in current.items() if prior.get(name) != owner}
    require(required, 'The successor must declare its new exact project exports')
    occurrences = {}
    strong = {}
    for row in rows:
        strengths = project_definition_strength(
            objects / composer.checked_relative(row['object']), row['source'])
        require(set(strengths) == set(row['definitions']),
                'Mach-O definition inventory differs from its recorded row: ' + row['source'])
        row['weak_definitions'] = sorted(name for name, strength in strengths.items() if strength == 'weak')
        for name, strength in strengths.items():
            occurrences.setdefault(name, []).append((row['source'], strength))
            if strength == 'strong':
                require(name not in strong, 'Duplicate strong project definition: ' + name)
                strong[name] = row['source']
    for name, owner in required.items():
        require(occurrences.get(name) == [(owner, 'strong')],
                'New successor export must have exactly one strong definition in its declared unit: ' + name)
    return required


def compile_project(parent: Path, output: Path, upstream: Path, sdk: Path,
                    cc: Path, cxx: Path, *, sdk_archive: Path | None = None,
                    changed_original: bool = False) -> dict:
    sys.path.insert(0, str(composer.FIRST / 'original'))
    import common
    parent, output, sdk = ordinary(parent), ordinary(output), ordinary(sdk)
    upstream = composer.original._pinned_upstream(ordinary(upstream))
    before, value = verify_provenance(parent, output)
    cc, cxx = common.compiler(str(cc)), common.compiler(str(cxx))
    identity = common.execution_identity(cc, cxx, True)
    identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
    sdk_record = common.validate_sdk(sdk, sdk_archive, True)
    require(sdk_record.get('provided') is True, 'The exact pinned kernel SDK is required')
    flags, cpp = linker.kernel_flags(sdk)
    require(flags[:3] == ['-arch', 'x86_64', '-mmacosx-version-min=15.0'],
            'The authenticated native kernel target flags changed')
    flags = ['-target', 'x86_64-apple-macos15', *flags[3:]]
    # This invokes the unchanged mapping guard on the frozen parent itself.
    bridge = relocate_flags(composer.composed_bridge_flags(upstream, parent, cc), parent, output)
    objects = output / 'project-objects'
    report_path = output / 'project-compilation.json'
    require(not objects.exists() and not report_path.exists(), 'All 61 successor objects must be fresh')
    require(len(value['project_translation_units']) == 61, 'Exactly 61 project units are required')
    if changed_original:
        require(not (output / 'changed-original-objects').exists() and
                not (output / 'changed-original-compilation.json').exists(),
                'Changed-original compilation must also be fresh')
    compiler_hashes = {str(path): composer.sha(path) for path in (cc, cxx)}
    source_hashes = {str(Path(__file__)): composer.sha(Path(__file__)),
                     **{str(ROOT / 'builders' / name): composer.sha(ROOT / 'builders' / name)
                        for name in ('compose_nvidia_first_transaction.py',
                                     'link_nvidia_first_transaction.py',
                                     'prepare_nvidia_integrated_successor.py',
                                     'compile_nvidia_global_rm.py', 'nvidia_stack_usage.py')}}
    rows = []
    report = dict(format=1, status='running', **identity, **CLOSED,
        composition_sha256=composer.sha(output / 'composition.json'),
        parent_composition_sha256=composer.sha(parent / 'composition.json'),
        integrated_provenance_verified=True, frozen_parent_mapping_guard_verified=True,
        compiler_file_sha256=compiler_hashes, builder_source_sha256=source_hashes,
        sdk=sdk_record, kernel_flags=flags, kernel_cpp_flags=cpp,
        cross_compiled_macho=True, objects_reused=False, results=rows)
    objects.mkdir()
    composer.write_json(report_path, report)
    try:
        for index, row in enumerate(value['project_translation_units']):
            source = output / 'project' / composer.checked_relative(row['source'])
            require(composer.sha(source) == row['sha256'], 'Translation unit changed before compilation')
            obj = objects / ('project-%03d-' % index + source.stem + '.o')
            if row['kind'] == 'original-c':
                compiler = cc
                selected = [*bridge, '-target', 'x86_64-apple-macos15', '-mkernel',
                            '-DKERNEL', '-D__KERNEL__', '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1']
            elif row['kind'] == 'plain-c':
                compiler, selected = cc, [*flags, '-std=c11', *composer.include_flags(output)]
            elif row['kind'] == 'cpp':
                compiler = cxx
                selected = [*flags, *composer.execution.kernel_cpp_flags(cpp),
                            *composer.include_flags(output)]
            else:
                raise ValueError('Unknown composed source kind: ' + str(row['kind']))
            if row.get('compile_definitions'):
                require(row['compile_definitions'] == value['fixed_source_profiles'][
                    'per_source_compile_definitions'].get(row['source']),
                    'Unreviewed per-source compile definitions')
                selected += ['-D' + name + '=' + definition
                             for name, definition in sorted(row['compile_definitions'].items())]
            if row.get('original_include_directories'):
                require(row['source'] == composer.CONTROL_UNIT and
                        row['original_include_directories'] == ['src/nvidia/src/libraries'],
                        'Unreviewed original include directory')
                selected += ['-I', str(output / 'source/src/nvidia/src/libraries')]
            dep = obj.with_suffix('.d')
            command = [str(compiler), *selected, '-Wframe-larger-than=4096',
                       '-Werror=frame-larger-than', '-fstack-usage', '-MD', '-MF', str(dep),
                       '-c', str(source), '-o', str(obj)]
            composer.original.execute(command, cwd=output / 'project', timeout=300,
                                      diagnostic_log=obj.with_suffix('.log'))
            allowed = row['source'] in REVIEWED_INITIALIZERS
            defined, imports, sections = composer.original.macho_symbols(
                obj, reviewed_project_initializers=allowed)
            compiler_imports = composer.verify_fixed_project_symbols(row, defined, imports)
            rows.append({**row, 'object': obj.name, 'object_sha256': composer.sha(obj),
                'definitions': sorted(defined), 'imports': sorted(imports), 'sections': sections,
                'compiler_memory_imports': sorted(compiler_imports), 'command': command,
                'cwd': str(output / 'project'),
                'dependency_sha256': dependency_hashes(dep, output / 'project', upstream, parent, output),
                'stack_usage': composer.stack.capture_usage(source, obj, command,
                    cwd=output / 'project', native_apple=False)})
            composer.write_json(report_path, report)
        require(verify_provenance(parent, output) == (before, value),
                'Source provenance changed during compilation')
        composer.verify_compiled_rows(rows, objects)
        new_owners = verify_new_export_owners(before, value, rows, objects)
        for path, digest in {**compiler_hashes, **source_hashes}.items():
            require(composer.sha(Path(path)) == digest, 'Compiler or builder changed during compilation')
        require(common.validate_sdk(sdk, sdk_archive, True) == sdk_record,
                'Pinned SDK identity changed during compilation')
        report.update(status='compiled-integrated-project-source-only', project_objects=len(rows),
            new_successor_definition_owners=new_owners, exact_new_export_owners_verified=True,
            complete_symbol_closure_proven=False,
            stack_usage=composer.stack.usage_manifest([row['stack_usage'] for row in rows],
                                                      output / 'project-stack-usage-manifest.json'))
        if changed_original:
            selected = sorted({row['source'] for row in value['integrated_successor']['changes']
                               if row['scope'] == 'source'})
            require(selected, 'No actual changed original sources were declared')
            subset = composer.compile_original_subset(upstream, output, cc, selected, host_control=True)
            report['changed_original'] = dict(status=subset['status'], sources=selected,
                report_sha256=composer.sha(output / 'changed-original-compilation.json'),
                full_profile_validated=False)
            require(verify_provenance(parent, output) == (before, value),
                    'Source provenance changed during original-subset compilation')
            composer.verify_compiled_rows(rows, objects)
            require(verify_new_export_owners(before, value, rows, objects) == new_owners,
                    'Project export ownership changed during original-subset compilation')
            for path, digest in {**compiler_hashes, **source_hashes}.items():
                require(composer.sha(Path(path)) == digest, 'Compiler or builder changed during original subset')
            require(common.validate_sdk(sdk, sdk_archive, True) == sdk_record,
                    'Pinned SDK changed during original-subset compilation')
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        composer.write_json(report_path, report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-composition', 'composition', 'upstream', 'kernel-sdk', 'cc', 'cxx'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sdk-archive', type=Path)
    parser.add_argument('--compile-changed-original', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        verify_provenance(args.parent_composition, args.composition)
        print('Exact integrated provenance verified; no compiler executed.')
    else:
        result = compile_project(args.parent_composition, args.composition, args.upstream,
            args.kernel_sdk, args.cc, args.cxx, sdk_archive=args.sdk_archive,
            changed_original=args.compile_changed_original)
        print(json.dumps({key: result[key] for key in (
            'status', 'project_objects', 'host_control', 'native_darwin_compilation')}, sort_keys=True))


if __name__ == '__main__':
    main()
