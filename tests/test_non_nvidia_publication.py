#!/usr/bin/env python3
"""Hardware-free publication guards; all GitHub mutations are mocked."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publisher', ROOT / 'builders/publish_non_nvidia_release.py')
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)
HEAD, PARENT = '1' * 40, '2' * 40
NOTES = 'An ongoing development release.'


class PublicationGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = {}
        for n in range(6):
            p = self.root / ('asset-' + str(n))
            p.write_bytes(('reviewed-' + str(n)).encode())
            self.assets[p.name] = p

    def tearDown(self):
        self.temp.cleanup()

    def record(self, names=(), draft=True):
        return {'id': 30, 'tag_name': pub.TAG, 'target_commitish': HEAD, 'name': pub.TITLE,
                'prerelease': False, 'draft': draft, 'body': NOTES, 'html_url': 'https://example.invalid/v0.3.0',
                'assets': [{'id': n + 1, 'name': k, 'state': 'uploaded',
                            'size': len(self.assets[k].read_bytes()),
                            'digest': 'sha256:' + pub.sha(self.assets[k].read_bytes())}
                           for n, k in enumerate(names)]}

    def simulate(self, initial=None, tag=None):
        state = {'value': initial, 'tag': tag, 'create': 0, 'upload': 0, 'patch': 0}
        def run(command, **kwargs):
            if command[0:3] == ['gh', 'release', 'create']:
                self.assertIsNone(state['value'])
                state['value'] = self.record()
                state['create'] += 1
            elif command[0:3] == ['gh', 'release', 'upload']:
                name = Path(command[4]).name
                self.assertNotIn(name, {a['name'] for a in state['value']['assets']})
                asset = self.record([name])['assets'][0]
                asset['id'] = len(state['value']['assets']) + 1
                state['value']['assets'].append(asset)
                state['upload'] += 1
            else:
                raise AssertionError('Unexpected subprocess: ' + repr(command))
            return types.SimpleNamespace(returncode=0)
        def api(endpoint, method='GET', body=None, missing_ok=False):
            if endpoint == 'git/ref/tags/' + pub.TAG:
                return copy.deepcopy(state['tag'])
            if endpoint == 'releases/30' and method == 'PATCH':
                self.assertEqual(body, {'draft': False, 'make_latest': 'true'})
                state['value']['draft'] = False
                state['tag'] = {'object': {'type': 'commit', 'sha': HEAD}}
                state['patch'] += 1
                return copy.deepcopy(state['value'])
            raise AssertionError('Unexpected API: ' + endpoint)
        def download(identifier):
            asset = next(a for a in state['value']['assets'] if a['id'] == identifier)
            return self.assets[asset['name']].read_bytes()
        with patch.object(pub, 'validate_request', return_value=HEAD), \
             patch.object(pub, 'validate_assets', return_value=self.assets), \
             patch.object(pub, 'release_notes', return_value=NOTES), \
             patch.object(pub, 'release', side_effect=lambda: copy.deepcopy(state['value'])), \
             patch.object(pub, 'api', side_effect=api), \
             patch.object(pub, 'download_asset', side_effect=download), \
             patch.object(pub.subprocess, 'run', side_effect=run):
            pub.publish(self.root)
        return state

    def test_new_draft_verified_then_published(self):
        s = self.simulate()
        self.assertEqual((s['create'], s['upload'], s['patch']), (1, 6, 1))

    def test_resume_same_draft_uploads_only_missing(self):
        s = self.simulate(self.record(list(self.assets)[:2]))
        self.assertEqual((s['create'], s['upload'], s['patch']), (0, 4, 1))

    def test_same_published_release_is_read_only(self):
        s = self.simulate(self.record(self.assets, False), {'object': {'type': 'commit', 'sha': HEAD}})
        self.assertEqual((s['create'], s['upload'], s['patch']), (0, 0, 0))

    def test_other_release_identity_is_refused(self):
        x = self.record()
        x['target_commitish'] = '3' * 40
        with self.assertRaises(ValueError):
            self.simulate(x)

    def test_wrong_existing_digest_is_refused(self):
        x = self.record(list(self.assets)[:1])
        x['assets'][0]['digest'] = 'sha256:' + '0' * 64
        with self.assertRaises(ValueError):
            self.simulate(x)

    def test_other_tag_is_refused(self):
        with self.assertRaises(ValueError):
            self.simulate(tag={'object': {'type': 'commit', 'sha': '3' * 40}})

    def test_remote_set_and_notes_guards(self):
        x = self.record()
        with self.assertRaises(ValueError):
            pub.validate_remote(x, HEAD, NOTES, self.assets, complete=True)
        x['body'] = 'Changed notes'
        with self.assertRaises(ValueError):
            pub.validate_remote(x, HEAD, NOTES, self.assets)
        x = self.record()
        x['assets'] = [{'name': 'foreign'}]
        with self.assertRaises(ValueError):
            pub.validate_remote(x, HEAD, NOTES, self.assets)

    def test_archive_paths_duplicates_and_links_are_refused(self):
        for name, mode, duplicate in [('../escape', 0, False), ('/escape', 0, False),
                                      ('a\\b', 0, False), ('link', 0o120777, False), ('x', 0, True)]:
            b = io.BytesIO()
            with zipfile.ZipFile(b, 'w') as z:
                i = zipfile.ZipInfo(name)
                i.external_attr = mode << 16
                z.writestr(i, b'bad')
                if duplicate:
                    z.writestr(i, b'duplicate')
            with self.assertRaises(ValueError):
                pub.unpack(b.getvalue())

    def test_explicit_request_binding_and_environment(self):
        for n in pub.BOUND_FILES:
            p = self.root / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('reviewed ' + n).encode())
        r = {'schema': 1, 'version': pub.TAG, 'batch': 'test-v0.3.0-20261024',
             'source_parent': PARENT,
             'files': {n: pub.sha((self.root / n).read_bytes()) for n in pub.BOUND_FILES}}
        request = self.root / pub.REQUEST
        request.parent.mkdir(parents=True, exist_ok=True)
        request.write_text(json.dumps(r))
        def git(command, **kwargs):
            if command == ['git', 'rev-parse', 'HEAD']:
                return HEAD + '\n'
            if command == ['git', 'rev-parse', 'HEAD^']:
                return PARENT + '\n'
            return pub.REQUEST + '\n'
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': pub.REPOSITORY,
               'GITHUB_REF': 'refs/heads/' + pub.BRANCH, 'GITHUB_SHA': HEAD}
        with patch.object(pub, 'ROOT', self.root), patch.object(pub.subprocess, 'check_output', side_effect=git), \
             patch.dict(os.environ, env):
            self.assertEqual(pub.validate_request(), HEAD)
            (self.root / pub.BOUND_FILES[0]).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                pub.validate_request()
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(ValueError):
                pub.validate_request()


if __name__ == '__main__':
    unittest.main()
