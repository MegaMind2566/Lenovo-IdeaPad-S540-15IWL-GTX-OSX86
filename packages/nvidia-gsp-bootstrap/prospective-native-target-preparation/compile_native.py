#!/usr/bin/env python3
"""Compile one fully replayed current plan using actual Intel Apple clang.

This is a separate experimental compiler, never an override of a frozen
compiler's source-policy guard. Every object is built freshly. Complete .d,
stack captures, command, source, compiler and SDK bytes remain authenticated.
"""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
import platform
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as composer
import compile_nvidia_integrated_successor as previous
import link_nvidia_first_transaction as old
import nvidia_metaclass_initializers as metaclass

DENIED = dict(original_entry_admission=False, production_candidate_allowed=False,
              hardware_admission=False, gpu_access=False, module_loaded=False,
              kernel_execution='not_tested', physical_reclamation_authorized=False,
              aggregate_stack_proven=False, whole_dma_stop_proven=False)
OLD_KERNEL = 'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp'
POWER = 'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp'


def require(value, message):
    if not value:
        raise ValueError(message)


def checked_plan(value, callback):
    actual = callback()
    if isinstance(actual, tuple):
        actual = actual[-1]
    require(actual == value, 'Current source plan differs from its exact independent replay')


def native_environment(args):
    # Refuse before output creation or subprocesses on another host.
    require(sys.platform == 'darwin' and platform.machine() == 'x86_64',
            'Actual current native compilation/linking requires Intel macOS')
    common = composer.load('s540_current_native_common',
        composer.FIRST / 'original/common.py')
    requested = [common.compiler(str(args.cc)), common.compiler(str(args.cxx))]
    selected = []
    for request, language in zip(requested, ('clang', 'clang++')):
        actual = common.compiler(subprocess.check_output(
            ['/usr/bin/xcrun', '--find', language], text=True).strip())
        require(request == Path('/usr/bin') / language or request.resolve(strict=True) == actual.resolve(strict=True),
                'Current native compilation requires the actual xcrun-selected Apple compiler')
        selected.append(actual)
    cc, cxx = selected
    identity = common.execution_identity(cc, cxx, False)
    identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
    sdk = previous.ordinary(Path(args.kernel_sdk))
    sdk_record = common.validate_sdk(sdk, None, False)
    require(sdk_record.get('provided') is True, 'The clean pinned SDK checkout is required')
    return common, cc, cxx, sdk, sdk_record, identity


def helpers():
    paths = [Path(__file__), *[ROOT / 'builders' / name for name in (
        'compile_nvidia_global_rm.py', 'compose_nvidia_first_transaction.py',
        'compile_nvidia_integrated_successor.py', 'link_nvidia_first_transaction.py',
        'nvidia_stack_usage.py', 'nvidia_metaclass_initializers.py',
        'build_nvidia_execution.py')], composer.FIRST / 'original/common.py']
    return {str(path): composer.sha(path) for path in paths}


def dependencies(path, source, cwd, composed, sdk, compiler, *, authored_reference=False, allowed_raw_sources=()):
    require(path.is_file() and not path.is_symlink(), 'Actual compiler dependency file missing')
    result = {}
    for name in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1]):
        item = Path(name)
        item = previous.ordinary(item if item.is_absolute() else cwd / item)
        require(not item.is_relative_to(ROOT / 'packages') or
                authored_reference and item == source.resolve(strict=True) or item in allowed_raw_sources,
                'A raw project dependency escaped the composed tree: ' + str(item))
        result[str(item)] = composer.sha(item)
    require(str(source.resolve(strict=True)) in result,
            'Actual compiler dependency list omitted its claimed source')
    return result


