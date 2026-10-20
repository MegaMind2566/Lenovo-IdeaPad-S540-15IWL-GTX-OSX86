#!/usr/bin/env python3
"""Source, recipe and real-object controls for the isolated DSM refinement.

The fixture graphs test the transformation, not an RM stack certificate. Actual
Mach-O data probes check typed predicate extraction. Complete-TU replay remains
mandatory in the production analysis entry point.
"""
from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'builders'))
import nvidia_stack_context_refinement as context
import nvidia_stack_root_closure as closure

UPSTREAM = None


def measured_graph():
    def node(name, address, frame, target):
        return {'id': 'object:'+name, 'symbols': [name], 'external_symbols': [name],
                'non_strong_external_symbols': [], 'static_frame_bytes': frame,
                'compiler_records': [{'source_location': 'fixture.c:1:'+name}],
                'calls': [{'kind': 'call', 'address': address, 'target': {'symbol': target}}],
                'unknown_sites': []}
    return [{'object': 'fixture.o', 'object_sha256': 'object', 'source': 'fixture.c',
             'source_sha256': 'source', 'capture_sha256': 'capture',
             'nodes': [node(context.REMAP, 1377, 56, context.TEST),
                       node(context.TEST, 479, 40, context.REMAP)]}]


def refined(graphs):
    result = context._refine_verified(graphs, 'object')
    # The helper returns the fresh graph and the precise transformation record.
    return result if isinstance(result, tuple) else (result['graphs'], result['transformation'])


class TransformationControls(unittest.TestCase):
    def test_general_entries_preserved_and_only_nested_cycle_removed(self):
        original = measured_graph()
        saved = deepcopy(original)
        graphs, evidence = refined(original)
        self.assertEqual(original, saved)
        roots = {'remap': context.REMAP, 'test': context.TEST}
        before = closure.selected_roots(original, roots)
        after = closure.selected_roots(graphs, roots)
        self.assertEqual(len(graphs[0]['nodes']), 4)
        for name in roots:
            self.assertEqual(before['roots'][name]['recursive_component_count'], 1)
            self.assertEqual(after['roots'][name]['recursive_component_count'], 0)
        original_test = next(n for n in graphs[0]['nodes'] if n['id'] == 'object:'+context.TEST)
        self.assertEqual(original_test['calls'], saved[0]['nodes'][1]['calls'])
        self.assertFalse(evidence['general_entry_edge_deleted'])

    def test_actual_frames_and_unresolved_sites_survive_context_cloning(self):
        original = measured_graph()
        original[0]['nodes'][0]['unknown_sites'] = [
            {'reason': 'indirect-control-transfer', 'address': 14, 'instruction': 'callq *%rax'}]
        graphs, _ = refined(original)
        by_id = {node['id']: node for node in original[0]['nodes']}
        clones = [n for n in graphs[0]['nodes'] if 'context_origin_id' in n]
        self.assertEqual(len(clones), 2)
        for clone in clones:
            source = by_id[clone['context_origin_id']]
            self.assertEqual(clone['static_frame_bytes'], source['static_frame_bytes'])
            self.assertEqual(clone['compiler_records'], source['compiler_records'])
            self.assertEqual(clone['unknown_sites'], source['unknown_sites'])
            self.assertEqual(clone['external_symbols'], [])
        result = closure.selected_roots(graphs, {'entry': context.REMAP})['roots']['entry']
        self.assertFalse(result['compiled_subgraph_complete'])
        self.assertIsNone(result['compiled_subgraph_upper_bound_bytes'])
        self.assertGreater(result['barrier_reason_counts']['indirect-control-transfer'], 0)

    def test_missing_or_duplicate_reviewed_call_is_rejected(self):
        for count in (0, 2):
            with self.subTest(count=count):
                graphs = measured_graph()
                graphs[0]['nodes'][0]['calls'] *= count
                with self.assertRaises(ValueError):
                    refined(graphs)

    def test_nonstrong_or_duplicate_actual_definition_is_rejected(self):
        graphs = measured_graph()
        graphs[0]['nodes'][0]['non_strong_external_symbols'] = [context.REMAP]
        with self.assertRaises(ValueError):
            refined(graphs)
        graphs = measured_graph()
        duplicate = deepcopy(graphs[0]['nodes'][0])
        duplicate['id'] = 'other:'+context.REMAP
        graphs[0]['nodes'].append(duplicate)
        with self.assertRaises(ValueError):
            refined(graphs)

    def test_wrong_object_or_ambiguous_measured_object_is_rejected(self):
        with self.assertRaises(ValueError):
            context._refine_verified(measured_graph(), 'not-the-measured-object')
        with self.assertRaises(ValueError):
            context._refine_verified(measured_graph()*2, 'object')

    def test_changed_source_is_rejected_before_compiler_or_report_use(self):
        checked = {'unit': {'source_sha256': 'changed'}}
        with patch.object(subprocess, 'run', side_effect=AssertionError('compiler must not execute')):
            with self.assertRaises(ValueError):
                context._prove_acpi(checked, None, None, None,
                                    trusted_compiler=Path(sys.executable).resolve())


class RecipeControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.composition = Path(self.temporary.name).resolve()/'composed'
        self.source = self.composition/'source/src/nvidia/src/kernel/platform/acpi_common.c'
        self.obj = self.composition/'original-objects/acpi_common.o'
        for path in (self.source, self.obj):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('')
        (self.composition/'other').mkdir()
        (self.composition/'other/acpi_common.c').write_text('')

    def unit(self, compiler):
        source, obj = str(self.source), str(self.obj)
        return {'source': source, 'object': obj,
                'cwd': str(self.composition/'source/src/nvidia'),
                'command': [str(compiler), '-target', 'x86_64-macos-none', '-fPIC',
                            '-O2', '-fstack-usage', '-c', source,
                            '-o', obj]}

    def reviewed_units(self):
        audit = json.loads((ROOT/'packages/nvidia-global-rm/STACK-CONTEXT-COMPILER-RECIPES.json').read_text())
        self.assertEqual(audit['format'], 1)
        self.assertEqual(len(audit['recipes']), 2)
        compiler = Path(sys.executable).resolve()
        for row in audit['recipes']:
            unit = self.unit(compiler)
            normalized = row['normalized_command']
            self.assertEqual(hashlib.sha256(json.dumps(normalized).encode()).hexdigest(),
                             row['normalized_command_sha256'])
            self.assertEqual(normalized[0], '<TRUSTED_CLANG>')
            unit['command'] = [str(compiler), *[
                value.replace('<OBJECTS>', str(self.obj.parent)).replace('<COMPOSITION>', str(self.composition))
                for value in normalized[1:]]]
            yield row, unit, compiler

    def test_reviewed_complete_recipes_relocate_without_executing_the_compiler(self):
        for row, unit, compiler in self.reviewed_units():
            with self.subTest(profile=row['profile']), patch.object(subprocess, 'run',
                    side_effect=AssertionError('Recipe validation must not execute a compiler')):
                accepted = context._validated_command(unit, compiler)
                self.assertEqual(accepted['normalized_command_sha256'], row['normalized_command_sha256'])
                self.assertEqual(accepted['approved_recipe'], row['approval_label'])

    def test_plugin_injection_into_an_otherwise_reviewed_recipe_is_rejected(self):
        for row, unit, compiler in self.reviewed_units():
            unit['command'][1:1] = ['-Xclang', '-load', '-Xclang', '/tmp/plugin.so']
            with self.subTest(profile=row['profile']), patch.object(subprocess, 'run',
                    side_effect=AssertionError('Injected recipe must not execute')):
                with self.assertRaisesRegex(ValueError, 'Unreviewed complete'):
                    context._validated_command(unit, compiler)

    def test_json_cannot_select_executable_in_place_of_operator_trust(self):
        unit = self.unit(Path(__file__).resolve())
        with patch.object(subprocess, 'run', side_effect=AssertionError('compiler must not execute')):
            with self.assertRaises(ValueError):
                context._validated_command(unit, Path(sys.executable).resolve())

    def test_unreviewed_flags_are_refused_before_compiler_execution(self):
        compiler = Path(sys.executable).resolve()
        for flags in (['-Xclang', '-load', '-Xclang', '/tmp/plugin.so'],
                      ['-include', '/tmp/injected.h'], ['-fno-stack-usage'],
                      ['-D', 'isGenericDsmFunction(x)=0']):
            with self.subTest(flags=flags):
                unit = self.unit(compiler)
                unit['command'][1:1] = flags
                with patch.object(subprocess, 'run', side_effect=AssertionError('compiler must not execute')):
                    with self.assertRaises(ValueError):
                        context._validated_command(unit, compiler)

    def test_source_and_working_directory_cannot_be_retargeted(self):
        compiler = Path(sys.executable).resolve()
        for key, value in (('source', str(self.composition/'other/acpi_common.c')),
                           ('cwd', str(self.composition/'other'))):
            with self.subTest(key=key):
                unit = self.unit(compiler)
                unit[key] = value
                with patch.object(subprocess, 'run', side_effect=AssertionError('compiler must not execute')):
                    with self.assertRaises(ValueError):
                        context._validated_command(unit, compiler)


