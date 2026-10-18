#!/usr/bin/env python3
"""CPU-only coordinator-root/closure regressions; fixture images are never run."""
from contextlib import ExitStack
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import nvidia_execution_closure as closure

P = closure.original.PREFIX
UPSTREAM = ROOT / 'build-src/nvidia-upstream'


def macho(path: Path, defined=(), undefined=(), kind=1, dylib=False):
    """Minimal nlist fixtures for the reader; never executable/linkable code."""
    names = [(name, 0x0f) for name in sorted(defined)] + [(name, 1) for name in sorted(undefined)]
    command_bytes = 24 + (8 if dylib else 0)
    string_offset = 32 + command_bytes + 16 * len(names)
    strings = bytearray(b'\0')
    symbols = bytearray()
    for name, symbol_kind in names:
        symbols += struct.pack('<IBBHQ', len(strings), symbol_kind,
                               1 if symbol_kind == 0x0f else 0, 0, 0)
        strings += ('_' + name).encode() + b'\0'
    header = struct.pack('<8I', 0xfeedfacf, 0x01000007, 3, kind,
                         2 if dylib else 1, command_bytes, 0, 0)
    commands = struct.pack('<6I', 2, 24, 32 + command_bytes, len(names), string_offset, len(strings))
    if dylib:
        commands += struct.pack('<II', 0xc, 8)
    path.write_bytes(header + commands + symbols + strings)


class CoordinatorClosureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.project = self.directory / 'project.o'
        self.objects = [self.directory / 'first.o', self.directory / 'second.o']
        self.root = P + 'rm_init_adapter'
        self.other = P + 'rm_execute_work_item'
        self.provided = P + 'nv_alloc_pages'
        self.crypto = P + 'libspdm_random_bytes'
        self.reviewed_missing = P + 'nv_acpi_methods_init'
        self.abi_missing = P + 'nv_dynamic_power_available'
        self.remap_missing = P + 'nv_requires_dma_remap'
        self.queue_provided = P + 'os_is_queue_flush_ongoing'
        self.imports = {self.provided, self.crypto, self.reviewed_missing,
                        self.abi_missing, self.remap_missing, self.queue_provided, 'memcpy'}
        macho(self.objects[0], {self.root}, self.imports)
        macho(self.objects[1], {self.other})
        # Project callbacks are externals of original RM, never replacements
        # for original definitions. A separate regression rejects that overlap.
        macho(self.project, {self.provided, self.crypto, self.queue_provided},
              {self.root, self.provided, 'IOFixturePlatformImport'})
        self.source_contract = self.directory / 'source-contract.json'
        self.source_contract.write_text(json.dumps({'defined_count': 2, 'namespace_sha256': 'a' * 64}))
        self.compiled = {
            'status': 'compiled', 'commit': closure.original.COMMIT,
            'source_namespace_verified': True, 'namespace_applied': True,
            'native_apple_compiler': True, 'cross_compile_probe': False,
            'source_profile': 'checked-cleanup-development',
            'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.objects},
            'namespace_contract': {'defined': sorted({self.root, self.other}),
                                   'external': sorted(self.imports), 'namespace_sha256': 'a' * 64}}
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(closure, 'EXPECTED_ORIGINAL_OBJECTS', 2))
        self.patches.enter_context(mock.patch.object(closure, 'SOURCE_CONTRACT', self.source_contract))
        self.patches.enter_context(mock.patch.object(closure.sys, 'platform', 'darwin'))
        self.patches.enter_context(mock.patch.object(closure.platform, 'machine', return_value='x86_64'))
        # Native integration validates the real pinned source. These small
        # nlist fixtures inject only the already declared supplemental ABIs;
        # independent tests below exercise their actual source verification.
        self.review_coordinator_contracts = closure.review_coordinator_contracts
        supplemental = json.loads(closure.COORDINATOR_CONTRACTS.read_text())
        self.patches.enter_context(mock.patch.object(closure, 'review_coordinator_contracts', return_value=(
            {row['namespace_symbol']: row for row in supplemental['contracts']},
            {'status': 'fixture-only; no source execution', 'manifest_sha256': 'b' * 64})))
        self.output = self.directory / 'audit'

    def analyze(self, *, extra_imports=(), kind=11, dylib=False, cross_probe=False):
        def link(*args, **kwargs):
            self.link_arguments = args
            macho(Path(args[args.index('-o') + 1]), {self.root},
                  self.imports | set(extra_imports), kind=kind, dylib=dylib)
        with mock.patch.object(closure.commands, 'run', side_effect=link) as command:
            result = closure.analyze_execution_closure(
                self.project, self.objects, self.compiled, self.output,
                linker=['fixture-ld'], cross_probe=cross_probe)
        self.assertEqual(command.call_count, 1)
        return result

    def report(self):
        return json.loads((self.output / 'execution-closure.json').read_text())

    def test_actual_project_roots_and_distinct_missing_contracts(self):
        result = self.analyze()
        self.assertEqual(result['original_roots'], [self.root])
        self.assertEqual(result['provided_project_callbacks'], sorted({self.provided, self.queue_provided}))
        self.assertEqual(result['provided_unavailable_crypto'], [self.crypto])
        self.assertEqual(result['compiler_memory_helpers'], ['memcpy'])
        self.assertEqual([row['symbol'] for row in result['unmet_reviewed_callbacks']],
                         sorted({self.reviewed_missing, self.remap_missing}))
        remap = next(row for row in result['unmet_reviewed_callbacks'] if row['symbol'] == self.remap_missing)
        self.assertEqual(remap['type'], 'NvBool (nv_state_t *)')
        self.assertEqual(remap['unavailable_policy'], 'entry-must-be-blocked-before-call')
        self.assertEqual(remap['implementation_status'], 'provided-guarded-device-remap')
        self.assertEqual([row['symbol'] for row in result['unmet_abi_review']], [self.abi_missing])
        self.assertFalse(result['unmet_abi_review'][0]['default_value_inferred'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['link_control_status'], 'passed')
        self.assertFalse(result['closure_implementation_complete'])
        for flag in ('executable', 'production_candidate_allowed', 'gpu_access', 'adapter_initialized'):
            self.assertIs(result[flag], False)
        self.assertEqual(result['source_profile'], 'checked-cleanup-development')
        self.assertEqual(result['current_kernel_global_lifecycle_gate'], 'refused-before-original-code')
        self.assertIn('-kext', self.link_arguments)
        self.assertNotIn('-bundle', self.link_arguments)
        self.assertEqual(self.link_arguments.count('-exported_symbol'), 1)
        self.assertIn('_' + self.root, self.link_arguments)
        self.assertNotIn('_' + self.other, self.link_arguments)

    def test_stale_original_object_is_rejected_before_link(self):
        self.objects[0].write_bytes(self.objects[0].read_bytes() + b'changed')
        with mock.patch.object(closure.commands, 'run') as command, \
             self.assertRaisesRegex(ValueError, 'object bytes differ'):
            closure.analyze_execution_closure(self.project, self.objects, self.compiled, self.output)
        command.assert_not_called()
        self.assertEqual(self.report()['status'], 'failed')
        self.assertEqual(self.report()['failure_phase'], 'validate-inputs')

    def test_project_must_not_replace_an_original_definition(self):
        macho(self.project, {self.other}, {self.root, self.other})
        with mock.patch.object(closure.commands, 'run') as command, \
             self.assertRaisesRegex(ValueError, 'redefine original RM definitions'):
            closure.analyze_execution_closure(self.project, self.objects, self.compiled, self.output)
        command.assert_not_called()
        self.assertEqual(self.report()['project_original_definition_overlap'], [self.other])
        self.assertEqual(self.report()['status'], 'failed')

    def test_name_only_provided_callback_still_requires_exact_abi_review(self):
        macho(self.project, {self.provided, self.crypto, self.abi_missing}, {self.root})
        result = self.analyze()
        self.assertEqual(result['unmet_abi_review'], [])
        self.assertEqual(result['provided_without_selected_abi_contract'], [self.abi_missing])
        self.assertEqual(result['abi_inventory_status'], 'blocked')
        self.assertFalse(result['closure_implementation_complete'])

    def test_supplemental_inventory_preserves_selected_244_contracts(self):
        selected = json.loads(closure.EXTERNAL_CONTRACTS.read_text())
        supplemental = json.loads(closure.COORDINATOR_CONTRACTS.read_text())
        self.assertEqual(len(selected['contracts']), 244)
        self.assertEqual({row['symbol'] for row in supplemental['contracts']},
                         {'nv_requires_dma_remap', 'os_is_queue_flush_ongoing'})
        self.assertFalse({row['symbol'] for row in selected['contracts']} &
                         {row['symbol'] for row in supplemental['contracts']})
        for reference in supplemental['reference_copies']:
            actual = hashlib.sha256((ROOT / reference['path']).read_bytes()).hexdigest()
            self.assertEqual(actual, supplemental['source_sha256'][reference['source']])

    def test_supplemental_prototypes_and_operational_implementations_match_pinned_upstream(self):
        if not UPSTREAM.exists():
            self.skipTest('Pass --upstream or provide build-src/nvidia-upstream to verify pinned source bytes.')
        rows, evidence = self.review_coordinator_contracts(UPSTREAM)
        self.assertEqual(set(rows), {self.remap_missing, self.queue_provided})
        self.assertEqual(evidence['status'], 'verified-exact-prototypes-and-source')
        self.assertEqual(evidence['contract_count'], 2)
        self.assertIn('positively attested bound-device', evidence['nv_requires_dma_remap_backend'])
        self.assertIn('before an original RM entry', evidence['nv_requires_dma_remap_admission_requirement'])
        self.assertFalse(evidence['dma_remap_runtime_admission_verified'])
        self.assertIn('must be bound', evidence['os_is_queue_flush_ongoing_admission_requirement'])
        self.assertFalse(evidence['queue_runtime_admission_verified'])

    def test_supplemental_review_refuses_absent_upstream(self):
        with self.assertRaisesRegex(ValueError, 'pinned upstream tree is required'):
            self.review_coordinator_contracts(None)

    def test_supplemental_review_rejects_changed_original_header_bytes(self):
        upstream = self.directory / 'changed-upstream'
        header = upstream / 'src/nvidia/arch/nvalloc/unix/include/nv.h'
        header.parent.mkdir(parents=True)
        header.write_text('/* Changed declaration source must fail before any policy inference. */')
        with self.assertRaisesRegex(ValueError, 'source hash changed'):
            self.review_coordinator_contracts(upstream)

    def test_stale_external_inventory_is_rejected(self):
        self.compiled['namespace_contract']['external'].remove(self.abi_missing)
        with self.assertRaisesRegex(ValueError, 'inventory is stale'):
            self.analyze()
        self.assertEqual(self.report()['status'], 'failed')

    def test_unknown_retained_import_has_structured_failure_report(self):
        unknown = P + 'invented_unreviewed_service'
        with self.assertRaisesRegex(ValueError, 'escape the verified full compilation inventory'):
            self.analyze(extra_imports={unknown})
        result = self.report()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['unreviewed_retained_imports'], [unknown])
        self.assertEqual(result['failure_phase'], 'classify-retained-imports')
        self.assertFalse(result['executable'])

    def test_wrong_link_format_is_not_a_native_fallback(self):
        with self.assertRaisesRegex(ValueError, 'not a thin x86_64'):
            self.analyze(kind=8)
        self.assertEqual(self.report()['status'], 'failed')
        self.assertEqual(self.report()['mach_o_filetype'], 11)

    def test_dylib_load_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'dynamic library'):
            self.analyze(dylib=True)
        self.assertEqual(self.report()['status'], 'failed')

    def test_linker_failure_preserves_blocked_roots_and_failure_phase(self):
        with mock.patch.object(closure.commands, 'run', side_effect=RuntimeError('actual linker stderr')), \
             self.assertRaisesRegex(RuntimeError, 'actual linker stderr'):
            closure.analyze_execution_closure(self.project, self.objects, self.compiled, self.output)
        result = self.report()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['original_roots'], [self.root])
        self.assertEqual(result['failure_phase'], 'link-original-coordinator-control')
        self.assertIn('actual linker stderr', result['failure'])

    def test_explicit_cross_profile_is_never_native_evidence(self):
        self.compiled.update(native_apple_compiler=False, cross_compile_probe=True)
        result = self.analyze(kind=8, cross_probe=True)
        self.assertIn('-bundle', self.link_arguments)
        self.assertNotIn('-kext', self.link_arguments)
        self.assertFalse(result['authoritative_darwin_link'])
        self.assertFalse(result['executable'])
        with self.assertRaisesRegex(ValueError, 'dynamic library'):
            self.analyze(kind=8, cross_probe=True, dylib=True)

    def test_changed_kernel_lifecycle_gate_requires_review(self):
        changed = self.directory / 'lifecycle.c'
        changed.write_text('/* No reviewed kernel refusal. */')
        with mock.patch.object(closure, 'LIFECYCLE_SOURCE', changed), \
             self.assertRaisesRegex(ValueError, 'lifecycle refusal needs a new source review'):
            self.analyze()
        self.assertEqual(self.report()['failure_phase'], 'validate-inputs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, default=UPSTREAM)
    arguments, remaining = parser.parse_known_args()
    UPSTREAM = arguments.upstream
    unittest.main(argv=[__file__, *remaining])