def bridge_flags(upstream, composed, compiler, value, include):
    # Use the original make ABI directly. The caller's source replay owns the
    # current policy; do not run the old mapping guard on altered source bytes.
    first = composer.original.original_commands(upstream, composed / 'bridge-plan', compiler)[0]
    flags = first[1:first.index('-c')]
    source_root = composed / 'source/src/nvidia'
    result, index = [], 0
    while index < len(flags):
        flag = flags[index]
        result.append(flag)
        if flag in ('-I', '-include'):
            index += 1
            item = Path(flags[index])
            require(not item.is_absolute(), 'Original make ABI contains an unexpected external include')
            result.append(str((source_root / item).resolve(strict=flag == '-include')))
        index += 1
    return [*result, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
            '-DNV_VERSION_STRING="615.78.08"', '-include', str(composed / value['namespace']), *include]


def original_plan(upstream, composed, output, compiler, value, include):
    objects = output / 'original-objects'
    declared = composer.original.original_commands(upstream, objects, compiler)
    require(len(declared) == 1100, 'The pinned complete make plan must contain 1100 units')
    extra = ['-mkernel', '-DKERNEL', '-D__KERNEL__', '-arch', 'x86_64',
        '-mmacosx-version-min=15.0', '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
        '-DNV_VERSION_STRING="615.78.08"', '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1',
        '-include', str(composed / value['namespace']), *include,
        '-Wframe-larger-than=4096', '-Werror=frame-larger-than', '-fstack-usage']
    rows = []
    cwd = composed / 'source/src/nvidia'
    for index, base in enumerate(declared):
        path = Path(base[base.index('-c') + 1])
        source = path if path.is_absolute() else cwd / path
        relative = 'generated/g_nvid_string.c' if path.is_absolute() else source.resolve(strict=True).relative_to(composed / 'source').as_posix()
        require(not path.is_absolute() or path == objects / 'g_nvid_string.c',
                'The original make plan contains an unreviewed generated source')
        obj = Path(base[base.index('-o') + 1])
        require(obj.parent == objects, 'Original target escaped its exact native object directory')
        command = [*base, *extra, *composer.original_source_flags(value, relative),
                   '-MD', '-MF', str(obj.with_suffix('.d'))]
        rows.append(dict(source=relative, path=source, obj=obj, command=command,
                         cwd=cwd, label='original-%04d' % index,
                         compile_definitions=value['fixed_source_profiles'].get(
                             'per_original_source_compile_definitions', {}).get(relative, {})))
    require(len({r['source'] for r in rows}) == len({str(r['obj']) for r in rows}) == 1100,
            'The complete original make plan duplicates a source or target')
    return rows


def project_plan(upstream, composed, output, cc, cxx, sdk, value, include):
    flags, cpp = old.kernel_flags(sdk)
    bridge = bridge_flags(upstream, composed, cc, value, include)
    rows = []
    for index, declared in enumerate(value['project_translation_units']):
        source = composed / 'project' / composer.checked_relative(declared['source'])
        obj = output / 'project-objects' / ('project-%03d-' % index + source.stem + '.o')
        if declared['kind'] == 'original-c':
            compiler = cc
            selected = [*bridge, '-arch', 'x86_64', '-mmacosx-version-min=15.0',
                '-mkernel', '-DKERNEL', '-D__KERNEL__', '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1']
        elif declared['kind'] == 'plain-c':
            compiler, selected = cc, [*flags, '-std=c11', *include]
        elif declared['kind'] == 'cpp':
            compiler, selected = cxx, [*flags, *composer.execution.kernel_cpp_flags(cpp), *include]
        else:
            raise ValueError('Unknown actual project source language kind')
        macros = declared.get('compile_definitions', {})
        require(macros == value['fixed_source_profiles'].get('per_source_compile_definitions', {}).get(declared['source'], {}),
                'Project source macros differ from their exact declared profile')
        require('S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE' not in macros,
                'A global original-C ABI macro cannot be duplicated by a scoped source profile')
        selected += ['-D' + k + '=' + v for k, v in sorted(macros.items())]
        if declared.get('original_include_directories'):
            require(declared['source'] == composer.CONTROL_UNIT and
                declared['original_include_directories'] == ['src/nvidia/src/libraries'],
                'An unreviewed original include directory entered a project unit')
            selected += ['-I', str(composed / 'source/src/nvidia/src/libraries')]
        command = [str(compiler), *selected, '-Wframe-larger-than=4096',
            '-Werror=frame-larger-than', '-fstack-usage', '-MD', '-MF', str(obj.with_suffix('.d')),
            '-c', str(source), '-o', str(obj)]
        rows.append(dict(source=declared['source'], path=source, obj=obj, command=command,
                         cwd=composed / 'project', label='project-%03d' % index, declared=declared))
    require(len({r['source'] for r in rows}) == len(rows) and OLD_KERNEL not in {r['source'] for r in rows},
            'Current project matrix duplicates a unit or retains the obsolete control kernel')
    return rows


