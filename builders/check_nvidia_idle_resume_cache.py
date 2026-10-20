#!/usr/bin/env python3
"""Fetch one pinned native cache and restore sources without compilation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

REPO = 'MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86'
COMMIT = '4939252f7c5ab2ee72a26e626f8db2b7b5922c8e'
RUN = 39447802669
ARTIFACT = 12278871334
ARCHIVE_SHA = '54e6bd2b210fb6f903da38df19f2d185afa8204a905f64a91cc5bc925c0cd1fd'
REPORT_SHA = '3875dfb142cf040882d58e94f52cf260f493ebb0d06c07e80f810f5898f2f5aa'
NATIVE_PATHS = {'.github/workflows/build-nvidia-idle-image.yml',
    '.github/workflows/check-nvidia-execution-development.yml',
    '.github/workflows/resume-nvidia-idle-link-once.yml'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/' + REPO + '/' + path]))


def refuse_overlap():
    current = int(os.environ['GITHUB_RUN_ID'])
    for status in ('in_progress', 'queued', 'waiting', 'requested', 'pending'):
        result = api('actions/runs?status=' + status + '&per_page=100')
        require(result['total_count'] < 100, 'Active run inventory requires pagination; stopping before native work')
        others = [row['id'] for row in result['workflow_runs'] if row['id'] != current
                  and row['path'].split('@', 1)[0] in NATIVE_PATHS]
        require(not others, 'Another native workflow is active: ' + repr(others))


def extract_pinned(archive, destination):
    require(not destination.exists(), 'Cache extraction requires a fresh directory')
    with zipfile.ZipFile(archive) as bundle:
        rows = bundle.infolist()
        require(len(rows) == 9081 and sum(r.file_size for r in rows) == 311664901,
                'Pinned artifact inventory changed')
        names = set()
        for row in rows:
            path = Path(row.filename)
            mode = row.external_attr >> 16
            require(row.filename and not path.is_absolute() and '\\' not in row.filename
                    and '..' not in path.parts and path.as_posix() == row.filename
                    and row.filename not in names and not row.is_dir()
                    and not stat.S_ISLNK(mode), 'Unsafe cached artifact member')
            names.add(row.filename)
        bundle.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--linux-source-preflight', action='store_true')
    args = parser.parse_args()
    receipt = {'status': 'failed', 'native_jobs_started_by_helper': 0,
               'compilation_performed': False, 'link_performed': False}
    try:
        require(os.environ.get('GITHUB_REPOSITORY') == REPO, 'Unexpected repository')
        refuse_overlap()
        run = api('actions/runs/' + str(RUN))
        require(run['head_sha'] == COMMIT and run['status'] == 'completed'
                and run['conclusion'] == 'failure'
                and run['path'] == '.github/workflows/build-nvidia-idle-image.yml',
                'Native cache run provenance changed')
        artifact = api('actions/artifacts/' + str(ARTIFACT))
        require(artifact['name'] == 'NVIDIA-idle-image-native-validation'
                and artifact['workflow_run']['id'] == RUN
                and artifact['workflow_run']['head_sha'] == COMMIT
                and artifact['size_in_bytes'] == 113859952 and artifact['expired'] is False,
                'Native cache artifact provenance changed')
        require(artifact.get('digest') == 'sha256:' + ARCHIVE_SHA,
                'Native cache artifact metadata digest changed')
        temporary = Path(os.environ['RUNNER_TEMP'])
        archive = temporary / 'nvidia-idle-4939252-native.zip'
        with archive.open('xb') as stream:
            subprocess.run(['gh', 'api', 'repos/' + REPO + '/actions/artifacts/' + str(ARTIFACT) + '/zip'],
                           stdout=stream, check=True)
        require(hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA,
                'Downloaded native archive SHA256 differs')
        destination = temporary / 'nvidia-idle-4939252-native'
        extract_pinned(archive, destination)
        historical = temporary / 'nvidia-idle-original-linker.py'
        with historical.open('xb') as stream:
            subprocess.run(['git', 'show', COMMIT + ':builders/link_nvidia_first_transaction.py'],
                           stdout=stream, check=True)
        command = [sys.executable, '-B', 'builders/restore_nvidia_idle_native.py',
            '--artifact-root', str(destination), '--report-sha256', REPORT_SHA,
            '--allow-failed-link-cache', '--upstream', str(Path.cwd() / 'build-src/nvidia-upstream'),
            '--kernel-sdk', str(Path.cwd() / 'build-src/MacKernelSDK'),
            '--original-linker-source', str(historical)]
        if args.linux_source_preflight:
            command.append('--linux-source-preflight')
        restored = json.loads(subprocess.check_output(command))
        require(restored['package_allowed'] is False and restored['compilation_performed'] is False
                and restored['link_performed'] is False, 'Restoration exceeded source-only scope')
        receipt.update(status='passed', artifact_id=ARTIFACT, archive_sha256=ARCHIVE_SHA,
                       source_commit=COMMIT, workflow_run_id=RUN, restoration=restored)
        print(json.dumps(receipt, indent=2, sort_keys=True))
    except Exception as error:
        receipt.update(failure_type=type(error).__name__, failure=str(error))
        raise
    finally:
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
