#!/usr/bin/env python3
"""Cross-compile all current project units and changed original C units only.

This Linux Mach-O control is not native compilation, a complete original build,
a link, or target execution. The independent Intel Apple job remains required.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

import compose_nvidia_first_transaction as composer
import compile_nvidia_integrated_successor as previous
import link_nvidia_first_transaction as old
import prepare_nvidia_retained_trial as retained

ROOT = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def cross_command(command):
    result, index = [command[0], '-target', 'x86_64-apple-macos15.0'], 1
    while index < len(command):
        flag = command[index]
        if flag == '-arch':
            require(command[index + 1] == 'x86_64', 'Unexpected native architecture in cross plan')
            index += 2
            continue
        if flag.startswith('-mmacosx-version-min='):
            index += 1
            continue
        result.append(flag)
        index += 1
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('canonical-parent', 'integrated-base', 'operational-base', 'base', 'composition',
                 'upstream', 'kernel-sdk', 'cc', 'cxx', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--changed-original', action='store_true')
    a = p.parse_args()
    for key, value in vars(a).items():
        if isinstance(value, Path):
            setattr(a, key, value.absolute() if key == 'output' else value.resolve(strict=True))
    verify = lambda: retained.verify_plan(a.canonical_parent, a.integrated_base,
        a.operational_base, a.base, a.composition)[1]
    value = verify()
    require(not a.output.exists(), 'Fresh cross-control output required')
    core = composer.load('s540_retained_cross_native_plan', ROOT /
        'packages/nvidia-gsp-bootstrap/prospective-native-target-preparation/compile_native.py')
    common = composer.load('s540_retained_cross_common', composer.FIRST / 'original/common.py')
    sdk = common.validate_sdk(a.kernel_sdk, None, True)
    identity = common.execution_identity(a.cc, a.cxx, True)
    include = [*composer.include_flags(a.composition), *[flag for relative in
        value['retained_trial']['include_directories'] for flag in
        ('-I', str(a.composition / 'project' / relative))]]
    a.output.mkdir(parents=True)
    (a.output / 'project-objects').mkdir()
    plans = core.project_plan(a.upstream, a.composition, a.output, a.cc, a.cxx,
                             a.kernel_sdk, value, include)
    reviewed = set(value['retained_trial']['reviewed_initializer_sources'])
    helpers = {str(Path(__file__)): composer.sha(Path(__file__)),
        str(Path(core.__file__)): composer.sha(Path(core.__file__))}
    summary = dict(format=1, status='running', host_control=True,
        native_darwin_compilation=False, full_original_compilation=False,
        composition_sha256=composer.sha(a.composition / 'composition.json'),
        sdk=sdk, compiler=identity, builder_source_sha256=helpers,
        original_entry_admission=False, hardware_admission=False,
        final_link='not_performed', kernel_execution='not_tested', **{'results': []})
    def compile_one(plan, original=False):
        command = cross_command(plan['command'])
        obj, source, cwd = plan['obj'], plan['path'], plan['cwd']
        composer.original.execute(command, cwd=cwd, timeout=300, diagnostic_log=obj.with_suffix('.log'))
        defined, imports, sections = composer.original.macho_symbols(obj,
            reviewed_project_initializers=plan['source'] in reviewed)
        if not original:
            composer.verify_fixed_project_symbols(plan['declared'], defined, imports)
        return dict(source=plan['source'], source_sha256=composer.sha(source),
            object=obj.name, object_sha256=composer.sha(obj), command=command, cwd=str(cwd),
            definitions=sorted(defined), imports=sorted(imports), sections=sections,
            dependency_sha256=core.dependencies(obj.with_suffix('.d'), source, cwd,
                a.composition, a.kernel_sdk, a.cc),
            stack_usage=composer.stack.capture_usage(source, obj, command, cwd=cwd, native_apple=False))
    report_path = a.output / 'project-compilation.json'
    try:
        for index, plan in enumerate(plans, 1):
            summary['results'].append(compile_one(plan))
            composer.write_json(report_path, summary)
            if index % 10 == 0:
                print('SDK cross project', index, '/', len(plans), flush=True)
        owners, occurrences = core.actual_owners(summary['results'], a.output / 'project-objects', reviewed)
        summary['strong_definition_owners'] = owners
        for symbol, owner in value['fixed_source_profiles']['additional_project_exports'].items():
            require(occurrences.get(symbol) == [(owner, 'strong')], 'Missing exact cross export owner: ' + symbol)
        composer.verify_compiled_rows(summary['results'], a.output / 'project-objects')
        summary['stack_usage'] = composer.stack.usage_manifest([r['stack_usage'] for r in summary['results']],
            a.output / 'project-stack-usage-manifest.json')
        if a.changed_original:
            (a.output / 'original-objects').mkdir()
            (a.output / 'original-objects/g_nvid_string.c').write_text(core.GENERATED_ORIGINAL_SOURCE)
            originals = core.original_plan(a.upstream, a.composition, a.output, a.cc, value, include)
            changed = {r['source'] for r in value['retained_trial']['changes'] if r['scope'] == 'source' and r['source'].endswith('.c')}
            chosen = [plan for plan in originals if plan['source'] in changed]
            require({r['source'] for r in chosen} == changed and changed, 'Changed original make selection differs')
            rows = [compile_one(plan, True) for plan in chosen]
            composer.verify_compiled_rows(rows, a.output / 'original-objects')
            composer.write_json(a.output / 'changed-original-compilation.json', dict(summary,
                status='compiled-retained-trial-original-delta-cross-only', results=rows,
                delta_sources=sorted(changed), original_translation_units=len(rows)))
        require(verify() == value, 'Source replay changed during cross control')
        require(common.validate_sdk(a.kernel_sdk, None, True) == sdk, 'SDK changed during cross control')
        require(all(composer.sha(Path(p)) == sha for p, sha in helpers.items()), 'Cross helper changed')
        summary.update(status='compiled-retained-trial-project-cross-only', project_translation_units=len(plans))
        print(json.dumps({'status': summary['status'], 'project_translation_units': len(plans)}), flush=True)
    except Exception as error:
        summary.update(status='failed', error=str(error))
        raise
    finally:
        composer.write_json(report_path, summary)


if __name__ == '__main__':
    main()
