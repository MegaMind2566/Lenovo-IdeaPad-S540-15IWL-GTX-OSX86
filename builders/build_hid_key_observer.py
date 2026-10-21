#!/usr/bin/env python3
"""Build the passive HID probe on an Intel Mac; never opens HID during CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import zipfile


def run(args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise SystemExit('The release build requires a native Intel macOS runner.')
    source = args.source_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    required = ['src/hid_key_probe.m', 'COLLECT-HID-KEYS.command', 'README.txt']
    for relative in required:
        if not (source / relative).is_file():
            raise SystemExit('Missing source: ' + relative)
    request_path = Path(__file__).resolve().parents[1] / '.github/native-ci/hid-key-observer-request.json'
    request = json.loads(request_path.read_text())
    for relative in required:
        digest = hashlib.sha256((source / relative).read_bytes()).hexdigest()
        if request.get('source_sha256', {}).get(relative) != digest:
            raise SystemExit('Explicit build request does not match source: ' + relative)
    with tempfile.TemporaryDirectory(prefix='s540-hid-build-') as tmp:
        package = Path(tmp) / 'S540-HID-Keys-v2'
        (package / 'bin').mkdir(parents=True)
        for relative in required:
            destination = package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, destination)
        binary = package / 'bin/hid-key-probe'
        run(['xcrun', 'clang', '-arch', 'x86_64', '-mmacosx-version-min=10.15',
             '-fobjc-arc', '-Wall', '-Wextra', '-Werror', '-O2',
             '-framework', 'Foundation', '-framework', 'IOKit',
             '-framework', 'CoreFoundation', str(source / 'src/hid_key_probe.m'),
             '-o', str(binary)])
        binary.chmod(0o755)
        (package / 'COLLECT-HID-KEYS.command').chmod(0o755)
        if run(['lipo', '-archs', str(binary)]) != 'x86_64':
            raise SystemExit('Unexpected executable architecture.')
        run(['codesign', '--force', '--sign', '-', '--timestamp=none',
             '--identifier', 'it.megamind.s540.hid-key-probe.v1', str(binary)])
        run(['codesign', '--verify', '--strict', str(binary)])
        self_test = run([str(binary), '--self-test'])
        self_test_data = json.loads(self_test)
        if (self_test_data.get('result') != 'SELF_TEST_PASSED'
                or len(self_test_data.get('checks', [])) < 23
                or not all(item.get('passed') is True for item in self_test_data['checks'])):
            raise SystemExit('Offline self-tests did not pass.')
        if not any(item.get('name') == 'pty-function-escape-does-not-contaminate-next-prompt'
                   and item.get('passed') is True for item in self_test_data['checks']):
            raise SystemExit('The real terminal escape/input regression did not pass.')
        cli_checks = []
        for arguments in [[], ['--unknown'], ['--output', 'relative-report.json']]:
            result = subprocess.run([str(binary), *arguments], text=True, capture_output=True)
            if result.returncode != 64:
                raise SystemExit('Argument validation unexpectedly reached the HID path.')
            cli_checks.append({'arguments': arguments, 'exit_code': result.returncode})
        print(json.dumps({'self_test_checks': len(self_test_data['checks']),
                          'cli_argument_checks': len(cli_checks), 'result': 'passed'}))
        run(['/bin/bash', '-n', str(package / 'COLLECT-HID-KEYS.command')])
        source_hashes = {relative: hashlib.sha256((source / relative).read_bytes()).hexdigest()
                         for relative in required}
        provenance = {'format': 1, 'architecture': 'x86_64',
                      'git_commit': os.environ.get('GITHUB_SHA', ''),
                      'source_sha256': source_hashes,
                      'self_tests': self_test_data,
                      'cli_argument_checks': cli_checks,
                      'runtime_hid_test': 'not_run_in_ci'}
        (package / 'BUILD.json').write_text(json.dumps(provenance, indent=2) + '\n')
        files = sorted(p for p in package.rglob('*') if p.is_file())
        (package / 'SHA256SUMS').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(package).as_posix() + '\n'
            for p in files))
        archive = output / 'S540-HID-Keys-v2.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(package.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(package.parent).as_posix())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (output / (archive.name + '.sha256')).write_text(digest + '  ' + archive.name + '\n')
        print(json.dumps({'artifact': archive.name, 'sha256': digest,
                          'bytes': archive.stat().st_size}))


if __name__ == '__main__':
    main()
