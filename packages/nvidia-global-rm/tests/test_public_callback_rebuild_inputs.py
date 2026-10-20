#!/usr/bin/env python3
"""Source replay/cache-download controls without new network or compilation."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
SPEC = importlib.util.spec_from_file_location('s540_callback_inputs', ROOT / 'builders/prepare_nvidia_public_callback_rebuild.py')
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_compositions():
    names = sorted(helper.CHANGED_SOURCES) + ['packages/fixture/unit%02d.cpp' % i for i in range(58)]
    rows = [{'source': name, 'kind': 'cpp', 'sha256': '1' * 64} for name in names]
    original_files = {'src/original/%04d.c' % i: {'sha256': '0' * 64, 'mode': '100644'} for i in range(4005)}
    baseline = {'format': 1, 'status': 'materialized-source-only', 'original_file_count': 4005,
        **helper.CLOSED, 'original_files': original_files, 'original_tree_sha256': 'a' * 64,
        'namespace_sha256': 'b' * 64, 'baseline_namespace_sha256': 'c' * 64,
        'namespace': 'S540ComposedNamespace.h',
        'fixed_source_profiles': dict.fromkeys(helper.FLAGS, True),
        'project_files': {name: {'sha256': '1' * 64, 'mode': '100644'} for name in names},
        'project_translation_units': rows}
    public = deepcopy(baseline)
    public['fixed_source_profiles']['public_callback_closure'] = True
    public['project_files'][helper.NEW_HEADER] = {'sha256': '2' * 64, 'mode': '100644'}
    for name in helper.CHANGED_SOURCES:
        public['project_files'][name]['sha256'] = '3' * 64
    for row in public['project_translation_units']:
        if row['source'] in helper.CHANGED_SOURCES:
            row['sha256'] = '3' * 64
    return baseline, public


class CompositionDifferenceTests(unittest.TestCase):
    def test_exact_two_source_successor(self):
        baseline, public = source_compositions()
        result = helper.verify_composition_difference(baseline, public)
        self.assertEqual(result['original_files_unchanged'], 4005)
        self.assertEqual(result['new_translation_units'], 0)
        self.assertEqual(set(result['changed_project_sources']), helper.CHANGED_SOURCES)
        self.assertFalse(result['compilation_performed'])

    def test_unreviewed_changes_missing_profiles_or_open_gates_are_rejected(self):
        baseline, public = source_compositions()
        mutations = [
            lambda p: p['original_files']['src/original/0000.c'].__setitem__('sha256', 'f' * 64),
            lambda p: p['project_files'].__setitem__('extra.h', {'sha256': 'e' * 64}),
            lambda p: p['project_files'].pop(helper.NEW_HEADER),
            lambda p: p['project_translation_units'].append({'source': 'extra.cpp', 'kind': 'cpp', 'sha256': 'e' * 64}),
            lambda p: p['project_translation_units'][0].__setitem__('kind', 'plain-c'),
            lambda p: p['fixed_source_profiles'].__setitem__('global_epoch', False),
            lambda p: p['fixed_source_profiles'].__setitem__('public_callback_closure', False),
            lambda p: p.__setitem__('namespace_sha256', 'e' * 64),
            lambda p: p.__setitem__('hardware_admission', True),
            lambda p: p.__setitem__('original_entry_admission', True),
        ]
        for mutate in mutations:
            changed = deepcopy(public)
            mutate(changed)
            with self.assertRaises(ValueError):
                helper.verify_composition_difference(baseline, changed)


class CacheDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / 'native-cache'
        self.archive = b'synthetic pinned archive bytes; extraction is independently tested'
        self.run = {'head_sha': helper.fetch_cache.COMMIT, 'status': 'completed', 'conclusion': 'failure',
                    'path': '.github/workflows/build-nvidia-idle-image.yml'}
        self.artifact = {'name': 'NVIDIA-idle-image-native-validation',
            'workflow_run': {'id': helper.fetch_cache.RUN, 'head_sha': helper.fetch_cache.COMMIT},
            'size_in_bytes': 113859952, 'expired': False,
            'digest': 'sha256:' + digest(self.archive)}

    def patches(self, *, overlap=None, bad_bytes=False):
        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ, {'GITHUB_REPOSITORY': helper.fetch_cache.REPO}))
        stack.enter_context(patch.object(helper.fetch_cache, 'ARCHIVE_SHA', digest(self.archive)))
        self.guard = stack.enter_context(patch.object(helper.fetch_cache, 'refuse_overlap', side_effect=overlap))
        self.api = stack.enter_context(patch.object(helper.fetch_cache, 'api',
            side_effect=lambda path: self.run if path.startswith('actions/runs/') else self.artifact))
        def download(argv, *, stdout, check):
            self.assertEqual(argv[:2], ['gh', 'api'])
            self.assertTrue(argv[2].endswith('/actions/artifacts/' + str(helper.fetch_cache.ARTIFACT) + '/zip'))
            self.assertTrue(check)
            stdout.write(b'invalid bytes' if bad_bytes else self.archive)
        self.download = stack.enter_context(patch.object(helper.subprocess, 'run', side_effect=download))
        self.extract = stack.enter_context(patch.object(helper.fetch_cache, 'extract_pinned',
            side_effect=lambda archive, destination: destination.mkdir()))
        return stack

    def test_download_uses_overlap_guard_pinned_metadata_hash_and_safe_extractor(self):
        with self.patches():
            result = helper.download_cache(self.destination)
            self.guard.assert_called_once_with()
            self.assertEqual(self.api.call_count, 2)
            self.download.assert_called_once()
            self.extract.assert_called_once()
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(result['artifact_id'], helper.fetch_cache.ARTIFACT)
        self.assertEqual(result['native_jobs_started_by_helper'], 0)
        self.assertFalse(result['compilation_performed'])

    def test_native_overlap_stops_before_github_metadata_or_download(self):
        with self.patches(overlap=ValueError('another native workflow active')):
            with self.assertRaisesRegex(ValueError, 'another native workflow'):
                helper.download_cache(self.destination)
            self.api.assert_not_called()
            self.download.assert_not_called()
            self.extract.assert_not_called()

    def test_wrong_metadata_stops_before_binary_download(self):
        with self.patches():
            self.artifact['expired'] = True
            with self.assertRaisesRegex(ValueError, 'artifact provenance'):
                helper.download_cache(self.destination)
            self.download.assert_not_called()
            self.extract.assert_not_called()

    def test_changed_archive_hash_stops_before_extraction(self):
        with self.patches(bad_bytes=True):
            with self.assertRaisesRegex(ValueError, 'archive SHA256'):
                helper.download_cache(self.destination)
            self.extract.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_existing_outputs_are_not_overwritten(self):
        self.destination.mkdir()
        with self.patches():
            with self.assertRaisesRegex(ValueError, 'fresh'):
                helper.download_cache(self.destination)
            self.guard.assert_not_called()


class SourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.artifact = self.base / 'artifact'
        self.upstream = self.base / 'upstream'
        self.output = self.base / 'new-inputs'
        self.upstream.mkdir()
        baseline = self.artifact / 'inputs/baseline'
        baseline.mkdir(parents=True)
        for i in range(1100):
            (baseline / ('original-%04d.o' % i)).write_bytes(b'synthetic fixture object')
        (baseline / 'contract').mkdir()
        self.contract = {'namespace_sha256': 'fixture contract'}
        self.contract_bytes = json.dumps(self.contract, indent=2, sort_keys=True).encode() + b'\n'
        (baseline / 'contract/SOURCE-CONTRACT.json').write_bytes(self.contract_bytes)
        self.namespace_bytes = b'/* regenerated exact source-derived namespace */\n'
        self.evidence = {'report': {'status': 'failed', 'input_object_sha256': {str(i): '0' * 64 for i in range(1163)}},
                         'baseline': {'namespace_contract': self.contract}}

    def patches(self, *, bad_namespace=False, bad_cache=False):
        stack = ExitStack()
        self.upstream_check = stack.enter_context(patch.object(helper.original, '_pinned_upstream', return_value=self.upstream))
        self.cache_check = stack.enter_context(patch.object(helper.restore, 'verify_cache',
            side_effect=ValueError('corrupt pinned cache') if bad_cache else None,
            return_value=self.evidence))
        stack.enter_context(patch.object(helper.replay, 'BASELINE_SHA', digest(self.namespace_bytes)))
        stack.enter_context(patch.object(helper.restore, 'BASELINE_SHA', digest(self.namespace_bytes)))
        def namespace(objects, output):
            self.assertEqual(len(objects), 1100)
            output.mkdir(parents=True)
            (output / 'S540GlobalRmNamespace.h').write_bytes(b'wrong' if bad_namespace else self.namespace_bytes)
            (output / 'SOURCE-CONTRACT.json').write_bytes(self.contract_bytes)
        self.namespace = stack.enter_context(patch.object(helper.original, 'namespace_contract', side_effect=namespace))
        def replay(upstream, namespace, output):
            self.assertEqual(upstream, self.upstream)
            output.mkdir()
            result = {'status': 'materialized-source-only', 'source_only': True,
                'compiled': False, 'compile_report_issued': False, 'objects_reused': False,
                'original_file_count': 4005, 'hardware_admission': False,
                'original_entry_admission': False, 'production_candidate_allowed': False,
                'original_tree_sha256': 'a' * 64, 'project_tree_sha256': 'b' * 64}
            (output / 'materialized-source.json').write_text(json.dumps(result))
            return result
        self.replay = stack.enter_context(patch.object(helper.replay, 'materialize_v3', side_effect=replay))
        baseline, public = source_compositions()
        self.compose = stack.enter_context(patch.object(helper.composition, 'materialize',
            side_effect=lambda upstream, v3, namespace, output, **flags:
                public if flags.get('public_callback_closure') else baseline))
        self.verify = stack.enter_context(patch.object(helper.composition, 'verify_composition'))
        self.subprocess = stack.enter_context(patch.object(helper.subprocess, 'run'))
        self.compile = stack.enter_context(patch.object(helper.original, 'compile_original'))
        return stack

    def test_source_only_replay_never_compiles_and_checks_exact_successor(self):
        with self.patches():
            result = helper.prepare_inputs(self.artifact, self.upstream, self.output, compose_check=True)
            self.cache_check.assert_called_once_with(self.artifact, helper.fetch_cache.REPORT_SHA, allow_failed=True)
            self.namespace.assert_called_once()
            self.replay.assert_called_once()
            self.assertEqual(self.compose.call_count, 2)
            self.assertEqual(self.verify.call_count, 2)
            self.subprocess.assert_not_called()
            self.compile.assert_not_called()
        self.assertEqual(result['cached_complete_link_inputs_verified'], 1163)
        self.assertEqual(result['cached_baseline_objects_verified'], 1100)
        self.assertEqual(result['fresh_native_compilations'], 0)
        self.assertFalse(result['package_allowed'])
        receipt = json.loads((self.output / 'public-callback-rebuild-inputs.json').read_bytes())
        self.assertEqual(receipt, result)

    def test_bad_cache_is_rejected_before_source_output_creation(self):
        with self.patches(bad_cache=True):
            with self.assertRaisesRegex(ValueError, 'corrupt pinned cache'):
                helper.prepare_inputs(self.artifact, self.upstream, self.output)
            self.namespace.assert_not_called()
            self.replay.assert_not_called()
            self.compile.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_namespace_mismatch_stops_before_v3_materialization(self):
        with self.patches(bad_namespace=True):
            with self.assertRaisesRegex(ValueError, 'baseline namespace differs'):
                helper.prepare_inputs(self.artifact, self.upstream, self.output)
            self.replay.assert_not_called()
            self.compose.assert_not_called()

    def test_incomplete_baseline_matrix_is_rejected(self):
        (self.artifact / 'inputs/baseline/original-0000.o').unlink()
        with self.patches():
            with self.assertRaisesRegex(ValueError, 'complete cached raw-original'):
                helper.prepare_inputs(self.artifact, self.upstream, self.output)
            self.namespace.assert_not_called()

    def test_output_overlap_and_reuse_never_replace_inputs(self):
        with self.patches():
            for output in (self.artifact / 'overwrite', self.upstream / 'overwrite', self.base):
                with self.assertRaises(ValueError):
                    helper.prepare_inputs(self.artifact, self.upstream, output)
            self.cache_check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
