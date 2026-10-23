#!/usr/bin/env python3
"""Exercise the actual workflow request parser against real temporary commits."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

HERE = Path(__file__).resolve().parents[1]
WORKFLOW = HERE.parents[2] / '.github/workflows/build-nvidia-retained-first-init.yml'
REQUEST = '.github/native-ci/nvidia-retained-first-init-request.json'
TEXT = WORKFLOW.read_text()
BODY = textwrap.dedent(TEXT.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])


class RequestControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Isolated workflow fixture')
        (self.path / 'source.c').write_text('int fixture;\n')
        self.git('add', 'source.c')
        self.git('commit', '-qm', 'Reviewed fixture source [skip ci]')
        self.source = self.git('rev-parse', 'HEAD')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.path, text=True,
            stderr=subprocess.DEVNULL).strip()

    def request(self, *, message='Reviewed test request [native ci]', extra_file=False, **changes):
        value = {'format': 1, 'scope': 's540-retained-first-initialization',
            'batch_id': 'isolated-retained-batch-0001', 'source_commit': self.source}
        value.update(changes)
        path = self.path / REQUEST
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(value))
        if extra_file:
            (self.path / 'source.c').write_text('int changed_during_request;\n')
        self.git('add', '.')
        self.git('commit', '-qm', message)

    def execute(self, event='push', batch='isolated-retained-batch-0001'):
        body = self.path / 'actual-workflow-request-parser.py'
        body.write_text(BODY)
        payload = self.path / 'event.json'
        payload.write_text(json.dumps({'inputs': {'batch_id': batch}}))
        output = self.path / 'output.txt'
        env = dict(os.environ, GITHUB_SHA=self.git('rev-parse', 'HEAD'),
            GITHUB_REF='refs/heads/main', GITHUB_EVENT_NAME=event,
            GITHUB_EVENT_PATH=str(payload), GITHUB_OUTPUT=str(output))
        run = subprocess.run(['python3', '-B', str(body)], cwd=self.path,
            env=env, capture_output=True, text=True)
        return run, output.read_text() if output.exists() else ''

    def test_exact_one_file_final_request(self):
        self.request()
        run, output = self.execute()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('requested=true\n', output)
        self.assertIn('source_commit=' + self.source + '\n', output)

    def test_large_push_fallback_cannot_admit_source_changes(self):
        self.request(extra_file=True)
        run, output = self.execute()
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(output, '')

    def test_missing_marker_cannot_admit_path_match(self):
        self.request(message='Unrequested fixture change')
        run, output = self.execute()
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(output, '')

    def test_skipped_commit_cannot_be_a_native_request(self):
        self.request(message='Ambiguous [native ci] [skip ci]')
        run, _ = self.execute()
        self.assertNotEqual(run.returncode, 0)

    def test_wrong_source_parent_is_rejected(self):
        self.request(source_commit='0' * 40)
        run, _ = self.execute()
        self.assertNotEqual(run.returncode, 0)

    def test_wrong_scope_is_rejected(self):
        self.request(scope='idle-loader')
        run, _ = self.execute()
        self.assertNotEqual(run.returncode, 0)

    def test_unknown_schema_field_is_rejected(self):
        self.request(allow_paid_runner=True)
        run, _ = self.execute()
        self.assertNotEqual(run.returncode, 0)

    def test_output_injection_is_rejected(self):
        self.request(batch_id='validbatch\nrequested=true')
        run, _ = self.execute()
        self.assertNotEqual(run.returncode, 0)

    def test_manual_dispatch_is_explicit_and_source_bound(self):
        run, output = self.execute(event='workflow_dispatch')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('source_commit=' + self.source + '\n', output)

    def test_manual_dispatch_rejects_missing_unique_batch(self):
        run, _ = self.execute(event='workflow_dispatch', batch='')
        self.assertNotEqual(run.returncode, 0)

    def test_both_job_guards_and_standard_runners_remain(self):
        self.assertEqual(TEXT.count('github.event.repository.private == false'), 2)
        self.assertIn("needs.source-preflight.outputs.requested == 'true'", TEXT)
        self.assertEqual(re.findall(r'^    runs-on: (.+)$', TEXT, re.M),
                         ['ubuntu-24.04', 'macos-15-intel'])
        self.assertIn('cancel-in-progress: false', TEXT)
        self.assertNotIn('actions/cache', TEXT)
        self.assertNotIn('retention-days: 30', TEXT)


if __name__ == '__main__':
    unittest.main()
