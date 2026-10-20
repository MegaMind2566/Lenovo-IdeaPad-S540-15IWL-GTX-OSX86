#!/usr/bin/env python3
"""Transport/invalidation tests, never a claim of Apple compiler execution."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('s540_selective_cache', ROOT / 'builders/nvidia_selective_native_cache.py')
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    return digest(path.read_bytes())


class Fixture:
    """A deliberately synthetic compiler matrix with production checks enabled.

    Tests replace module pins, inventory sizes and host detection through
    unittest.mock; production exposes none of these as CLI/runtime switches.
    Object parsing remains the caller's independently tested responsibility.
    """
    def __init__(self, root):
        self.root = root / 'canonical'
        self.artifact = root / 'artifact'
        self.composition = self.root / 'build/nvidia-idle-image/first-transaction-image/composition'
        self.composition.mkdir(parents=True)
        self.build = self.composition.parent.parent
        self.identity = {'host_system': 'Darwin', 'host_control': False,
            'native_darwin_compilation': True,
            'compilers': {'cc': {'path': '/usr/bin/clang', 'version': 'test Apple compiler'},
                          'cxx': {'path': '/usr/bin/clang++', 'version': 'test Apple compiler'}}}
        self.sdk = {'reference_commit': 'test pinned SDK', 'tree_sha256': 'a' * 64}
        manifest = {'format': 1, 'status': 'materialized-source-only', **cache.CLOSED}
        self.composition_hash = write_json(self.composition / 'composition.json', manifest)
        write_json(self.cached(self.composition / 'composition.json'), manifest)
        self.header = self.root / 'build-src/MacKernelSDK/Headers/public.h'
        self.header.parent.mkdir(parents=True)
        self.header.write_text('/* exact public header */\n')
        self.sources, self.rows, self.objects = {}, {}, {}
        matrices = {}
        for kind in ('original', 'project'):
            rows = []
            names = (['generated/g_nvid_string.c', 'src/nvidia/second.c'] if kind == 'original'
                     else ['packages/test/one.cpp', 'packages/test/two.cpp'])
            for index, relative in enumerate(names):
                source = (self.composition / 'original-objects/g_nvid_string.c'
                    if relative.startswith('generated/') else
                    self.composition / ('source' if kind == 'original' else 'project') / relative)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('/* real source input ' + relative + ' */\n')
                obj = self.composition / (kind + '-objects') / ('unit%d.o' % index)
                obj.parent.mkdir(parents=True, exist_ok=True)
                compiler = '/usr/bin/clang' if kind == 'original' else '/usr/bin/clang++'
                cwd = self.composition / ('source/src/nvidia' if kind == 'original' else 'project')
                cwd.mkdir(parents=True, exist_ok=True)
                command = [compiler, '-arch', 'x86_64', '-fstack-usage', '-c', str(source), '-o', str(obj),
                           '-MD', '-MF', str(obj.with_suffix('.d'))]
                data = ('synthetic transport object ' + kind + relative).encode()
                self.cached(obj).parent.mkdir(parents=True, exist_ok=True)
                self.cached(obj).write_bytes(data)
                usage = (relative + ':1:function\t8\tstatic\n').encode()
                self.cached(obj.with_suffix('.su')).write_bytes(usage)
                capture = {'format': 1, 'status': 'compiler-stack-usage-captured',
                    'native_apple_compiler': True, 'source': str(source),
                    'source_sha256': digest(source.read_bytes()), 'object': str(obj),
                    'object_sha256': digest(data), 'command': command, 'cwd': str(cwd),
                    'command_sha256': digest(json.dumps(command).encode()),
                    'usage_file': str(obj.with_suffix('.su')), 'usage_sha256': digest(usage),
                    'usage_emission': 'compiler-file',
                    'functions': [{'static_frame_known': True}],
                    'kernel_execution': 'not_tested', 'production_candidate_allowed': False}
                capture_digest = write_json(self.cached(obj.with_suffix('.stack.json')), capture)
                row = {'source': relative, 'object': obj.name, 'object_sha256': digest(data),
                    'source_sha256' if kind == 'original' else 'sha256': digest(source.read_bytes()),
                    'definitions': ['synthetic'], 'imports': [],
                    'command': command, 'cwd': str(cwd),
                    'dependency_sha256': {str(source): digest(source.read_bytes()),
                                          str(self.header): digest(self.header.read_bytes())},
                    'stack_usage': {'path': str(obj.with_suffix('.stack.json')), 'sha256': capture_digest,
                        'function_count': 1, 'dynamic_function_count': 0, 'native_apple_compiler': True}}
                rows.append(row)
                self.sources[kind, relative] = source
                self.rows[kind, relative] = row
                self.objects[str(obj)] = digest(data)
            compilers = (dict.fromkeys(('cc', 'cxx'), self.identity['compilers']['cc'])
                         if kind == 'original' else self.identity['compilers'])
            matrix = {'format': 1, 'status': 'compiled-full-original-source-only' if kind == 'original'
                else 'compiled-project-source-only', **self.identity, 'compilers': compilers,
                'composition_sha256': self.composition_hash, 'results': rows,
                'original_entry_admission': False, 'production_candidate_allowed': False,
                'gpu_access': False, 'kernel_execution': 'not_tested'}
            if kind == 'original':
                matrix.update(native_apple_compiler=True, cross_compile_probe=False, failures=[])
            filename = 'full-original-compilation.json' if kind == 'original' else 'project-compilation.json'
            matrices[kind] = write_json(self.cached(self.composition / filename), matrix)
        for name in cache.RUNTIME_OBJECTS:
            path = self.composition.parent / name
            data = ('runtime ' + name).encode()
            self.cached(path).write_bytes(data)
            self.objects[str(path)] = digest(data)
        self.report = {'format': 1, 'status': 'failed',
            'phase': 'link-same-complete-relocatable-image', 'failure_type': 'ValueError',
            'failure': 'The non-dead-stripping combined image lost or gained an external definition',
            **self.identity, 'original_compilation_performed': True,
            'project_compilation_performed': True, 'actual_link_performed': False,
            'final_link_attempted': False, 'module_loaded': False, 'installable_bundle_created': False,
            'composition_directory': str(self.composition), **cache.CLOSED,
            'composition_sha256': self.composition_hash, 'sdk': self.sdk,
            'source_plan': {'complete_original_translation_units': 2, 'canonical_project_translation_units': 2,
                'firmware_objects': 1, 'pinned_libkmod_c_wrappers': ['c_start.o', 'c_stop.o'],
                'total_expected_link_objects': 7, 'make_declared_original_source_plan_verified': True,
                'declared_original_sources': [r['source'] for (k, _), r in self.rows.items() if k == 'original'],
                'project_sources': [r['source'] for (k, _), r in self.rows.items() if k == 'project']},
            'compilation_reports': {'original_sha256': matrices['original'], 'project_sha256': matrices['project']},
            'input_object_sha256': self.objects}
        self.report_path = self.artifact / 'first-transaction-image/first-transaction-image.json'
        self.report_hash = write_json(self.report_path, self.report)

    def cached(self, path):
        return self.artifact / path.relative_to(self.build)

    def patches(self, native=True):
        stack = ExitStack()
        for key, value in [('CANONICAL_ROOT', self.root), ('REPORT_SHA256', self.report_hash),
                           ('ORIGINAL_COUNT', 2), ('PROJECT_COUNT', 2)]:
            stack.enter_context(patch.object(cache, key, value))
        stack.enter_context(patch.object(cache.platform, 'system', return_value='Darwin' if native else 'Linux'))
        stack.enter_context(patch.object(cache.platform, 'machine', return_value='x86_64'))
        return stack

    def instance(self, identity=None, sdk=None, **options):
        return cache.SelectiveNativeCache(self.artifact, composition=self.composition,
            current_identity=identity or self.identity, sdk=sdk or self.sdk, **options)

    def reuse(self, helper, key=('project', 'packages/test/one.cpp'), **overrides):
        row = self.rows[key]
        args = dict(kind=key[0], source=self.sources[key], command=row['command'],
                    cwd=Path(row['cwd']), obj=self.composition / (key[0] + '-objects') / row['object'])
        args.update(overrides)
        return helper.reuse(**args)

    def compile_synthetic_row(self, key):
        row = deepcopy(self.rows[key])
        source = self.sources[key]
        obj = self.composition / (key[0] + '-objects') / row['object']
        obj.write_bytes(b'new synthetic compiler result')
        row['object_sha256'] = digest(obj.read_bytes())
        row['source_sha256' if key[0] == 'original' else 'sha256'] = digest(source.read_bytes())
        row['dependency_sha256'][str(source)] = digest(source.read_bytes())
        capture = json.loads(self.cached(obj.with_suffix('.stack.json')).read_bytes())
        capture['object_sha256'] = row['object_sha256']
        capture['source_sha256'] = digest(source.read_bytes())
        obj.with_suffix('.su').write_bytes(self.cached(obj.with_suffix('.su')).read_bytes())
        row['stack_usage']['sha256'] = write_json(obj.with_suffix('.stack.json'), capture)
        return row

    def build_matrices(self, helper, changed=None):
        matrices = {kind: deepcopy(helper.verified['matrices'][kind]) for kind in ('original', 'project')}
        for matrix in matrices.values():
            matrix['results'] = []
            matrix['composition_sha256'] = helper.composition_sha256
        for key in self.rows:
            row = self.reuse(helper, key)
            if row is None:
                row = self.compile_synthetic_row(key)
                helper.record_compiled(kind=key[0], source=key[1])
            matrices[key[0]]['results'].append(row)
        proof = {'artifact_root': str(self.artifact), **helper.report(require_complete=True)}
        return proof, matrices['original'], matrices['project']


class NativeCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(Path(self.temp.name))

    def test_complete_cache_and_exact_transport_preserve_evidence(self):
        f = self.fixture
        before = {p.relative_to(f.artifact).as_posix(): digest(p.read_bytes())
                  for p in f.artifact.rglob('*') if p.is_file()}
        with f.patches():
            helper = f.instance()
            self.assertEqual(helper.verified['object_count'], 7)
            for key in f.rows:
                row = f.reuse(helper, key)
                self.assertTrue(row['native_cache_reuse']['all_recorded_dependencies_unchanged'])
                self.assertFalse(row['native_cache_reuse']['compiled_this_run'])
                obj = f.composition / (key[0] + '-objects') / row['object']
                for path in [obj, obj.with_suffix('.su'), obj.with_suffix('.stack.json')]:
                    self.assertEqual(path.read_bytes(), f.cached(path).read_bytes())
            result = helper.report(require_complete=True)
            self.assertEqual(result['original']['reused_objects'], 2)
            self.assertEqual(result['project']['reused_objects'], 2)
            self.assertEqual(result['original']['compiled_this_run'], 0)
            self.assertFalse(result['actual_link_performed'])
        after = {p.relative_to(f.artifact).as_posix(): digest(p.read_bytes())
                 for p in f.artifact.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_changed_source_compiles_and_records_actual_success_separately(self):
        f = self.fixture
        key = ('project', 'packages/test/one.cpp')
        with f.patches():
            helper = f.instance()
            f.sources[key].write_text('changed implementation\n')
            self.assertIsNone(f.reuse(helper, key))
            before = helper.report()['project']
            self.assertEqual((before['compile_required'], before['compiled_this_run']), (1, 0))
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                helper.report(require_complete=True)
            helper.record_compiled(kind=key[0], source=key[1])
            self.assertEqual(helper.report()['project']['compiled_this_run'], 1)
            with self.assertRaises(ValueError):
                helper.record_compiled(kind=key[0], source=key[1])

    def test_changed_and_missing_header_invalidate_unchanged_source(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            f.header.write_text('different ABI header\n')
            self.assertIsNone(f.reuse(helper))
            f.header.unlink()
            self.assertIsNone(f.reuse(helper, ('project', 'packages/test/two.cpp')))
            self.assertEqual(helper.report()['project']['compile_required'], 2)

    def test_changed_command_or_working_directory_never_rewrites_flags(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            row = f.rows['project', 'packages/test/one.cpp']
            self.assertIsNone(f.reuse(helper, command=[*row['command'], '-DCHANGED=1']))
            self.assertIsNone(f.reuse(helper, ('project', 'packages/test/two.cpp'), cwd=f.composition))
            self.assertFalse(any((f.composition / 'project-objects').glob('*.o')))

    def test_corrupt_or_missing_any_cached_object_rejects_whole_cache(self):
        f = self.fixture
        path = f.cached(Path(next(iter(f.objects))))
        with f.patches():
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Changed native cache bytes'):
                f.instance()
            path.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing regular'):
                f.instance()

    def test_corrupt_stack_capture_or_usage_rejects_whole_cache(self):
        f = self.fixture
        row = f.rows['project', 'packages/test/one.cpp']
        path = f.cached(Path(row['stack_usage']['path']))
        original = path.read_bytes()
        with f.patches():
            path.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'Changed native cache bytes'):
                f.instance()
            path.write_bytes(original)
            usage = f.cached(f.composition / 'project-objects' / row['object']).with_suffix('.su')
            usage.write_bytes(b'bad compiler stack output')
            with self.assertRaisesRegex(ValueError, 'Changed native cache bytes'):
                f.instance()

    def test_tamper_after_verification_is_detected_before_copy(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            row = f.rows['project', 'packages/test/one.cpp']
            obj = f.composition / 'project-objects' / row['object']
            f.cached(obj).write_bytes(b'changed after preflight')
            with self.assertRaisesRegex(ValueError, 'Changed native cache bytes'):
                f.reuse(helper)
            self.assertFalse(obj.exists())

    def test_host_compiler_sdk_and_canonical_paths_are_enforced(self):
        f = self.fixture
        with f.patches(native=False):
            cache.verify_cache(f.artifact)  # read-only proof is allowed on Linux
            with self.assertRaisesRegex(ValueError, 'actual Intel Darwin'):
                f.instance()
        with f.patches():
            identity = deepcopy(f.identity)
            identity['compilers']['cc']['version'] += ' changed'
            with self.assertRaisesRegex(ValueError, 'compiler identity'):
                f.instance(identity=identity)
            with self.assertRaisesRegex(ValueError, 'SDK identity'):
                f.instance(sdk={'reference_commit': 'wrong'})
            other = f.composition.parent / 'other'
            other.mkdir()
            with self.assertRaisesRegex(ValueError, 'canonical absolute'):
                cache.SelectiveNativeCache(f.artifact, composition=other,
                    current_identity=f.identity, sdk=f.sdk)

    def test_report_digest_and_symlinks_fail_closed(self):
        f = self.fixture
        with f.patches():
            f.report_path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Changed native cache bytes'):
                cache.verify_cache(f.artifact)
            write_json(f.report_path, f.report)
            row = f.rows['project', 'packages/test/one.cpp']
            obj = f.cached(f.composition / 'project-objects' / row['object'])
            target = obj.with_suffix('.other')
            obj.rename(target)
            obj.symlink_to(target.name)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                cache.verify_cache(f.artifact)

    def test_source_plan_cannot_replace_authenticated_results(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            with self.assertRaisesRegex(ValueError, 'replace authenticated'):
                f.reuse(helper, plan_row={'source': 'packages/test/one.cpp', 'imports': ['invented']})
            self.assertFalse(any((f.composition / 'project-objects').glob('*.o')))

    def test_independent_verification_accepts_exact_reuse_and_new_compile(self):
        f = self.fixture
        with f.patches():
            # Changing a source-profile manifest does not grant object reuse;
            # exact per-row commands, sources and dependencies still decide.
            manifest = json.loads((f.composition / 'composition.json').read_bytes())
            manifest['public_callback_profile'] = True
            write_json(f.composition / 'composition.json', manifest)
            helper = f.instance()
            key = ('project', 'packages/test/two.cpp')
            f.sources[key].write_text('changed public callback implementation\n')
            proof, originals, projects = f.build_matrices(helper)
            self.assertEqual(proof['original']['reused_objects'], 2)
            self.assertEqual(proof['project']['reused_objects'], 1)
            self.assertEqual(proof['project']['compiled_this_run'], 1)
            self.assertEqual(cache.verify_compilation_result(proof, f.composition, originals, projects), proof)

    def test_independent_verification_rejects_forged_or_missing_provenance(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            proof, originals, projects = f.build_matrices(helper)
            for mutate in [lambda r: r.pop('native_cache_reuse'),
                           lambda r: r['native_cache_reuse'].__setitem__('compiled_this_run', True),
                           lambda r: r['command'].append('-DFAKE=1')]:
                changed = deepcopy(projects)
                mutate(changed['results'][0])
                with self.assertRaises(ValueError):
                    cache.verify_compilation_result(proof, f.composition, originals, changed)
            changed = deepcopy(proof)
            changed['project']['reused_objects'] -= 1
            with self.assertRaisesRegex(ValueError, 'cache counts'):
                cache.verify_compilation_result(changed, f.composition, originals, projects)
            changed = deepcopy(proof)
            changed['project']['sources'].pop('packages/test/two.cpp')
            with self.assertRaisesRegex(ValueError, 'decisions differ'):
                cache.verify_compilation_result(changed, f.composition, originals, projects)

    def test_independent_verification_rehashes_current_dependencies_and_stack(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            proof, originals, projects = f.build_matrices(helper)
            header = f.header.read_bytes()
            f.header.write_text('changed after copy\n')
            with self.assertRaisesRegex(ValueError, 'input changed'):
                cache.verify_compilation_result(proof, f.composition, originals, projects)
            f.header.write_bytes(header)
            Path(projects['results'][0]['stack_usage']['path']).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Changed native cache bytes'):
                cache.verify_compilation_result(proof, f.composition, originals, projects)

    def test_independent_verification_rejects_new_compile_with_reuse_binding(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            key = ('project', 'packages/test/two.cpp')
            f.sources[key].write_text('new implementation\n')
            proof, originals, projects = f.build_matrices(helper)
            row = next(r for r in projects['results'] if r['source'] == key[1])
            row['native_cache_reuse'] = cache.reuse_provenance(helper.previous, helper.composition_sha256)
            with self.assertRaisesRegex(ValueError, 'inconsistent native cache provenance'):
                cache.verify_compilation_result(proof, f.composition, originals, projects)

    def test_controlled_scope_accepts_only_the_two_expected_source_changes(self):
        f = self.fixture
        scope = {key for key in f.rows if key[0] == 'project'}
        with f.patches(), patch.object(cache, 'PUBLIC_CALLBACK_REBUILDS', scope):
            helper = f.instance(allowed_rebuilds=scope)
            for key in scope:
                f.sources[key].write_text('reviewed callback successor ' + key[1])
            proof, originals, projects = f.build_matrices(helper)
            self.assertEqual(proof['allowed_rebuilds'], cache.rebuild_scope_rows(scope))
            self.assertEqual(proof['original']['compiled_this_run'], 0)
            self.assertEqual(proof['project']['compiled_this_run'], 2)
            self.assertEqual(cache.verify_compilation_result(proof, f.composition, originals, projects), proof)

    def test_controlled_scope_refuses_original_or_other_source_before_copy_or_record(self):
        f = self.fixture
        # The second controlled source is absent from the synthetic two-project
        # matrix; its first project row stands for an unchanged third-party row.
        approved = {('project', 'packages/test/two.cpp'), ('project', 'packages/test/reviewed.cpp')}
        with f.patches(), patch.object(cache, 'PUBLIC_CALLBACK_REBUILDS', approved):
            helper = f.instance(allowed_rebuilds=approved)
            for key in [('original', 'src/nvidia/second.c'), ('project', 'packages/test/one.cpp')]:
                f.sources[key].write_text('unexpected source edit')
                with self.assertRaisesRegex(ValueError, 'unexpected compiler cache miss'):
                    f.reuse(helper, key)
                self.assertEqual(helper.report()[key[0]]['planned_sources'], 0)
                self.assertFalse((f.composition / (key[0] + '-objects') / f.rows[key]['object']).exists())

    def test_controlled_scope_refuses_command_drift_even_for_approved_sources(self):
        f = self.fixture
        scope = {key for key in f.rows if key[0] == 'project'}
        with f.patches(), patch.object(cache, 'PUBLIC_CALLBACK_REBUILDS', scope):
            helper = f.instance(allowed_rebuilds=scope)
            key = ('project', 'packages/test/one.cpp')
            f.sources[key].write_text('reviewed successor')
            with self.assertRaisesRegex(ValueError, 'compile-command-or-cwd-changed'):
                f.reuse(helper, key, command=[*f.rows[key]['command'], '-Iunexpected'])
            self.assertEqual(helper.report()['project']['planned_sources'], 0)
            self.assertFalse(any((f.composition / 'project-objects').glob('*.o')))

    def test_controlled_scope_refuses_widened_policy_and_forged_postbuild_policy(self):
        f = self.fixture
        scope = {key for key in f.rows if key[0] == 'project'}
        with f.patches(), patch.object(cache, 'PUBLIC_CALLBACK_REBUILDS', scope):
            with self.assertRaisesRegex(ValueError, 'exactly the two'):
                f.instance(allowed_rebuilds=scope | {('original', 'src/nvidia/second.c')})
            helper = f.instance(allowed_rebuilds=scope)
            proof, originals, projects = f.build_matrices(helper)
            proof['allowed_rebuilds'].append({'kind': 'original', 'source': 'src/nvidia/second.c'})
            with self.assertRaisesRegex(ValueError, 'scope changed'):
                cache.verify_compilation_result(proof, f.composition, originals, projects)

    def test_public_callback_profile_cannot_disable_its_precompile_cost_guard(self):
        f = self.fixture
        manifest = json.loads((f.composition / 'composition.json').read_bytes())
        manifest['fixed_source_profiles'] = {'public_callback_closure': True}
        write_json(f.composition / 'composition.json', manifest)
        scope = {key for key in f.rows if key[0] == 'project'}
        with f.patches(), patch.object(cache, 'PUBLIC_CALLBACK_REBUILDS', scope):
            with self.assertRaisesRegex(ValueError, 'explicit two-source rebuild cost guard'):
                f.instance()
            helper = f.instance(allowed_rebuilds=scope)
            proof, originals, projects = f.build_matrices(helper)
            proof['allowed_rebuilds'] = None
            with self.assertRaisesRegex(ValueError, 'mandatory two-source rebuild cost guard'):
                cache.verify_compilation_result(proof, f.composition, originals, projects)

    def test_postbuild_verification_detects_header_tamper_after_deduplicated_hit(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            proof, originals, projects = f.build_matrices(helper)
            original_check = cache.PhaseByteSnapshot.check
            hits = 0
            def changed_after_hit(snapshot, path, expected):
                nonlocal hits
                result = original_check(snapshot, path, expected)
                if path == f.header:
                    hits += 1
                    if hits == 2:
                        f.header.write_text('changed after duplicate-path validation\n')
                return result
            with patch.object(cache.PhaseByteSnapshot, 'check', changed_after_hit):
                with self.assertRaisesRegex(ValueError, 'input changed'):
                    cache.verify_compilation_result(proof, f.composition, originals, projects)
            self.assertGreaterEqual(hits, 2)

    def test_postbuild_verification_rejects_cross_row_conflicting_dependency_hash(self):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            proof, originals, projects = f.build_matrices(helper)
            originals['results'][1]['dependency_sha256'][str(f.header)] = 'f' * 64
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                cache.verify_compilation_result(proof, f.composition, originals, projects)

    def assert_fresh_compiled_stack_tamper_detected(self, usage_file):
        f = self.fixture
        with f.patches():
            helper = f.instance()
            key = ('project', 'packages/test/two.cpp')
            f.sources[key].write_text('fresh compiled callback source\n')
            proof, originals, projects = f.build_matrices(helper)
            fresh = next(row for row in projects['results'] if row['source'] == key[1])
            self.assertNotIn('native_cache_reuse', fresh)
            capture_path = Path(fresh['stack_usage']['path'])
            capture = json.loads(capture_path.read_bytes())
            path = Path(capture['usage_file']) if usage_file else capture_path
            expected = capture['usage_sha256'] if usage_file else fresh['stack_usage']['sha256']
            original_finish = cache.PhaseByteSnapshot.finish
            def tamper_after_enrolled_hit(snapshot):
                self.assertIn(str(path), snapshot.files)
                snapshot.check(path, expected)  # prove this is an existing phase-cache hit
                path.write_bytes(b'changed after fresh compiler stack validation')
                return original_finish(snapshot)
            with patch.object(cache.PhaseByteSnapshot, 'finish', tamper_after_enrolled_hit):
                with self.assertRaisesRegex(ValueError, 'input changed'):
                    cache.verify_compilation_result(proof, f.composition, originals, projects)

    def test_fresh_compiled_stack_capture_is_rechecked_at_phase_end(self):
        self.assert_fresh_compiled_stack_tamper_detected(usage_file=False)

    def test_fresh_compiled_usage_file_is_rechecked_at_phase_end(self):
        self.assert_fresh_compiled_stack_tamper_detected(usage_file=True)


if __name__ == '__main__':
    unittest.main()
