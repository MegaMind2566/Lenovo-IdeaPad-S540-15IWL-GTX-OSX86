#!/usr/bin/env python3
"""Reuse only byte-identical native compilation inputs from one pinned cache.

The historical failed link report remains immutable. Reuse is a compiler-cache
operation, never successful linking, package admission or kernel execution.
The caller must still parse every object and run all current symbol, stack,
metaclass, root-retention and final-image verifiers.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import threading

REPORT_SHA256 = '3875dfb142cf040882d58e94f52cf260f493ebb0d06c07e80f810f5898f2f5aa'
PROVENANCE = {'workflow_run_id': 39447802669, 'artifact_id': 12278871334,
              'source_commit': '4939252f7c5ab2ee72a26e626f8db2b7b5922c8e'}
CANONICAL_ROOT = Path('/Users/runner/work/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86')
ORIGINAL_COUNT, PROJECT_COUNT = 1100, 60
RUNTIME_OBJECTS = ('firmware-bytes.o', 'c_start.o', 'c_stop.o')
PUBLIC_CALLBACK_REBUILDS = {
    ('project', 'packages/nvidia-darwin-services/src/S540NvidiaDarwinTimer.cpp'),
    ('project', 'packages/nvidia-darwin-services/src/S540NvidiaDarwinWork.cpp')}
CLOSED = {'hardware_admission': False, 'original_entry_admission': False,
          'production_candidate_allowed': False, 'gpu_access': False,
          'kernel_execution': 'not_tested'}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def no_symlink(path: Path) -> None:
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            'Selective native cache refuses symlinks: ' + str(path))


def regular(path: Path) -> None:
    no_symlink(path)
    require(path.is_file(), 'Missing regular native cache file: ' + str(path))


def read_bound(path: Path, expected: str) -> bytes:
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected) is not None,
            'Malformed native cache SHA256')
    regular(path)
    data = path.read_bytes()
    require(sha_bytes(data) == expected, 'Changed native cache bytes: ' + str(path))
    return data


def exact(record: dict, expected: dict, label: str) -> None:
    for key, value in expected.items():
        require(type(record.get(key)) is type(value) and record[key] == value,
                'Selective native cache ' + label + ' differs: ' + key)


def canonical_paths() -> tuple[Path, Path]:
    build = CANONICAL_ROOT / 'build/nvidia-idle-image'
    return build, build / 'first-transaction-image/composition'


def confined_relative(value: str) -> Path:
    require(isinstance(value, str) and value and '\\' not in value,
            'Invalid native cache relative path')
    result = Path(value)
    require(not result.is_absolute() and result.as_posix() == value and
            all(part not in ('', '.', '..') for part in result.parts) and str(result) != '.',
            'Unconfined native cache relative path: ' + value)
    return result


def cache_path(artifact: Path, recorded: str) -> Path:
    build, _ = canonical_paths()
    path = Path(recorded)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(build),
            'Native cache path escaped its canonical build: ' + recorded)
    result = artifact / confined_relative(path.relative_to(build).as_posix())
    no_symlink(result)
    return result


def _source_path(kind: str, row: dict) -> Path:
    _, composition = canonical_paths()
    relative = confined_relative(row['source'])
    if kind == 'original' and row['source'] == 'generated/g_nvid_string.c':
        return composition / 'original-objects/g_nvid_string.c'
    return composition / ('source' if kind == 'original' else 'project') / relative


def _source_hash(kind: str, row: dict) -> str:
    return row['source_sha256' if kind == 'original' else 'sha256']


def _verify_stack(artifact: Path, kind: str, row: dict, obj: Path) -> dict:
    reference = row['stack_usage']
    require(reference['path'] == str(obj.with_suffix('.stack.json')),
            'Native stack capture moved away from its object')
    capture = json.loads(read_bound(cache_path(artifact, reference['path']), reference['sha256']))
    exact(capture, {'format': 1, 'status': 'compiler-stack-usage-captured',
        'native_apple_compiler': True, 'source': str(_source_path(kind, row)),
        'source_sha256': _source_hash(kind, row), 'object': str(obj),
        'object_sha256': row['object_sha256'], 'command': row['command'],
        'cwd': row['cwd'], 'command_sha256': sha_bytes(json.dumps(row['command']).encode()),
        'kernel_execution': 'not_tested', 'production_candidate_allowed': False}, 'stack capture')
    if capture['usage_file'] is None:
        exact(capture, {'usage_sha256': None,
            'usage_emission': 'not-emitted-for-object-without-executable-code',
            'functions': []}, 'absent stack usage')
        require(not cache_path(artifact, str(obj.with_suffix('.su'))).exists(),
                'Unexpected stack usage beside an absent-output capture')
    else:
        exact(capture, {'usage_file': str(obj.with_suffix('.su')),
                        'usage_emission': 'compiler-file'}, 'stack usage')
        read_bound(cache_path(artifact, capture['usage_file']), capture['usage_sha256'])
    require(reference['function_count'] == len(capture['functions']) and
            reference['dynamic_function_count'] == sum(not f['static_frame_known'] for f in capture['functions']) and
            reference['native_apple_compiler'] is True,
            'Native stack summary differs from its bound capture')
    return capture


def verify_cache(artifact: Path) -> dict:
    """Verify the complete historical cache read-only, on any host.

    The single pinned top-level report authenticates the composition, both
    compiler matrices and every object/stack capture. No runtime opt-out of
    its digest or full inventory exists.
    """
    no_symlink(artifact)
    artifact = artifact.resolve(strict=True)
    require(artifact.is_dir(), 'A native artifact directory is required')
    _, composition_path = canonical_paths()
    report_path = artifact / 'first-transaction-image/first-transaction-image.json'
    report = json.loads(read_bound(report_path, REPORT_SHA256))
    exact(report, {'format': 1, 'status': 'failed',
        'phase': 'link-same-complete-relocatable-image',
        'failure_type': 'ValueError',
        'failure': 'The non-dead-stripping combined image lost or gained an external definition',
        'host_system': 'Darwin', 'host_control': False,
        'native_darwin_compilation': True, 'original_compilation_performed': True,
        'project_compilation_performed': True, 'actual_link_performed': False,
        'final_link_attempted': False, 'module_loaded': False,
        'installable_bundle_created': False, 'composition_directory': str(composition_path),
        **CLOSED}, 'historical report')
    require(not any(name in report for name in ('relocatable_image', 'final_image')),
            'Historical failed cache unexpectedly claims completed image proof')
    plan = report['source_plan']
    exact(plan, {'complete_original_translation_units': ORIGINAL_COUNT,
        'canonical_project_translation_units': PROJECT_COUNT,
        'firmware_objects': 1, 'pinned_libkmod_c_wrappers': ['c_start.o', 'c_stop.o'],
        'total_expected_link_objects': ORIGINAL_COUNT + PROJECT_COUNT + len(RUNTIME_OBJECTS),
        'make_declared_original_source_plan_verified': True}, 'source plan')
    composition = json.loads(read_bound(artifact / 'first-transaction-image/composition/composition.json',
                                       report['composition_sha256']))
    exact(composition, {'format': 1, 'status': 'materialized-source-only', **CLOSED}, 'composition')
    matrices, indexed, captures, objects = {}, {}, {}, {}
    for kind, count, filename, binding, sources in (
        ('original', ORIGINAL_COUNT, 'full-original-compilation.json', 'original_sha256', plan['declared_original_sources']),
        ('project', PROJECT_COUNT, 'project-compilation.json', 'project_sha256', plan['project_sources'])):
        matrix = json.loads(read_bound(artifact / 'first-transaction-image/composition' / filename,
                                       report['compilation_reports'][binding]))
        exact(matrix, {'format': 1, 'status': 'compiled-full-original-source-only' if kind == 'original'
            else 'compiled-project-source-only', 'host_system': 'Darwin', 'host_control': False,
            'native_darwin_compilation': True, 'composition_sha256': report['composition_sha256'],
            'original_entry_admission': False, 'production_candidate_allowed': False,
            'gpu_access': False, 'kernel_execution': 'not_tested'}, kind + ' compiler matrix')
        if kind == 'original':
            exact(matrix, {'native_apple_compiler': True, 'cross_compile_probe': False,
                           'failures': []}, 'original compiler identity')
        expected_compilers = (dict.fromkeys(('cc', 'cxx'), report['compilers']['cc'])
                              if kind == 'original' else report['compilers'])
        require(matrix['compilers'] == expected_compilers,
                'Native compiler matrix identity differs from the pinned linker report')
        rows = matrix['results']
        require(len(rows) == count and len(set(sources)) == count and
                len({r['source'] for r in rows}) == count and {r['source'] for r in rows} == set(sources),
                'Incomplete or duplicate native compiler inventory: ' + kind)
        indexed[kind], captures[kind] = {}, {}
        for row in rows:
            confined_relative(row['source'])
            name = confined_relative(row['object'])
            require(len(name.parts) == 1, 'Native object basename escaped its directory')
            obj = composition_path / (kind + '-objects') / name
            require(str(obj) not in objects, 'Duplicate native cache object')
            read_bound(cache_path(artifact, str(obj)), row['object_sha256'])
            require(isinstance(row.get('dependency_sha256'), dict) and row['dependency_sha256'],
                    'Native cache row has no compiler-produced dependency inventory')
            source_path = str(_source_path(kind, row))
            require(row['dependency_sha256'].get(source_path) == _source_hash(kind, row),
                    'Native source is absent from its recorded dependencies')
            require(isinstance(row['command'], list) and row['command'] and
                    row['command'].count('-c') == row['command'].count('-o') == 1 and
                    row['command'][row['command'].index('-o') + 1] == str(obj) and
                    row['cwd'] == str(composition_path / ('source/src/nvidia' if kind == 'original' else 'project')),
                    'Malformed native compile command or working directory')
            command_source = Path(row['command'][row['command'].index('-c') + 1])
            if not command_source.is_absolute():
                command_source = Path(row['cwd']) / command_source
            require(os.path.normpath(command_source) == source_path,
                    'Native command source differs from its recorded source')
            for dependency, digest in row['dependency_sha256'].items():
                dep = Path(dependency)
                require(dep.is_absolute() and '..' not in dep.parts and
                        isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest) is not None,
                        'Malformed native dependency record')
            captures[kind][row['source']] = _verify_stack(artifact, kind, row, obj)
            indexed[kind][row['source']] = row
            objects[str(obj)] = row['object_sha256']
        matrices[kind] = matrix
    for name in RUNTIME_OBJECTS:
        obj = composition_path.parent / name
        expected = report['input_object_sha256'].get(str(obj))
        read_bound(cache_path(artifact, str(obj)), expected)
        objects[str(obj)] = expected
    require(objects == report['input_object_sha256'], 'Full native cache object mapping changed')
    return {'artifact': artifact, 'report': report, 'composition': composition,
            'matrices': matrices, 'rows': indexed, 'captures': captures,
            'object_count': len(objects), 'historical_report_sha256': REPORT_SHA256}


def reuse_provenance(previous: dict, current_composition_sha256: str) -> dict:
    return {**PROVENANCE, 'historical_report_sha256': REPORT_SHA256,
        'historical_composition_sha256': previous['composition_sha256'],
        'current_composition_sha256': current_composition_sha256,
        'compiled_this_run': False, 'object_bytes_unchanged': True,
        'exact_command_and_cwd_unchanged': True,
        'all_recorded_dependencies_unchanged': True,
        'stack_capture_bytes_unchanged': True}


def rebuild_scope_rows(scope: set[tuple[str, str]] | None) -> list[dict] | None:
    if scope is None:
        return None
    require(type(scope) is set and scope == PUBLIC_CALLBACK_REBUILDS,
            'Controlled native rebuild scope must be exactly the two public callback sources')
    return [{'kind': kind, 'source': source} for kind, source in sorted(scope)]


def require_allowed_miss(scope: set[tuple[str, str]] | None,
                         key: tuple[str, str], reason: str) -> None:
    if scope is None:
        return
    require(key in scope and (reason == 'source-changed-or-missing' or
            reason.startswith('dependency-changed-or-missing:')),
            'Controlled native rebuild refused an unexpected compiler cache miss: ' +
            repr(key) + '; ' + reason)


class SelectiveNativeCache:
    """Thread-safe decisions for a fresh composition at the exact old paths."""

    def __init__(self, artifact: Path, *, composition: Path,
                 current_identity: dict, sdk: dict,
                 allowed_rebuilds: set[tuple[str, str]] | None = None):
        require(platform.system() == 'Darwin' and platform.machine() == 'x86_64',
                'Native object reuse requires an actual Intel Darwin host')
        rebuild_scope_rows(allowed_rebuilds)
        self.allowed_rebuilds = None if allowed_rebuilds is None else set(allowed_rebuilds)
        self.verified = verify_cache(artifact)
        self.artifact = self.verified['artifact']
        self.previous = self.verified['report']
        no_symlink(composition)
        self.composition = composition.resolve(strict=True)
        require(self.composition == canonical_paths()[1],
                'Selective reuse requires unchanged canonical absolute composition paths')
        exact(current_identity, {'host_system': 'Darwin', 'host_control': False,
            'native_darwin_compilation': True, 'compilers': self.previous['compilers']}, 'current compiler identity')
        require(sdk == self.previous['sdk'], 'Selective native reuse SDK identity changed')
        self.identity = deepcopy(current_identity)
        current_manifest = self.composition / 'composition.json'
        regular(current_manifest)
        manifest_bytes = current_manifest.read_bytes()
        manifest = json.loads(manifest_bytes)
        exact(manifest, {'format': 1, 'status': 'materialized-source-only',
                         **CLOSED}, 'current composition')
        require(not manifest.get('fixed_source_profiles', {}).get('public_callback_closure') or
                self.allowed_rebuilds is not None,
                'The public callback successor requires the explicit two-source rebuild cost guard')
        self.composition_sha256 = sha_bytes(manifest_bytes)
        self._lock = threading.RLock()
        self._decisions: dict[tuple[str, str], dict] = {}
        self._hashes: dict[str, tuple[tuple, str]] = {}

    def _current_hash(self, path: Path) -> str | None:
        no_symlink(path)
        if not path.is_file():
            return None
        before = path.stat()
        signature = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        key = str(path)
        with self._lock:
            old = self._hashes.get(key)
        if old and old[0] == signature:
            return old[1]
        digest = sha_bytes(path.read_bytes())
        after = path.stat()
        require(signature == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'A current compilation dependency changed while hashing: ' + str(path))
        with self._lock:
            self._hashes[key] = (signature, digest)
        return digest

    def _decision(self, key: tuple[str, str], decision: dict) -> None:
        with self._lock:
            require(key not in self._decisions, 'A native source received duplicate cache decisions: ' + repr(key))
            self._decisions[key] = decision

    def reuse(self, *, kind: str, source: Path, command: list[str], cwd: Path,
              obj: Path, plan_row: dict | None = None,
              current_identity: dict | None = None) -> dict | None:
        require(kind in ('original', 'project'), 'Unknown native compilation kind')
        require(source.is_absolute() and cwd.is_absolute() and obj.is_absolute(),
                'Selective reuse accepts exact absolute source/cwd/object paths')
        no_symlink(source); no_symlink(cwd); no_symlink(obj)
        require(obj.parent == self.composition / (kind + '-objects') and not obj.exists(),
                'Selective reuse requires a fresh canonical object destination')
        if kind == 'original' and source == self.composition / 'original-objects/g_nvid_string.c':
            relative = 'generated/g_nvid_string.c'
        else:
            root = self.composition / ('source' if kind == 'original' else 'project')
            require(source.is_relative_to(root), 'Native source escaped the fresh composition')
            relative = source.relative_to(root).as_posix()
        key = (kind, relative)
        old = self.verified['rows'][kind].get(relative)
        reason = None
        if old is None:
            reason = 'new-source'
        elif current_identity is not None and any(current_identity.get(k) != self.verified['matrices'][kind].get(k)
                for k in ('host_system', 'host_control', 'native_darwin_compilation', 'compilers')):
            raise ValueError('Current source compiler identity differs from its native cache matrix')
        elif command != old['command'] or str(cwd) != old['cwd'] or obj.name != old['object']:
            reason = 'compile-command-or-cwd-changed'
        elif self._current_hash(source) != _source_hash(kind, old):
            reason = 'source-changed-or-missing'
        else:
            for dependency, expected in old['dependency_sha256'].items():
                if self._current_hash(Path(dependency)) != expected:
                    reason = 'dependency-changed-or-missing:' + dependency
                    break
        if reason is not None:
            require_allowed_miss(self.allowed_rebuilds, key, reason)
            self._decision(key, {'decision': 'compile-required', 'reason': reason,
                                 'compiled_this_run': False})
            return None
        assert old is not None
        if plan_row is not None:
            require(plan_row.get('source') == relative,
                    'Current native source-plan row does not match its source')
            require(set(plan_row) <= {'source', 'kind', 'sha256', 'source_sha256',
                'compile_definitions', 'expected_definitions', 'expected_imports',
                'allowed_compiler_memory_imports', 'original_include_directories'},
                'A source-plan row attempted to replace authenticated compiler results')
            source_hash = plan_row.get('sha256', plan_row.get('source_sha256'))
            require(source_hash is None or source_hash == _source_hash(kind, old),
                    'Current source-plan digest differs from its verified source')
        capture = self.verified['captures'][kind][relative]
        files = [(str(obj), old['object_sha256']),
                 (old['stack_usage']['path'], old['stack_usage']['sha256'])]
        if capture['usage_file'] is not None:
            files.append((capture['usage_file'], capture['usage_sha256']))
        # Read/hash all authenticated bytes before writing any destination.
        pending = [(Path(path), read_bound(cache_path(self.artifact, path), digest), digest)
                   for path, digest in files]
        require(all(path.parent == obj.parent and not path.exists() for path, _, _ in pending),
                'Native cache destination is not fresh')
        for path, data, digest in pending:
            no_symlink(path)
            with path.open('xb') as stream:
                stream.write(data)
            require(sha_bytes(path.read_bytes()) == digest, 'Copied native artifact bytes changed')
        result = deepcopy(old)
        if plan_row is not None:
            # New verification requirements remain current; source/command and
            # compiler results are authenticated separately above.
            result.update(deepcopy(plan_row))
        result['native_cache_reuse'] = reuse_provenance(self.previous, self.composition_sha256)
        self._decision(key, {'decision': 'reused-native-object', 'compiled_this_run': False})
        return result

    def record_compiled(self, *, kind: str, source: str) -> None:
        """Call only after the current compiler and existing row checks pass."""
        with self._lock:
            row = self._decisions.get((kind, source))
            require(row is not None and row['decision'] == 'compile-required' and not row['compiled_this_run'],
                    'No unique outstanding native compilation decision')
            row['compiled_this_run'] = True

    def report(self, *, require_complete: bool = False) -> dict:
        require(sha_bytes((self.composition / 'composition.json').read_bytes()) == self.composition_sha256,
                'The fresh composition manifest changed during native compilation')
        with self._lock:
            decisions = deepcopy(self._decisions)
        groups = {}
        for kind, expected in (('original', ORIGINAL_COUNT), ('project', PROJECT_COUNT)):
            rows = {source: decision for (group, source), decision in decisions.items() if group == kind}
            reused = sum(r['decision'] == 'reused-native-object' for r in rows.values())
            required = sum(r['decision'] == 'compile-required' for r in rows.values())
            compiled = sum(r['compiled_this_run'] for r in rows.values())
            groups[kind] = {'planned_sources': len(rows), 'expected_sources': expected,
                'reused_objects': reused, 'compile_required': required,
                'compiled_this_run': compiled, 'complete': len(rows) == expected and required == compiled,
                'sources': rows}
        complete = all(group['complete'] for group in groups.values())
        if require_complete:
            require(complete, 'Selective native compiler matrix is incomplete')
        return {'format': 1, 'mode': 'pinned-exact-native-object-reuse', **PROVENANCE,
            'historical_report_sha256': REPORT_SHA256,
            'historical_status': self.previous['status'],
            'historical_phase': self.previous['phase'],
            'historical_full_cache_object_count': self.verified['object_count'],
            'compilers': deepcopy(self.previous['compilers']),
            'sdk': deepcopy(self.previous['sdk']),
            'allowed_rebuilds': rebuild_scope_rows(self.allowed_rebuilds),
            'current_composition_sha256': self.composition_sha256,
            'original': groups['original'], 'project': groups['project'],
            'complete': complete, 'actual_link_performed': False,
            'module_loaded': False, **CLOSED}


def verify_compilation_result(proof: dict, composition: Path,
                              originals: dict, projects: dict) -> dict:
    """Independently recheck cache provenance after compile/link or packaging.

    Both inputs are complete current compilation reports, not their row lists.
    This read-only verifier is host-independent; its current compiler reports
    must claim the same independently verified native compiler identity as the
    authenticated historical matrices. It never executes or modifies objects.
    """
    require(isinstance(proof, dict) and isinstance(proof.get('artifact_root'), str),
            'An explicit selective native artifact-root binding is required')
    verified = verify_cache(Path(proof['artifact_root']))
    previous = verified['report']
    no_symlink(composition)
    composition = composition.resolve(strict=True)
    require(composition == canonical_paths()[1], 'Post-build selective cache composition path changed')
    manifest_path = composition / 'composition.json'
    regular(manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    composition_sha = sha_bytes(manifest_bytes)
    manifest = json.loads(manifest_bytes)
    exact(manifest, {'format': 1, 'status': 'materialized-source-only',
                     **CLOSED}, 'post-build composition')
    exact(proof, {'format': 1, 'mode': 'pinned-exact-native-object-reuse', **PROVENANCE,
        'historical_report_sha256': REPORT_SHA256, 'historical_status': previous['status'],
        'historical_phase': previous['phase'],
        'historical_full_cache_object_count': verified['object_count'],
        'compilers': previous['compilers'], 'sdk': previous['sdk'],
        'current_composition_sha256': composition_sha, 'complete': True,
        'actual_link_performed': False, 'module_loaded': False, **CLOSED}, 'post-build proof')
    expected_binding = reuse_provenance(previous, composition_sha)
    require('allowed_rebuilds' in proof, 'Selective native proof lost its explicit rebuild-scope policy')
    scope_rows = proof['allowed_rebuilds']
    require(not manifest.get('fixed_source_profiles', {}).get('public_callback_closure') or
            scope_rows is not None,
            'The public callback proof lost its mandatory two-source rebuild cost guard')
    if scope_rows is None:
        allowed_rebuilds = None
    else:
        require(scope_rows == rebuild_scope_rows(set(PUBLIC_CALLBACK_REBUILDS)),
                'Post-build controlled native rebuild scope changed')
        allowed_rebuilds = set(PUBLIC_CALLBACK_REBUILDS)
    digest_cache = {}
    def current_bytes(path: Path, expected: str):
        regular(path)
        key = str(path)
        if key not in digest_cache:
            digest_cache[key] = sha_bytes(path.read_bytes())
        require(digest_cache[key] == expected, 'Current native compilation input changed: ' + key)
    for kind, count, matrix in (('original', ORIGINAL_COUNT, originals), ('project', PROJECT_COUNT, projects)):
        old_matrix = verified['matrices'][kind]
        exact(matrix, {'format': 1, 'status': old_matrix['status'],
            'host_system': 'Darwin', 'host_control': False, 'native_darwin_compilation': True,
            'compilers': old_matrix['compilers'], 'composition_sha256': composition_sha,
            'original_entry_admission': False, 'production_candidate_allowed': False,
            'kernel_execution': 'not_tested', 'gpu_access': False}, 'current ' + kind + ' matrix')
        if kind == 'original':
            exact(matrix, {'native_apple_compiler': True, 'cross_compile_probe': False,
                           'failures': []}, 'current original compiler')
        rows = matrix['results']
        require(len(rows) == count and len({row['source'] for row in rows}) == count,
                'Post-build selective matrix is incomplete or duplicated')
        group = proof[kind]
        require(isinstance(group, dict) and isinstance(group.get('sources'), dict) and
                set(group['sources']) == {row['source'] for row in rows},
                'Post-build cache decisions differ from current source inventory')
        reused = compiled = 0
        for row in rows:
            confined_relative(row['source'])
            decision = group['sources'][row['source']]
            source = _source_path(kind, row)
            obj = composition / (kind + '-objects') / confined_relative(row['object'])
            require(len(Path(row['object']).parts) == 1,
                    'Current native object escaped its source directory')
            current_bytes(source, _source_hash(kind, row))
            current_bytes(obj, row['object_sha256'])
            require(isinstance(row.get('dependency_sha256'), dict) and row['dependency_sha256'],
                    'Current native row lost its dependency bindings')
            for dependency, expected in row['dependency_sha256'].items():
                require(Path(dependency).is_absolute() and '..' not in Path(dependency).parts,
                        'Current native dependency lost its absolute path binding')
                current_bytes(Path(dependency), expected)
            _verify_stack(canonical_paths()[0], kind, row, obj)
            if decision.get('decision') == 'reused-native-object':
                exact(decision, {'decision': 'reused-native-object', 'compiled_this_run': False},
                      'reused source decision')
                old = verified['rows'][kind].get(row['source'])
                require(old is not None and row.get('native_cache_reuse') == expected_binding,
                        'Missing or forged selective native object provenance')
                for key in ('source', 'object', 'object_sha256', 'command', 'cwd', 'dependency_sha256',
                            'stack_usage', 'definitions', 'imports', 'sections', 'weak_definitions',
                            'compiler_memory_imports', 'compile_definitions',
                            'source_sha256' if kind == 'original' else 'sha256'):
                    require(row.get(key) == old.get(key),
                            'A reused native compiler result changed: ' + key)
                capture = verified['captures'][kind][row['source']]
                current_bytes(Path(old['stack_usage']['path']), old['stack_usage']['sha256'])
                if capture['usage_file'] is not None:
                    current_bytes(Path(capture['usage_file']), capture['usage_sha256'])
                else:
                    require(not obj.with_suffix('.su').exists(),
                            'Unexpected current .su output for an empty cached unit')
                reused += 1
            else:
                exact(decision, {'decision': 'compile-required', 'compiled_this_run': True},
                      'newly compiled source decision')
                require(isinstance(decision.get('reason'), str) and bool(decision['reason']) and
                        'native_cache_reuse' not in row,
                        'A newly compiled row claims inconsistent native cache provenance')
                require_allowed_miss(allowed_rebuilds, (kind, row['source']), decision['reason'])
                compiled += 1
        exact(group, {'planned_sources': count, 'expected_sources': count,
            'reused_objects': reused, 'compile_required': compiled,
            'compiled_this_run': compiled, 'complete': True}, kind + ' cache counts')
    return deepcopy(proof)