class ExpandedSemanticControls(unittest.TestCase):
    def test_expanded_function_scanner_preserves_literals_and_rejects_duplicates(self):
        name = context.REMAP[1:]
        definition = 'NV_STATUS '+name+'(void) { const char *s = "} {"; /* } */ return 0; }'
        self.assertEqual(context._expanded_function(definition+'\ntrailing', name), definition)
        with self.assertRaises(ValueError):
            context._expanded_function(definition+'\n'+definition, name)
        with self.assertRaises(ValueError):
            context._expanded_function('NV_STATUS '+name+'(void) {', name)

    def test_unreviewed_expanded_code_cannot_install_the_context_fact(self):
        table = 'static const ACPI_DSM_FUNCTION dsmOrderOfPrecedenceList[] = {'+','.join(
            'ACPI_DSM_FUNCTION_'+name for name in context.CONCRETE)+'};'
        definitions = '\n'.join('NV_STATUS '+name[1:]+'(void) { return 0; }'
                                for name in (context.REMAP, context.TEST))
        with self.assertRaises(ValueError):
            context._expanded_contract(definitions+'\n'+table)


class ActualPredicateObjects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = os.environ.get('S540_STACK_TEST_CLANG') or os.environ.get('CC') or \
            shutil.which('clang-18') or shutil.which('clang')
        if not cls.cc:
            raise unittest.SkipTest('Actual Clang required for typed Mach-O predicate controls.')

    def compile(self, root, text):
        source = root/'predicates.c'
        obj = root/'predicates.o'
        source.write_text(text)
        subprocess.run([self.cc, '-target', 'x86_64-apple-macos15', '-O2', '-ffreestanding',
                        '-c', str(source), '-o', str(obj)], check=True, capture_output=True)
        return obj

    def test_real_nonzero_and_wrong_size_atoms_cannot_be_proofs(self):
        for initializer, size in (('{1}', 12), ('{0}', 11), ('{0}', 13)):
            with self.subTest(initializer=initializer, size=size), tempfile.TemporaryDirectory() as directory:
                obj = self.compile(Path(directory), '__attribute__((used)) const unsigned long long '
                    f's540StackDsmPredicates[{size}] = {initializer};\n')
                with self.assertRaises(ValueError):
                    context._probe_values(obj)

    def test_real_weak_local_and_relocated_atoms_are_refused(self):
        cases = [
            '__attribute__((used,weak)) const unsigned long long s540StackDsmPredicates[12] = {0};\n',
            '__attribute__((used)) static const unsigned long long s540StackDsmPredicates[12] = {0};\n',
            'extern char external; __attribute__((used)) const unsigned long long '
            's540StackDsmPredicates[12] = {(unsigned long long)&external};\n']
        for text in cases:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                obj = self.compile(Path(directory), text)
                with self.assertRaises(ValueError):
                    context._probe_values(obj)

    def test_actual_zero_atom_is_accepted_without_decoder_or_json(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = self.compile(Path(directory), '__attribute__((used)) const unsigned long long '
                's540StackDsmPredicates[12] = {0};\n')
            proof = context._probe_values(obj)
            self.assertIsNotNone(proof)

    def test_actual_code_or_alias_cannot_pose_as_the_constant_array(self):
        cases = [
            '__attribute__((used)) const unsigned long long s540StackDsmPredicates[12] = {0};\n'
            '__asm__(".globl _predicate_alias\\n_predicate_alias = _s540StackDsmPredicates");\n',
            '__asm__(".text\\n.globl _s540StackDsmPredicates\\n.no_dead_strip _s540StackDsmPredicates'
            '\\n_s540StackDsmPredicates:\\n.zero 96");\n']
        for text in cases:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                obj = self.compile(Path(directory), text)
                with self.assertRaises(ValueError):
                    context._probe_values(obj)


class PinnedSourceControls(unittest.TestCase):
    def setUp(self):
        if UPSTREAM is None:
            self.skipTest('Pass --upstream to verify the restored pinned RM source and typed predicates.')
        self.source = UPSTREAM/'src/nvidia/src/kernel/platform/acpi_common.c'
        self.header = UPSTREAM/'src/nvidia/inc/kernel/platform/acpi_common.h'
        self.enum = UPSTREAM/'src/nvidia/interface/nvacpitypes.h'

    def check_identities(self):
        for path, expected in ((self.source, context.SOURCE_SHA),
                               (self.header, context.HEADER_SHA), (self.enum, context.ENUM_SHA)):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def compile(self, directory, text):
        ActualPredicateObjects.setUpClass()
        self.cc = ActualPredicateObjects.cc
        return ActualPredicateObjects.compile(self, directory, text)

    def test_complete_source_header_and_enum_have_reviewed_identities(self):
        self.check_identities()
        table = re.findall(r'static const ACPI_DSM_FUNCTION dsmOrderOfPrecedenceList\[\]\s*=\s*'
                           r'\{([^}]+)\};', self.source.read_text())
        self.assertEqual(len(table), 1)
        self.assertEqual(tuple(re.findall(r'ACPI_DSM_FUNCTION_([A-Z_0-9]+)', table[0])), context.CONCRETE)
        raw_table = re.findall(r'\bstatic\s+const\s+ACPI_DSM_FUNCTION\s+dsmOrderOfPrecedenceList'
                               r'\s*\[\s*\]\s*=\s*\{[^}]*\}\s*;', self.source.read_text())
        self.assertEqual(len(raw_table), 1)
        self.assertEqual(hashlib.sha256(raw_table[0].encode()).hexdigest(), context.PREPROCESSED_TABLE_SHA)

    def test_actual_enum_and_exact_header_predicate_compile_to_twelve_false_values(self):
        # This is a focused source predicate control. It does not replace replay
        # of the full measured RM TU with its complete dependency/recipe seals.
        self.check_identities()
        macro = re.findall(r'^#define isGenericDsmFunction\([^\n]+$', self.header.read_text(), re.M)
        self.assertEqual(len(macro), 1)
        values = ','.join('isGenericDsmFunction(ACPI_DSM_FUNCTION_'+name+')'
                          for name in context.CONCRETE)
        with tempfile.TemporaryDirectory() as directory:
            obj = self.compile(Path(directory), '#include "'+str(self.enum)+'"\n'+macro[0]+'\n'
                '__attribute__((used)) const unsigned long long s540StackDsmPredicates[12] = {'+values+'};\n')
            self.assertIsNotNone(context._probe_values(obj))

    def test_generic_enums_are_positive_negative_control(self):
        self.check_identities()
        macro = re.findall(r'^#define isGenericDsmFunction\([^\n]+$', self.header.read_text(), re.M)[0]
        with tempfile.TemporaryDirectory() as directory:
            obj = self.compile(Path(directory), '#include "'+str(self.enum)+'"\n'+macro+'\n'
                '__attribute__((used)) const unsigned long long s540StackDsmPredicates[12] = '
                '{isGenericDsmFunction(ACPI_DSM_FUNCTION_CURRENT)};\n')
            with self.assertRaises(ValueError):
                context._probe_values(obj)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path)
    args, rest = parser.parse_known_args()
    UPSTREAM = args.upstream.resolve(strict=True) if args.upstream else None
    unittest.main(argv=[sys.argv[0], *rest])