def actual_owners(rows, directory, reviewed):
    owners, occurrences = {}, {}
    for row in rows:
        obj = directory / composer.checked_relative(row['object'])
        composer.original.macho_symbols(obj, reviewed_project_initializers=row['source'] in reviewed)
        external = old.Image(obj, 1).externals()
        require(set(external['strong']) | set(external['weak']) == set(row['definitions']),
                'Actual external definition inventory differs from its compilation row')
        row['weak_definitions'] = sorted(external['weak'])
        for strength in ('strong', 'weak'):
            for symbol in external[strength]:
                occurrences.setdefault(symbol, []).append((row['source'], strength))
                if strength == 'strong':
                    require(symbol not in owners, 'Duplicate strong native definition: ' + symbol)
                    owners[symbol] = row['source']
    return owners, occurrences


def compile_verified_plan(args, value, verify_callback, *, companion_include_directories=(), reviewed_initializer_sources=()):
    common, cc, cxx, sdk, sdk_record, identity = native_environment(args)
    checked_plan(value, verify_callback)
    composed = previous.ordinary(Path(args.composition))
    upstream = composer.original._pinned_upstream(previous.ordinary(Path(args.upstream)))
    output = Path(args.native_compilation).absolute()
    require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)),
            'Every current native compilation requires a fresh ordinary output directory')
    require(not output.is_relative_to(composed) and not composed.is_relative_to(output), 'Native output overlaps composed sources')
    require(not ROOT.is_relative_to(output) and
        (not output.is_relative_to(ROOT) or output.is_relative_to(ROOT / 'build')) and
        all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in (upstream,sdk)),
        'Native output overlaps the repository or a pinned original/SDK input')
    reviewed = set(reviewed_initializer_sources)
    require(POWER in reviewed and len(reviewed) == 2 and OLD_KERNEL not in reviewed and
            reviewed <= {r['source'] for r in value['project_translation_units']},
            'Only Power plus the exact new reviewed control unit may own implicit initializers')
    include = [*composer.include_flags(composed), *[flag for name in companion_include_directories
        for flag in ('-I', str(composed / 'project' / composer.checked_relative(name)))]]
    inputs = helpers()
    compilers = {str(p): composer.sha(p) for p in (cc, cxx)}
    output.mkdir(parents=True)
    for name in ('original-objects', 'project-objects'):
        (output / name).mkdir()
    generated = output / 'original-objects/g_nvid_string.c'
    generated.write_text('const char NVRM_ID[] = "nvidia id: NVIDIA UNIX Open Kernel Module for x86_64 '
        '615.78.08 Release Build (build@ci)";\nconst char *const pNVRM_ID = NVRM_ID + 11;\n')
    original_rows = original_plan(upstream, composed, output, cc, value, include)
    project_rows = project_plan(upstream, composed, output, cc, cxx, sdk, value, include)
    reports = {}
    summary = dict(format=1, status='running', **identity, **DENIED,
        composition_directory=str(composed), composition_sha256=composer.sha(composed / 'composition.json'),
        sdk=sdk_record, compiler_file_sha256=compilers, builder_source_sha256=inputs,
        objects_reused=False, original_compilation_performed=True, project_compilation_performed=True,
        companion_include_directories=list(companion_include_directories),
        reviewed_initializer_sources=sorted(reviewed))
    composer.write_json(output / 'native-compilation.json', summary)
    def one(plan, original):
        source, obj, command, cwd = plan['path'], plan['obj'], plan['command'], plan['cwd']
        composer.original.execute(command, cwd=cwd, timeout=600, diagnostic_log=obj.with_suffix('.log'))
        defined, imported, sections = composer.original.macho_symbols(obj,
            reviewed_project_initializers=plan['source'] in reviewed)
        if original:
            allowed = composer.ORIGINAL_PROJECT_EXPORTS | set(value['fixed_source_profiles'].get('additional_private_original_exports', {}))
            require(not ({n for n in defined if not n.startswith(composer.original.PREFIX)} - allowed),
                    'An unreviewed original symbol escaped its private namespace')
            base = dict(source=plan['source'], compile_definitions=plan['compile_definitions'])
        else:
            base = dict(plan['declared'])
            composer.verify_fixed_project_symbols(base, defined, imported)
        return dict(base, source_sha256=composer.sha(source), object=obj.name,
            object_sha256=composer.sha(obj), definitions=sorted(defined), imports=sorted(imported), sections=sections,
            command=command, cwd=str(cwd), dependency_sha256=dependencies(obj.with_suffix('.d'),source,cwd,composed,sdk,cc),
            stack_usage=composer.stack.capture_usage(source, obj, command, cwd=cwd, native_apple=True))
    try:
        for label, plans in (('original', original_rows), ('project', project_rows)):
            filename = 'full-original-compilation.json' if label == 'original' else 'project-compilation.json'
            report = dict(summary, results=[], failures=[], status='running')
            reports[label] = report
            composer.write_json(output / filename, report)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(one, p, label == 'original'): p['source'] for p in plans}
                for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
                    try:
                        report['results'].append(future.result())
                    except Exception as error:
                        report['failures'].append(dict(source=futures[future], error=str(error)))
                    if index % 100 == 0:
                        composer.write_json(output / filename, report)
            require(not report['failures'] and len(report['results']) == len(plans), 'A current native compiler action failed: ' + repr(report['failures'][:4]))
            report['results'].sort(key=lambda r:r['source'])
            owners, occurrences = actual_owners(report['results'], output / (label + '-objects'), reviewed)
            report['strong_definition_owners'] = owners
            report['definition_occurrences'] = occurrences
            composer.verify_compiled_rows(report['results'], output / (label + '-objects'))
            report['stack_usage'] = composer.stack.usage_manifest([r['stack_usage'] for r in report['results']], output / (label + '-stack-usage-manifest.json'))
            report['status'] = 'compiled-current-full-original-native-source-only' if label == 'original' else 'compiled-current-project-native-source-only'
            composer.write_json(output / filename, report)
        checked_plan(value, verify_callback)
        require(common.validate_sdk(sdk,None,False) == sdk_record, 'Pinned SDK changed during current native compilation')
        require(helpers() == inputs and all(composer.sha(Path(p)) == h for p,h in compilers.items()), 'A current compiler/helper changed during compilation')
        complete = {str(output / (label + '-objects') / r['object']): old.Image(output / (label + '-objects') / r['object'],1).externals()
                    for label,report in reports.items() for r in report['results']}
        summary['input_symbol_audit'] = old.audit_symbols(complete, require_private_closure=False, require_reviewed_public=False)
        for symbol, owner in value['fixed_source_profiles'].get('additional_project_exports', {}).items():
            require(reports['project']['definition_occurrences'].get(symbol) == [(owner,'strong')], 'An exact additional project export has no sole strong native owner: ' + symbol)
        summary.update(status='compiled-current-native-source-only', original_objects=len(original_rows),
            project_objects=len(project_rows), original_report_sha256=composer.sha(output/'full-original-compilation.json'),
            project_report_sha256=composer.sha(output/'project-compilation.json'))
        return summary
    except Exception as error:
        summary.update(status='failed', error=str(error))
        raise
    finally:
        for label, report in reports.items():
            filename = 'full-original-compilation.json' if label == 'original' else 'project-compilation.json'
            composer.write_json(output / filename, report)
        composer.write_json(output / 'native-compilation.json', summary)


