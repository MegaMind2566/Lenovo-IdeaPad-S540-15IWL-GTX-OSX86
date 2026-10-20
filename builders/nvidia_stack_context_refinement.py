#!/usr/bin/env python3
"""One source/actual-object-bound ACPI context refinement; unknown stays unknown.

There is no verified-graph JSON input. The CLI independently decodes every
measured object and replays the measured ACPI compilation with an explicitly
trusted compiler and a reviewed complete command recipe before specialization.
Acceptance-policy hashes do not constitute evidence of an earlier execution.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import nvidia_nvoc_definitions as binding
import nvidia_metaclass_initializers as macho
import nvidia_stack_root_closure as closure
import nvidia_stack_usage as stack

SOURCE_SHA = 'b382e8f0260c8d56be62b18e31d7a7f25e04e078bb29c4546c655c8f1ba1f94f'
HEADER_SHA = 'caa3efa1da4416ca0a200299be381444b4e1e2652d1324f3312cae946582f2b2'
ENUM_SHA = '05d3023c8ea7dc41326f1324491880df70802d953faca19219f181d284a5e352'
REMAP = '_s540Global_remapDsmFunctionAndSubFunction'
TEST = '_s540Global_testIfDsmSubFunctionEnabled'
CONCRETE = ('NVOP', 'NBCI', 'MXM', 'NVHG', 'NBSI', 'PCFG', 'GPS_2X', 'GPS',
            'JT', 'PEX', 'NVPCF_2X', 'NVPCF')

# These reviewed acceptance policies are never substitutes for actual replay.
# No command originating in an input manifest is executed before its complete
# recipe has passed this check against the explicitly trusted compiler.
APPROVED_RECIPES = {
    '2191aef2a0c2c5fb6ba75b0cfb5d3ce87c5272dd943babf07edeba94d13969af':
        'reviewed-composed-original-cross-profile',
    '4e5e037c1659b7bda3d50547293eb1b95712a385a1b861a96e556faacd020870':
        'same-reviewed-profile-with-native-Apple-target-flags',
    '8367155ba6767125693f96f164045372c94c041618c50684c211a354c35864fc':
        'reviewed-irq64-fatal-original-cross-profile',
    '11d72ae06bd2f8e6c97c092031b7e35d8cc630fea66ae2421f699c13d9f6c574':
        'same-reviewed-irq64-fatal-profile-with-native-Apple-target-flags',
    # Fresh reconstruction recipes were reviewed independently. They are not
    # claimed to reproduce the historical normalized command hashes above.
    '62008dc4bdf9aaed8d5b901137bc2c79c3505344e79ed6c97f38edbd120d3b58':
        'reviewed-recovery-composed-original-cross-profile',
    '42adecd15de52600cff5f86f1fc1131ff7adee2cd106fead508384e26866bdc5':
        'reviewed-recovery-composed-fatal-original-cross-profile',
}
APPROVED_PREPROCESSED_FUNCTIONS = {
    REMAP[1:]: {
        '6414c54c8b0ac079a94efdec347c1d21dfa332bb7bfe166f94eed550a901c227',
        '337db6a444c57d3f6a6e732b9ef1fe2c1b13836d18501581a690e22330ea9d14',
    },
    TEST[1:]: {
        '8d070d217c57e9004e0f94a17dc8af546d149dd98a190cf1cedaf17f40463ed7',
        '3128495428981fe488e15f1640ce89bd2945c30125926cd835aa7cf73b58c634',
    },
}
PREPROCESSED_TABLE_SHA = 'bf5b52737cbe4144700d7dc07aeed303cf23786f58c89b5589a30093d0f9514f'


def require(value, message):
    if not value:
        raise ValueError(message)


def _compile_command(unit, output, *, source=None, trusted_compiler=None):
    result, index = [], 0
    while index < len(unit['command']):
        value = unit['command'][index]
        if value in ('-o', '-MF'):
            require(index + 1 < len(unit['command']), 'Compiler output option lacks an operand')
            index += 2
            continue
        if value == '-MD':
            index += 1
            continue
        if value == '-c' and source is not None:
            require(index + 1 < len(unit['command']), 'Compiler source option lacks an operand')
            result += ['-c', str(source)]
            index += 2
            continue
        result.append(value)
        index += 1
    if trusted_compiler is not None:
        result[0] = str(Path(trusted_compiler).resolve(strict=True))
    return [*result, '-o', str(output)]


def _normalize_command(unit):
    """Retain the complete recipe; only two declared filesystem roots relocate."""
    command = unit['command']
    require(isinstance(command, list) and command and all(isinstance(v, str) for v in command),
            'Actual measured compiler command required')
    require(Path(unit['cwd']).is_absolute(), 'Actual compiler working directory must be absolute')
    cwd = Path(unit['cwd']).resolve(strict=True)
    source = Path(unit['source']).resolve(strict=True)
    obj = Path(unit['object']).resolve(strict=True)
    composition = cwd.parents[2]
    require(cwd == composition/'source/src/nvidia' and
            source == composition/'source/src/nvidia/src/kernel/platform/acpi_common.c',
            'Unexpected actual ACPI source/cwd relation')
    require(obj.is_relative_to(composition) and not obj.is_relative_to(composition/'source'),
            'Actual ACPI object must be outside its source tree in the same composition')
    require(command.count('-c') == command.count('-o') == command.count('-fstack-usage') == 1 and
            '-fno-stack-usage' not in command,
            'Expected one complete measured ACPI compile recipe')
    for flag, expected in (('-c', source), ('-o', obj)):
        index = command.index(flag)+1
        require(index < len(command), 'Actual compiler command operand missing')
        recorded = Path(command[index])
        require((cwd/recorded if not recorded.is_absolute() else recorded).resolve(strict=True) == expected,
                'Actual compiler command source/object operand differs')
    return ['<TRUSTED_CLANG>', *[
        value.replace(str(obj.parent), '<OBJECTS>').replace(str(composition), '<COMPOSITION>')
        for value in command[1:]]]


def _validated_command(unit, trusted_compiler):
    trusted = Path(trusted_compiler).resolve(strict=True)
    command = unit['command']
    require(command and Path(command[0]).is_absolute() and
            Path(command[0]).resolve(strict=True) == trusted,
            'Recorded compiler is not the explicitly trusted compiler')
    normalized = _normalize_command(unit)
    digest = hashlib.sha256(json.dumps(normalized).encode()).hexdigest()
    require(digest in APPROVED_RECIPES, 'Unreviewed complete normalized ACPI compiler recipe')
    return {'path': str(trusted), 'sha256': stack.sha(trusted),
            'normalized_command_sha256': digest, 'normalized_command': normalized,
            'approved_recipe': APPROVED_RECIPES[digest]}


_approved_recipe = _validated_command


def _probe_values(obj):
    image = macho.Object(obj)
    named = [s for s in image.symbols if s.name == '_s540StackDsmPredicates' and s.section]
    require(len(named) == 1, 'Concrete DSM proof requires one actual compiler constant array')
    symbol = named[0]
    index = next(index for index, value in enumerate(image.symbols) if value is symbol)
    # The authored probe is marked used. Clang represents that contract as
    # exactly N_NO_DEAD_STRIP, without weak/reference/other linkage attributes.
    require(symbol.kind == 15 and binding.descriptors(image)[index] == 0x20,
            'Concrete DSM predicate requires an exact strong external used data definition')
    section = image.sections[symbol.section-1]
    require(section.name != '__text' and not section.flags & 0x80000400,
            'Concrete DSM predicate must be data, not executable code')
    require([value.name for value in image._defined(symbol.section) if value.value == symbol.value] ==
            ['_s540StackDsmPredicates'], 'Concrete DSM predicate aliases require separate proof')
    offset = symbol.value-section.address
    size = 8*len(CONCRETE)
    following = [s.value-section.address for s in image._defined(symbol.section) if s.value > symbol.value]
    require(0 <= offset and offset+size <= section.size and
            min(following, default=section.size)-offset == size,
            'Concrete DSM predicate array has unexpected size')
    require(not any(r.offset < offset+size and r.offset+r.width > offset for r in image.relocations(section)),
            'Concrete DSM predicate must be an absolute compiler constant')
    raw = image.data[section.offset+offset:section.offset+offset+size]
    require(len(raw) == size and raw == bytes(size), 'A DSM precedence table entry is generic')
    return [0]*len(CONCRETE)


def _expanded_function(text, name):
    matches = list(re.finditer(r'\bNV_STATUS\s+'+re.escape(name)+r'\s*\([^;{}]*\)\s*\{', text))
    require(len(matches) == 1, 'Expanded DSM function definition is absent or ambiguous: '+name)
    start = matches[0].start()
    opening = text.index('{', matches[0].start())
    depth = 1
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for token in tokens.finditer(text, opening + 1):
        depth += (token[0] == '{') - (token[0] == '}')
        if not depth:
            return text[start:token.end()]
    raise ValueError('Unclosed expanded DSM function: '+name)


def _expanded_contract(text):
    fragments = {name: _expanded_function(text, name) for name in (REMAP[1:], TEST[1:])}
    tables = re.findall(r'\bstatic\s+const\s+ACPI_DSM_FUNCTION\s+dsmOrderOfPrecedenceList\s*\[\s*\]\s*=\s*\{[^}]*\}\s*;', text)
    require(len(tables) == 1, 'Expanded DSM precedence table changed')
    fragments['dsmOrderOfPrecedenceList'] = tables[0]
    observed = {name: hashlib.sha256(value.encode()).hexdigest()
                for name, value in fragments.items()}
    require(all(observed[name] in expected for name, expected in APPROVED_PREPROCESSED_FUNCTIONS.items()) and
            observed['dsmOrderOfPrecedenceList'] == PREPROCESSED_TABLE_SHA,
            'Reviewed expanded DSM semantics changed')
    return observed


def _prove_acpi(checked, compilation_report, paths, work, *, trusted_compiler):
    unit = checked['unit']
    require(unit['source_sha256'] == SOURCE_SHA, 'Unreviewed complete ACPI source')
    paths.checked_file(unit['source'], SOURCE_SHA)
    compiler = _validated_command(unit, trusted_compiler)
    paths.checked_file(compiler['path'], compiler['sha256'])
    report = paths.checked_file(str(compilation_report), stack.sha(compilation_report))
    data = json.loads(report.read_text())
    rows = [row for row in data['results'] if row.get('object_sha256') == unit['object_sha256'] and
            row.get('source_sha256') == SOURCE_SHA]
    require(len(rows) == 1, 'Actual ACPI compilation provenance must be unique')
    row = rows[0]
    require(row['command'] == unit['command'] and row['cwd'] == unit['cwd'] and
            row['stack_usage']['sha256'] == stack.sha(checked['capture']),
            'ACPI compilation report does not identify the exact measured command/capture')
    dependencies = row['dependency_sha256']
    require(dependencies, 'Actual ACPI compiler dependencies are required')
    for name, expected in dependencies.items():
        paths.checked_file(name, expected)
    for suffix, expected in (('/inc/kernel/platform/acpi_common.h', HEADER_SHA),
                             ('/interface/nvacpitypes.h', ENUM_SHA)):
        values = [(name, value) for name, value in dependencies.items() if name.endswith(suffix)]
        require(len(values) == 1 and values[0][1] == expected, 'Actual DSM predicate/enum source changed')
    source = paths.path(unit['source']).read_text()
    table = re.findall(r'static const ACPI_DSM_FUNCTION dsmOrderOfPrecedenceList\[\]\s*=\s*\{([^}]+)\};', source)
    require(len(table) == 1 and tuple(re.findall(r'ACPI_DSM_FUNCTION_([A-Z_0-9]+)', table[0])) == CONCRETE,
            'The exact closed DSM precedence set changed')

    def run(command, message):
        require(stack.sha(Path(compiler['path'])) == compiler['sha256'], 'Trusted compiler changed before execution')
        process = subprocess.run(command, cwd=unit['cwd'], text=True, capture_output=True, timeout=180)
        require(not process.returncode, message+': '+process.stderr[-1000:])
        require(stack.sha(Path(compiler['path'])) == compiler['sha256'], 'Trusted compiler changed during execution')
        return process

    version = run([compiler['path'], '--version'], 'Trusted Clang identity query failed').stdout
    require('clang version' in version, 'Explicitly trusted compiler is not Clang')
    compiler['version'] = version
    replay = work/'replayed-acpi.o'
    command = _compile_command(unit, replay, trusted_compiler=compiler['path'])
    run(command, 'Actual ACPI object replay failed')
    require(stack.sha(replay) == unit['object_sha256'], 'Replayed ACPI code differs from the measured original bytes')
    preprocess = []
    index = 0
    while index < len(command):
        if command[index] == '-o':
            index += 2
        elif command[index] == '-c':
            # __FILE__ is part of the reviewed expanded assertion semantics.
            # Keep the actual recorded source operand under its verified cwd;
            # changing it to an absolute spelling would change the program.
            require(index+1 < len(command), 'Recorded preprocessing source operand missing')
            preprocess += ['-E', command[index+1]]
            index += 2
        elif command[index] == '-fstack-usage':
            index += 1
        else:
            preprocess.append(command[index])
            index += 1
    process = run([*preprocess, '-P'],
                  'Actual ACPI semantic preprocessing failed')
    expanded = _expanded_contract(process.stdout)
    probe = work/'dsm_predicate_probe.c'
    probe.write_text('#include "os/os.h"\n#include "platform/acpi_common.h"\n'
        '__attribute__((used)) const unsigned long long s540StackDsmPredicates[] = {\n'+
        ',\n'.join('isGenericDsmFunction(ACPI_DSM_FUNCTION_'+name+')' for name in CONCRETE)+'\n};\n')
    obj = work/'dsm-predicate-probe.o'
    command = _compile_command(unit, obj, source=probe, trusted_compiler=compiler['path'])
    run(command, 'Actual DSM typed predicate compilation failed')
    values = _probe_values(obj)
    return {'status': 'exact-source-and-replayed-object-concrete-dsm-context',
        'object_sha256': unit['object_sha256'], 'source_sha256': SOURCE_SHA,
        'actual_dependency_count': len(dependencies), 'header_sha256': HEADER_SHA, 'enum_sha256': ENUM_SHA,
        'trusted_compiler': compiler, 'expanded_semantics_sha256': expanded,
        'precedence_enum_names': ['ACPI_DSM_FUNCTION_'+name for name in CONCRETE],
        'actual_compiler_generic_predicates': values, 'probe_object_sha256': stack.sha(obj),
        'compilation_report_sha256': stack.sha(report), 'actual_code_replay_equal': True,
        'fact': 'The only remap->test call passes one closed non-generic enum by value. '
                'That test passes the address of its unchanged scalar local to remap. '
                'This nested remap returns from its non-generic branch before its test call.',
        'source_sites': {'precedence_table': 402, 'remap_calls_test': 488,
                         'test_calls_remap': 189, 'concrete_remap_returns': 452}}


def _refine_verified(graphs, acpi_object_sha):
    """Private transformation called only after actual semantic and code replay."""
    result = deepcopy(graphs)
    matches = [g for g in result if g['object_sha256'] == acpi_object_sha]
    require(len(matches) == 1, 'One actual ACPI graph required')
    graph = matches[0]

    def unique(name):
        values = [n for g in result for n in g['nodes'] if name in n['external_symbols']]
        require(len(values) == 1 and not values[0].get('non_strong_external_symbols'),
                'DSM context requires unique strong actual function definitions')
        return values[0]

    remap, test = unique(REMAP), unique(TEST)
    require(remap in graph['nodes'] and test in graph['nodes'], 'DSM functions must belong to the replayed object')

    def site(node, name):
        values = [e for e in node['calls'] if e['target'] == {'symbol': name}]
        require(len(values) == 1 and values[0]['kind'] == 'call', 'Unique direct reviewed DSM call required')
        return values[0]

    remap_site = site(remap, TEST)
    site(test, REMAP)
    concrete_remap, concrete_test = deepcopy(remap), deepcopy(test)
    for clone in (concrete_remap, concrete_test):
        clone['context_origin_id'] = clone['id']
        clone['id'] += '#dsm-concrete'
        clone['symbols'] = [name+'[dsm-concrete]' for name in clone['symbols']]
        clone['external_symbols'] = []
        clone['non_strong_external_symbols'] = []
        clone['context_fact'] = 'acpiDsmFunction is one closed non-generic precedence enum'
    concrete_remap['calls'] = [e for e in concrete_remap['calls'] if e != remap_site]
    site(concrete_test, REMAP)['target'] = {'node': concrete_remap['id']}
    remap_site['target'] = {'node': concrete_test['id']}
    graph['nodes'] += [concrete_remap, concrete_test]
    return result, {'general_test_entry_preserved': test['id'], 'general_remap_entry_preserved': remap['id'],
        'context_copies': [concrete_test['id'], concrete_remap['id']],
        'infeasible_edge_removed_only_from': concrete_remap['id'],
        'infeasible_call_address': remap_site['address'],
        'all_unknown_sites_and_static_frames_preserved': True,
        'general_entry_edge_deleted': False, 'all_indirect_calls_remain_unknown': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rm-manifest', type=Path, required=True)
    parser.add_argument('--acpi-compilation-report', type=Path, required=True)
    parser.add_argument('--trusted-compiler', type=Path, required=True)
    parser.add_argument('--replacement-manifest', type=Path)
    parser.add_argument('--project-manifest', type=Path)
    parser.add_argument('--project-unit-count', type=int, default=60)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--llvm-objdump', type=Path)
    args = parser.parse_args()
    for name in ('rm_manifest', 'acpi_compilation_report', 'replacement_manifest', 'project_manifest', 'trusted_compiler'):
        if getattr(args, name) is not None:
            setattr(args, name, getattr(args, name).resolve(strict=True))
    args.output = args.output.resolve()
    require(not args.output.exists(), 'Fresh evidence output required')
    paths = binding.Paths([])
    units, missing = closure.project_manifest(args.rm_manifest, paths, expected_count=1100)
    require(not missing, 'Complete original measured inventory required')
    if args.replacement_manifest:
        count = json.loads(args.replacement_manifest.read_text())['unit_count']
        replacements, missing = closure.project_manifest(args.replacement_manifest, paths, expected_count=count)
        require(not missing and count > 0, 'Nonempty exact replacement inventory required')

        def key(unit):
            source = unit['unit']['source']
            if Path(source).name == 'g_nvid_string.c' and Path(source).parent.name == 'original-objects':
                return 'generated/g_nvid_string.c'
            require('/source/' in source, 'Original replacements require actual composed-source paths')
            return source.split('/source/', 1)[1]

        replacement = {key(u): u for u in replacements}
        baseline_keys = {key(u) for u in units}
        require(len(baseline_keys) == 1100 and len(replacement) == count and set(replacement) <= baseline_keys,
                'Replacement units must each replace one declared original source')
        units = [replacement.get(key(unit), unit) for unit in units]
    if args.project_manifest:
        project, missing = closure.project_manifest(args.project_manifest, paths, expected_count=args.project_unit_count)
        require(not missing, 'Complete actual project inventory required')
        units += project
    acpi = [u for u in units if u['unit']['source'].endswith('/src/kernel/platform/acpi_common.c')]
    require(len(acpi) == 1, 'Exact measured ACPI source unit required')
    tools = {Path(m.__file__): stack.sha(Path(m.__file__)) for m in (stack, closure, binding, macho)}
    tools[Path(__file__)] = stack.sha(Path(__file__))
    decoder = ([str(args.llvm_objdump), '--macho', '--disassemble', '--no-show-raw-insn', '--no-symbolic-operands']
               if args.llvm_objdump else ['/usr/bin/xcrun', 'otool', '-tv'])
    with tempfile.TemporaryDirectory(prefix='s540-stack-context-') as temporary:
        proof = _prove_acpi(acpi[0], args.acpi_compilation_report, paths, Path(temporary),
                            trusted_compiler=args.trusted_compiler)
        with ThreadPoolExecutor(max_workers=6) as pool:
            graphs = list(pool.map(lambda unit: closure.fresh_graph(unit, decoder), units))
        refined, change = _refine_verified(graphs, proof['object_sha256'])
    roots = {**closure.ROOTS, **closure.PROJECT_ROOTS,
             'hard_irq_prerequisite': '_s540Global_rm_isr', 'bottom_half_prerequisite': '_s540Global_rm_isr_bh'}
    before, after = closure.selected_roots(graphs, roots), closure.selected_roots(refined, roots)
    paths.unchanged()
    require(all(stack.sha(path) == expected for path, expected in tools.items()), 'Refinement tools changed during analysis')
    result = {'format': 1, 'status': 'selected-root-context-refinement-measured', 'proof': proof,
        'transformation': change, 'before': before, 'after': after,
        'input_source_composition_equivalence': 'not inferred; each object/capture/source verified independently',
        'source_profile_overlays': 'not assumed from a mixed object union',
        'graph_sha256': hashlib.sha256(json.dumps(graphs, sort_keys=True).encode()).hexdigest(),
        'verified_input_count': len(paths.checked), 'aggregate_stack_proven': False,
        'native_kernel_stack_size': None, 'framework_and_panic_stack_bounds': 'not_established',
        'kernel_execution': 'not_tested', 'gpu_access': False, 'production_candidate_allowed': False,
        'tool_sha256': {str(p): expected for p, expected in tools.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stack.write(args.output, result)
    print(json.dumps({'path': str(args.output), 'sha256': stack.sha(args.output),
        'root_recursive_components_before_after': {name: [before['roots'][name]['recursive_component_count'],
            after['roots'][name]['recursive_component_count']] for name in roots}, 'aggregate_stack_proven': False}))


if __name__ == '__main__':
    main()
