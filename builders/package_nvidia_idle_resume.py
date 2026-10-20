#!/usr/bin/env python3
"""Independently package a verified native link continuation for the closed idle test."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


def main():
    home = Path('build/nvidia-idle-image')
    report = home / 'first-transaction-image/first-transaction-image.json'
    record = json.loads(report.read_bytes())
    assert record['status'] == 'linked-native-development-image'
    assert record['source_plan']['complete_original_translation_units'] == 1100
    assert record['source_plan']['canonical_project_translation_units'] == 60
    assert record['source_plan']['total_expected_link_objects'] == 1163
    assert len(record['input_object_sha256']) == 1163
    assert record['native_compilation_reused'] is True
    assert record['original_compilation_performed'] is False
    assert record['project_compilation_performed'] is False
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    output = home / 'idle-complete-image-package'
    subprocess.run([sys.executable,
        'packages/nvidia-gsp-bootstrap/prospective-complete-image-package/package.py',
        '--report', str(report), '--report-sha256', digest,
        '--kernel-sdk', 'build-src/MacKernelSDK', '--assets-dir', str(home / 'firmware'),
        '--output', str(output), '--cc', '/usr/bin/clang', '--cxx', '/usr/bin/clang++'], check=True)
    artifacts = home / 'package-artifacts'
    artifacts.mkdir()
    archive = artifacts / 'S540IdleCompleteImageABI.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_symlink():
                raise ValueError('Package symlinks are not admitted')
            if path.is_file():
                bundle.write(path, 'S540IdleCompleteImageABI/' + str(path.relative_to(output)))
    attestation = output / 'packaging-attestation.json'
    digests = {'archive': archive.name,
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'packaging_attestation_sha256': hashlib.sha256(attestation.read_bytes()).hexdigest(),
        'strict_native_report_sha256': digest, 'expected_native_link_inputs': 1163,
        'native_compilation_reused': True,
        'cached_compilation_workflow_run_id': record['compilation_cache']['workflow_run_id'],
        'test_scope': 'idle complete-image target-loader ABI only',
        'original_entry_admission': False, 'gpu_initialization_attempted': False}
    (artifacts / 'package-digests.json').write_text(json.dumps(digests, indent=2, sort_keys=True) + '\n')
    print(json.dumps(digests, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