def verify_native_reports(args, value, verify_callback):
    common, cc, cxx, sdk, sdk_record, identity = native_environment(args)
    checked_plan(value,verify_callback)
    output = previous.ordinary(Path(args.native_compilation))
    composed = previous.ordinary(Path(args.composition))
    summary = json.loads((output/'native-compilation.json').read_text())
    require(summary.get('status') == 'compiled-current-native-source-only' and
        summary.get('composition_sha256') == composer.sha(composed/'composition.json') and
        summary.get('composition_directory') == str(composed) and summary.get('objects_reused') is False,
        'Only a complete current native source compilation can enter the linker')
    require(all(summary.get(k)==v for k,v in identity.items()) and summary.get('sdk')==sdk_record,
            'Native compiler/SDK execution identity changed')
    require(summary.get('builder_source_sha256') == helpers() and
        all(composer.sha(Path(p))==h for p,h in summary['compiler_file_sha256'].items()),
        'A native compile helper/compiler changed')
    include = [*composer.include_flags(composed), *[flag for name in summary['companion_include_directories']
        for flag in ('-I',str(composed/'project'/composer.checked_relative(name)))]]
    plans = {'original': original_plan(Path(args.upstream),composed,output,cc,value,include),
             'project': project_plan(Path(args.upstream),composed,output,cc,cxx,sdk,value,include)}
    result = {'summary':summary}
    for label in ('original','project'):
        filename='full-original-compilation.json' if label=='original' else 'project-compilation.json'
        path=output/filename
        require(composer.sha(path)==summary[label+'_report_sha256'],'Native compilation report bytes changed')
        report=json.loads(path.read_text())
        expected='compiled-current-full-original-native-source-only' if label=='original' else 'compiled-current-project-native-source-only'
        require(report.get('status')==expected and report.get('failures')==[] and
            report.get('native_darwin_compilation') is True and report.get('host_control') is False and
            report.get('composition_sha256')==summary['composition_sha256'],'Current native report identity is invalid')
        lookup={r['source']:r for r in report['results']}
        require(len(lookup)==len(report['results'])==len(plans[label]),'Native report source inventory is incomplete or duplicated')
        for plan in plans[label]:
            require(plan['source'] in lookup,'A native make/source plan row is missing')
            row=lookup[plan['source']]
            require(row['command']==plan['command'] and row['cwd']==str(plan['cwd']) and
                row['source_sha256']==composer.sha(plan['path']) and row['object']==plan['obj'].name,
                'A native command/source/target binding changed: '+plan['source'])
            require(row['dependency_sha256']==dependencies(plan['obj'].with_suffix('.d'),plan['path'],plan['cwd'],composed,sdk,cc),
                'An actual full compiler dependency inventory changed')
            capture=composer.stack.load_capture(row['stack_usage'])
            require(capture['source']==str(plan['path'].resolve(strict=True)) and
                capture['object']==str(plan['obj'].resolve(strict=True)) and
                capture['command']==plan['command'] and capture['cwd']==str(plan['cwd'].resolve(strict=True)) and
                capture['native_apple_compiler'] is True,
                'A native compiler stack capture source/object/command binding changed')
        composer.verify_compiled_rows(report['results'],output/(label+'-objects'))
        result[label]=report
    checked_plan(value,verify_callback)
    return result
