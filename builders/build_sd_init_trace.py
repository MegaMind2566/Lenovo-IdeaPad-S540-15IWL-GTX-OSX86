#!/usr/bin/env python3
"""Compile and package the SD userspace diagnostic; never installs or tests target SD."""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'S540-SD-Init-Trace-v1'
SOURCE_FILES = [
    'packages/sd-init-trace/src/sd_init_trace.m',
    'packages/sd-init-trace/ESEGUI-TEST-SD.command',
    'packages/sd-init-trace/LEGGIMI.txt',
    'packages/sd-init-trace/README.md',
    'packages/sd-init-trace/LICENSE',
    'builders/build_sd_init_trace.py',
    '.github/workflows/build-sd-init-trace.yml',
]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(args, **kw):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=90, **kw)

def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

def native_probe(executable, out):
    """Short owned synthetic trace, separate from SD and from the userspace unit tests."""
    result = {'status': 'UNAVAILABLE', 'sd_hardware_test': False}
    trace = Path('/usr/bin/ktrace')
    if not trace.exists():
        result['reason'] = 'ktrace absent'
        return result
    try:
        state = run(['/usr/sbin/sysctl', '-n', 'ktrace.state']).stdout.strip()
        if state == '1':
            result['reason'] = 'foreground trace already active'
            return result
        stream = out / 'ktrace-native.ndjson'
        errors = out / 'ktrace-native.stderr.txt'
        with stream.open('wb') as stdout, errors.open('wb') as stderr:
            proc = subprocess.Popen(['sudo', '-n', str(trace), 'trace', '-f', 'S0xfeff', '-b', '4', '-T', '4', '--ndjson', '--no-default-codes-files'], stdout=stdout, stderr=stderr)
            try:
                time.sleep(1)
                emit = subprocess.run(['sudo', '-n', str(executable), '--emit-probe'], capture_output=True, text=True, timeout=5)
                result['emit_exit'] = emit.returncode
                proc.wait(timeout=8)
                result['trace_exit'] = proc.returncode
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
        if stream.stat().st_size > 8 * 1024 * 1024:
            stream.unlink()
            result['reason'] = 'synthetic stream unexpectedly large; removed'
            return result
        # These bytes belong only to the ephemeral CI diagnostic. No Lenovo report is read here.
        schemas = []
        objects = []
        non_json_lines = 0
        missing_debugid_records = 0
        for line in stream.read_text(errors='replace').splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                if line.strip():
                    non_json_lines += 1
                continue
            if isinstance(obj, dict):
                if "debugid" not in obj:
                    missing_debugid_records += 1
                schemas.append(sorted(obj))
                objects.append(obj)
        result['schemas'] = schemas[:3]
        result['object_count'] = len(objects)
        result['non_json_lines'] = non_json_lines
        result['missing_debugid_records'] = missing_debugid_records
        result['stderr'] = errors.read_text(errors='replace')[:2000]
        def integer(value):
            if isinstance(value, bool):
                raise ValueError('boolean is not an argument')
            return int(value, 0) if isinstance(value, str) else int(value)
        probes = []
        for obj in objects:
            try:
                if integer(obj.get('debugid')) == 0xfeff0010:
                    values = obj.get('args')
                    if not isinstance(values, list):
                        names = ['arg1', 'arg2', 'arg3', 'arg4'] if 'arg1' in obj else ['argument_1', 'argument_2', 'argument_3', 'argument_4']
                        values = [obj[name] for name in names]
                    if [integer(v) for v in values] == [1, 2, 3, 4]:
                        probes.append(obj)
            except (TypeError, ValueError, KeyError):
                pass
        result['synthetic_probe_count'] = len(probes)
        # Discard every unrelated CI event rather than shipping its metadata.
        stream.write_text(''.join(json.dumps(obj) + '\n' for obj in probes))
        result['status'] = 'CAPTURED' if result.get('trace_exit') == 0 and result.get('emit_exit') == 0 and probes else 'UNAVAILABLE'
        if result['status'] == 'CAPTURED':
            translated = dict(probes[0])
            translated['debugid'] = 0x06134080
            if isinstance(translated.get('args'), list):
                translated['args'] = [0, 0, 0, 0]
            else:
                names = ['arg1', 'arg2', 'arg3', 'arg4'] if 'arg1' in translated else ['argument_1', 'argument_2', 'argument_3', 'argument_4']
                for name in names:
                    translated[name] = 0
            fixture = out / 'native-format-translated-fixture.ndjson'
            fixture.write_text(json.dumps(translated) + '\n')
            try:
                decoded = json.loads(run([str(executable), '--decode-fixture', str(fixture)]).stdout)
            except (subprocess.SubprocessError, ValueError) as exc:
                raise RuntimeError('native-format parser execution failed') from exc
            result['native_format_parser'] = 'PASS' if decoded.get('result') == 'TRACE_CAPTURED' and len(decoded.get('events', [])) == 1 and decoded['events'][0]['fields'] == {'present': False} else 'FAIL'
            assert result['native_format_parser'] == 'PASS', 'native NDJSON format is not accepted by the delivered parser'
        else:
            result['native_format_parser'] = 'NOT_VALIDATED'
    except (OSError, subprocess.SubprocessError) as exc:
        result['reason'] = type(exc).__name__ + ': ' + str(exc)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert platform.system() == 'Darwin' and platform.machine() == 'x86_64', 'standard Intel macOS runner required'
    assert os.environ.get('GITHUB_REPOSITORY_VISIBILITY') == 'public', 'public runner path only'
    request = json.loads(args.request.read_text())
    assert request['schema'] == 1 and request['purpose'] == 'sd-init-trace-userspace'
    parent = run(['git', 'rev-parse', 'HEAD^'], cwd=ROOT).stdout.strip()
    assert request['source_parent'] == parent, 'request must be a separate commit after the exact reviewed source'
    assert set(request['source_sha256']) == set(SOURCE_FILES), 'exact source list required'
    changed = run(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'], cwd=ROOT).stdout.splitlines()
    assert changed == ['.github/native-ci/sd-init-trace-request.json'], 'request commit changes only its own marker'
    for name in SOURCE_FILES:
        parent_blob = subprocess.run(['git', 'show', parent + ':' + name], cwd=ROOT, capture_output=True, check=True, timeout=10).stdout
        assert hashlib.sha256(parent_blob).hexdigest() == request['source_sha256'][name], 'reviewed parent mismatch: ' + name
        assert sha(ROOT / name) == request['source_sha256'][name], 'source mismatch: ' + name
    dump(out / 'request-verified.json', request)
    stage = out / PREFIX
    (stage / 'bin').mkdir(parents=True, exist_ok=True)
    (stage / 'src').mkdir(exist_ok=True)
    (stage / 'validation').mkdir(exist_ok=True)
    for name in ['ESEGUI-TEST-SD.command', 'LEGGIMI.txt', 'README.md', 'LICENSE']:
        shutil.copyfile(ROOT / 'packages/sd-init-trace' / name, stage / name)
    shutil.copyfile(ROOT / SOURCE_FILES[0], stage / 'src/sd_init_trace.m')
    executable = stage / 'bin/sd-init-trace'
    cmd = ['xcrun', 'clang', '-arch', 'x86_64', '-mmacosx-version-min=12.0', '-fobjc-arc', '-O2', '-Wall', '-Wextra', '-Werror', '-framework', 'Foundation', '-framework', 'IOKit', str(ROOT / SOURCE_FILES[0]), '-o', str(executable)]
    (out / 'compile-command.json').write_text(json.dumps(cmd, indent=2) + '\n')
    try:
        compiled = run(cmd)
        (out / 'compile.stdout.txt').write_text(compiled.stdout)
        (out / 'compile.stderr.txt').write_text(compiled.stderr)
    except subprocess.CalledProcessError as exc:
        (out / 'compile.stdout.txt').write_text(exc.stdout or '')
        (out / 'compile.stderr.txt').write_text(exc.stderr or '')
        raise
    run(['codesign', '--force', '--sign', '-', '--identifier', 'org.s540.SDInitTrace', str(executable)])
    run(['codesign', '--verify', '--strict', str(executable)])
    checks = run([str(executable), '--self-test'])
    (out / 'self-test.stdout.txt').write_text(checks.stdout)
    (out / 'self-test.stderr.txt').write_text(checks.stderr)
    run(['/bin/bash', '-n', str(stage / 'ESEGUI-TEST-SD.command')])
    probe = native_probe(executable, out)
    dump(out / 'native-probe.json', probe)
    native = {
        'schema': 1,
        'source_commit': request['source_parent'],
        'request_commit': run(['git', 'rev-parse', 'HEAD'], cwd=ROOT).stdout.strip(),
        'source_sha256': request['source_sha256'],
        'compiler': run(['xcrun', 'clang', '--version']).stdout,
        'sdk': run(['xcrun', '--sdk', 'macosx', '--show-sdk-version']).stdout.strip(),
        'executable_sha256': sha(executable),
        'native_self_tests': 'PASS',
        'synthetic_trace': probe,
        'target_sd_test': 'NOT_RUN',
        'efi_modified': False,
        'nvidia_modified': False,
    }
    dump(stage / 'validation/native.json', native)
    (stage / 'validation/self-test.stdout.txt').write_text(checks.stdout)
    dump(stage / 'MANIFEST.json', {
        'schema': 1, 'name': PREFIX, 'kind': 'userspace-diagnostic',
        'source_commit': request['source_parent'],
        'driver_executable_sha256': 'dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7',
        'driver_uuid': 'D2EAAA60-AF10-360F-B645-1592B9B3A804',
        'target_sd_success': False,
    })
    for file in stage.rglob('*'):
        if file.is_file():
            file.chmod(0o755 if file.name in ['sd-init-trace', 'ESEGUI-TEST-SD.command'] else 0o644)
    files = sorted(p for p in stage.rglob('*') if p.is_file())
    (stage / 'SHA256SUMS').write_text(''.join(sha(p) + '  ' + p.relative_to(stage).as_posix() + '\n' for p in files))
    archive = out / (PREFIX + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(out))
    (out / (archive.name + '.sha256')).write_text(sha(archive) + '  ' + archive.name + '\n')
    print(json.dumps({'archive': str(archive), 'sha256': sha(archive), 'native_self_tests': 'PASS', 'synthetic_trace': probe['status'], 'target_sd_test': 'NOT_RUN'}))

if __name__ == '__main__':
    main()
