#!/usr/bin/env python3
"""Source controls; never manufacture a native image pass or emit a bundle."""
from __future__ import annotations
import argparse
import copy
import errno
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import macho_signing
import package as candidate

HERE = Path(__file__).resolve().parent


def fixture(signed=False):
    """Synthetic bytes exercise comparison only; they are not a signature."""
    def segment(name, address, virtual, offset, length, sections=b''):
        return struct.pack('<II16s4Q4I', 0x19, 72 + len(sections), name, address,
                           virtual, offset, length, 7, 5, len(sections) // 80, 0) + sections
    section = struct.pack('<16s16sQQ8I', b'__text', b'__TEXT', 0x2000, 16, 4096,
                          4, 0, 0, 0x80000400, 0, 0, 0)
    commands = [segment(b'__TEXT', 0x1000, 8192, 0, 8192, section),
        segment(b'__LINKEDIT', 0x4000, 4096, 8192, 64 + (32 if signed else 0)),
        struct.pack('<II16s', 0x1b, 24, b'\x01' * 16),
        struct.pack('<6I', 2, 24, 8192, 1, 8208, 16)]
    if signed:
        commands.append(struct.pack('<4I', 0x1d, 16, 8256, 32))
    table = b''.join(commands)
    data = bytearray(8288 if signed else 8256)
    data[:32] = struct.pack('<8I', 0xfeedfacf, 0x01000007, 3, 11, len(commands), len(table), 0, 0)
    data[32:32 + len(table)] = table
    data[4096:4112] = b'\x90' * 15 + b'\xc3'
    data[8192:8208] = struct.pack('<IBBHQ', 1, 15, 1, 0, 0x2000)
    data[8208:8224] = b'\0__start\0'.ljust(16, b'\0')
    if signed:
        data[8256:8288] = b'FAKE-SIGNATURE-CONTROL-ONLY'.ljust(32, b'\0')
    return bytes(data)


def report_fixture():
    return {'format': 1, 'status': 'linked-native-development-image', 'phase': 'done',
        'host_system': 'Darwin', 'host_control': False, 'native_darwin_compilation': True,
        'actual_link_performed': True, 'relocatable_link_performed': True,
        'final_link_attempted': True, 'original_compilation_performed': True,
        'project_compilation_performed': True, 'native_compilation_reports_verified': True,
        'module_loaded': False, 'installable_bundle_created': False,
        'target_kernel_admission_proven': False, 'kernel_execution': 'not_tested',
        'gpu_access': False, 'hardware_admission': False, 'original_entry_admission': False,
        'production_candidate_allowed': False,
        'final_image': {'filetype': 'MH_KEXT_BUNDLE', 'installable_bundle': False,
                        'sha256': 'a' * 64, 'imports': ['thread_call_cancel']},
        'final_public_kpi_export_audit': candidate.public_kpi.audit_imports(
            ['thread_call_cancel'], candidate.LIBRARIES),
        'final_link_policy': {'dead_strip': True,
            'undefined_policy': 'Apple x86_64 kext dynamic_lookup',
            'undefined_closure_enforcement': 'independent exact final Mach-O private/public symbol audit',
            'exported_symbols': ['_kmod_info'], 'unresolved_private_imports_permitted': False},
        'final_exported_symbols': ['kmod_info'], 'scatterable_input_objects': 1163,
        'relocatable_image': {'subsections_via_symbols': True},
        'source_plan': {'complete_original_translation_units': 1100, 'total_expected_link_objects': 1163,
            'complete_metaclass_classes': ['S540NvidiaGspPowerService',
                'S540ProspectiveLoaderControl', 'S540ProspectiveLoaderClient']},
        'commands': [{'name': name, 'status': 0} for name in
                     ('complete-relocatable-link', 'raw-development-kext-link')]}


def payload_ownership_controls(output):
    """Exercise actual launcher ownership commands; never load a kernel image."""
    source = (HERE / 'scripts/test-idle-loader.sh').read_text()
    repair = [line for line in source.splitlines() if line.startswith('/usr/sbin/chown ')]
    guards = [line for line in source.splitlines() if 'Temporary payload ownership is not ' in line]
    if len(repair) != 1 or len(guards) != 1:
        raise ValueError('Expected one actual payload ownership repair and guard')
    if '\\( ! -uid 0 -o ! -gid 0 \\)' not in guards[0]:
        raise ValueError('Payload ownership guard must reject either a nonzero UID or GID')
    if not source.index('PKG=$SESSION/payload') < source.index('verify_package') < source.index(repair[0]) < source.index(guards[0]):
        raise ValueError('Verify the copied package before ownership repair, then check both IDs')
    shell = 'fail() { exit 29; }; PKG=$1\n'
    fixture = output / 'payload-ownership'; fixture.mkdir()
    nested = fixture / 'nested'; nested.mkdir()
    payload = nested / 'unchanged.bin'; payload.write_bytes(b'ownership-control-only\n')
    original_bytes = payload.read_bytes()
    checks = []
    def guard(expected):
        result = subprocess.run(['/bin/sh', '-c', shell + guards[0], 'ownership-control', str(fixture)],
                                capture_output=True, text=True)
        if result.returncode != (0 if expected else 29):
            raise ValueError('Actual payload ownership guard gave an unexpected result: ' + result.stderr)
    repair_command = repair[0]
    if sys.platform != 'darwin':
        host_chown = shutil.which('chown')
        if host_chown is None or ' ' in host_chown:
            raise ValueError('A plain host chown path is required for ownership controls')
        repair_command = repair_command.replace('/usr/sbin/chown', host_chown, 1)
    def repair_fixture():
        result = subprocess.run(['/bin/sh', '-c', shell + repair_command,
            'ownership-repair-control', str(fixture)], capture_output=True, text=True)
        if result.returncode or any((p.stat().st_uid, p.stat().st_gid) != (0, 0)
                                   for p in (fixture, nested, payload)):
            raise ValueError('Actual payload ownership repair failed: ' + result.stderr)
    privileged = os.geteuid() == 0
    unavailable = None if privileged else 'The source-control process is not root'
    if privileged:
        try:
            for path in (fixture, nested, payload):
                os.chown(path, 0, 20)
        except OSError as error:
            if error.errno not in (errno.EPERM, errno.EACCES, errno.EINVAL):
                raise
            privileged = False
            unavailable = 'The host cannot create the actual UID/GID fixture: errno ' + str(error.errno)
            repair_fixture()
    if privileged:
        old = subprocess.run(['/bin/sh', '-c', shell +
            '[ -z "$(/usr/bin/find "$PKG" ! -user root -print)" ]',
            'historical-user-only-control', str(fixture)], capture_output=True, text=True)
        if old.returncode != 0:
            raise ValueError('The root:staff fixture must reproduce the historical user-only admission')
        checks.append('reproduce-root-staff-user-only-admission')
        guard(False); checks.append('reject-root-staff-payload')
        # Only the chown executable path is mapped for Linux source controls;
        # the exact launcher arguments and ownership guard execute unchanged.
        repair_fixture(); guard(True); checks.append('repair-root-wheel-payload')
        os.chown(payload, 0, 20)
        guard(False); checks.append('reject-nested-wrong-group')
        repair_fixture()
        os.chown(payload, 1, 0)
        guard(False); checks.append('reject-nested-wrong-user')
        repair_fixture(); guard(True)
    elif os.geteuid() == 0:
        repair_fixture(); guard(True)
        checks.append('accept-actual-root-wheel-payload')
    else:
        guard(False); checks.append('reject-user-owned-payload')
    if payload.read_bytes() != original_bytes:
        raise ValueError('Ownership controls changed payload bytes')
    checks.append('ownership-repair-preserves-payload-bytes')
    return {'checks': checks, 'privileged_cases_executed': privileged,
            'privileged_cases_unavailable': not privileged,
            'unavailable_reason': unavailable,
            'actual_launcher_commands_exercised': True, 'kernel_load_attempted': False}


def run(args):
    output = args.output.resolve()
    candidate.require(not output.exists(), 'Source control output must be fresh')
    output.mkdir(parents=True)
    frozen = {str(path): candidate.sha(path) for path in sorted(HERE.rglob('*'))
              if path.is_file() and path.suffix in ('.py', '.c', '.sh', '.md')}
    loader = candidate.link.LOADER
    contract_path = loader / 'LOADER-PROTOTYPE-CONTRACTS.json'
    candidate.require(candidate.sha(contract_path) == candidate.link.LOADER_CONTRACT_SHA,
                      'Closed loader contract changed')
    frozen[str(contract_path)] = candidate.sha(contract_path)
    contract = json.loads(contract_path.read_text())
    for name in ('S540ProspectiveLoaderState.c', 'S540ProspectiveLoaderState.h',
                 'S540ProspectiveLoaderProtocol.h'):
        candidate.require(candidate.sha(loader / name) == contract['source_sha256'][name],
                          'Actual loader decoder source changed')
        frozen[str(loader / name)] = candidate.sha(loader / name)
    notice = candidate.notice_mapping()
    candidate.require(notice['filename'] == 'NVIDIA-DRIVER-LICENSE.txt' and notice['filename'] != 'LICENSE',
                      'Acquired notice must use its actual independent mapping')
    notice_verified = archive_alias_refused = False
    if args.assets_dir:
        candidate.verified_notice(args.assets_dir)
        notice_verified = True
        with tempfile.TemporaryDirectory(prefix='wrong-notice-control-', dir=args.assets_dir.resolve().parent) as temp:
            wrong = Path(temp)
            for source in args.assets_dir.resolve().iterdir():
                os.link(source, wrong / ('LICENSE' if source.name == notice['filename'] else source.name))
            try:
                candidate.verified_notice(wrong)
            except candidate.firmware.ACQUIRE.AssetError:
                archive_alias_refused = True
            candidate.require(archive_alias_refused, 'Archive LICENSE alias was silently accepted')
    checks, commands = [], []
    before, after = output / 'synthetic-presign.bin', output / 'synthetic-signed.bin'
    before.write_bytes(fixture()); after.write_bytes(fixture(True))
    macho_signing.compare(before, after); checks.append('synthetic-signature-metadata-only')
    def rejected(data, name):
        after.write_bytes(data)
        try:
            macho_signing.compare(before, after)
        except ValueError:
            checks.append(name); return
        raise ValueError('Signing mutation was accepted: ' + name)
    for name, offset in (('code', 4096), ('symbol', 8192), ('string', 8209),
        ('header-padding', 1024), ('section-address', 32 + 72 + 32),
        ('section-flags', 32 + 72 + 64), ('uuid', 32 + 152 + 72 + 8),
        ('linkedit-address', 32 + 152 + 24), ('existing-command', 32 + 152 + 72 + 24 + 8)):
        changed = bytearray(fixture(True)); changed[offset] ^= 1
        rejected(changed, 'reject-signing-' + name)
    rejected(fixture(), 'reject-missing-signature')
    rejected(fixture(True) + b'UNREVIEWED', 'reject-trailing-overlay')
    report = report_fixture()
    candidate.validate_report_contract(report); checks.append('schema-only-success-fixture')
    modules = (candidate.link, candidate.compose, candidate.combined, candidate.firmware,
               candidate.link.execution, candidate.link.transport, candidate.link.original,
               candidate.link.metaclass, candidate.public_kpi, candidate.link.selective_cache)
    bindings = {str(Path(module.__file__).resolve()): candidate.sha(module.__file__) for module in modules}
    candidate.verifier_bindings(bindings); checks.append('exact-executing-verifier-bindings')
    def refuse_binding(value, name):
        try:
            candidate.verifier_bindings(value)
        except ValueError:
            checks.append(name); return
        raise ValueError('Unbound verifier was accepted: ' + name)
    bad = dict(bindings); key = next(iter(bad)); bad['/old/tree/' + Path(key).name] = bad.pop(key)
    refuse_binding(bad, 'reject-same-basename-verifier-other-tree')
    bad = dict(bindings); bad[key] = '0' * 64
    refuse_binding(bad, 'reject-changed-executing-verifier')
    def refuse_report(value, name):
        try:
            candidate.validate_report_contract(value)
        except (ValueError, KeyError, TypeError):
            checks.append(name); return
        raise ValueError('Non-native report was accepted: ' + name)
    bad = copy.deepcopy(report)
    bad['final_image']['imports'] = ['thread_call_cancel_wait']
    refuse_report(bad, 'reject-header-declared-private-live-import')
    bad = copy.deepcopy(report)
    bad.pop('final_public_kpi_export_audit')
    refuse_report(bad, 'reject-missing-final-public-export-proof')
    bad = copy.deepcopy(report)
    bad['final_public_kpi_export_audit']['exact_target_export_proof'] = True
    refuse_report(bad, 'reject-source-snapshot-as-exact-target-proof')
    for key, value in (('host_control', True), ('native_darwin_compilation', False),
        ('actual_link_performed', False), ('status', 'validated-source-plan-only'),
        ('original_compilation_performed', False), ('project_compilation_performed', False),
        ('module_loaded', True), ('hardware_admission', True), ('original_entry_admission', True),
        ('native_compilation_reports_verified', False), ('format', True)):
        bad = copy.deepcopy(report); bad[key] = value
        refuse_report(bad, 'reject-report-' + key)
    for key, value in (('undefined_policy', 'error'), ('exported_symbols', ['_kmod_info', '_unreviewed']),
        ('undefined_closure_enforcement', 'linker exit status only'), ('unresolved_private_imports_permitted', True)):
        bad = copy.deepcopy(report); bad['final_link_policy'][key] = value
        refuse_report(bad, 'reject-final-policy-' + key)
    for key, value in (('final_exported_symbols', ['kmod_info', 'unreviewed']),
        ('scatterable_input_objects', 1162), ('relocatable_image', {'subsections_via_symbols': False})):
        bad = copy.deepcopy(report); bad[key] = value
        refuse_report(bad, 'reject-final-boundaries-' + key)
    resumed = copy.deepcopy(report)
    resumed.update(native_compilation_reused=True, original_compilation_performed=False,
        project_compilation_performed=False, compilation_cache={'complete_native_compilation_verified': True})
    candidate.validate_report_contract(resumed); checks.append('schema-only-continuation-fixture')
    for key, value in (('native_compilation_reused', 1), ('original_compilation_performed', True),
        ('project_compilation_performed', True), ('compilation_cache', {})):
        bad = copy.deepcopy(resumed); bad[key] = value
        refuse_report(bad, 'reject-continuation-provenance-' + key)
    bad = copy.deepcopy(report); bad['commands'][1]['status'] = 1
    refuse_report(bad, 'reject-failed-final-command')
    for path in args.negative_report:
        refuse_report(json.loads(path.read_text()), 'reject-actual-report-' + path.name)
    scripts = sorted((HERE / 'scripts').glob('*.sh'))
    candidate.require(len(scripts) == 4, 'All four actual package scripts are required')
    for script in scripts:
        result = subprocess.run(['/bin/sh', '-n', str(script)], capture_output=True, text=True)
        candidate.require(result.returncode == 0, result.stderr)
        checks.append('shell-syntax-' + script.name)
    ownership = payload_ownership_controls(output)
    checks.extend(ownership['checks'])
    expected = 'ABCDEF11-1122-3344-5566-778899AABBCC'
    other = '22222222-2222-2222-2222-222222222222'
    identifier = candidate.BUNDLE_ID
    cases = [
        ('exact', identifier + ' (0.0.1) <' + expected + '>\n', True, True),
        ('mismatch', identifier + ' (0.0.1) <' + other + '>\n', True, False),
        ('suffix', 'unrelated.' + identifier + ' (0.0.1) <' + expected + '>\n', False, False),
        ('collision', identifier + ' <' + other + '>\nunrelated.' + identifier + ' <' + expected + '>\n', True, False),
        ('duplicate', identifier + ' <' + expected + '>\n' + identifier + ' <' + other + '>\n', True, False),
        ('uuid-substring', identifier + ' <PREFIX' + expected + '>\n', True, False),
        ('case-insensitive', identifier + ' <' + expected.lower() + '>\n', True, True)]
    shell = '. "$1"; BUNDLE_ID="$2"; EXPECTED_UUID="$3"; "$4" "$5"'
    for name, content, present, match in cases:
        path = output / ('loaded-' + name + '.txt'); path.write_text(content)
        for function, accepted in (('has_identifier', present), ('has_expected_uuid', match)):
            result = subprocess.run(['/bin/sh', '-c', shell, 'identity-control',
                str(HERE / 'scripts/common.sh'), identifier, expected, function, str(path)],
                capture_output=True, text=True)
            candidate.require((result.returncode == 0) == accepted,
                              'Actual loaded identifier/UUID parser failed: ' + name + '/' + function)
            checks.append('loaded-' + name + '-' + function)
    decoded = {}
    for name, sanitizer in (('plain', []), ('sanitized', ['-fsanitize=address,undefined,function',
            '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])):
        binary = output / ('actual-idle-decoder-' + name)
        command = [str(args.cc), '-O1', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-DS540_IDLE_CTL_DECODE_CONTROL', '-I', str(loader), *sanitizer,
            str(HERE / 'idle_ctl.c'), str(loader / 'S540ProspectiveLoaderState.c'), '-o', str(binary)]
        result = subprocess.run(command, capture_output=True, text=True)
        (output / ('compile-' + name + '.log')).write_text(result.stdout + result.stderr)
        commands.append({'name': 'compile-' + name, 'command': command, 'status': result.returncode})
        candidate.require(result.returncode == 0, result.stderr)
        if sys.platform == 'darwin':
            for label, cmd in [('sign', ['/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', str(binary)]),
                               ('verify', ['/usr/bin/codesign', '--verify', '--strict', str(binary)])]:
                result = subprocess.run(cmd, capture_output=True, text=True)
                commands.append({'name': label + '-' + name, 'command': cmd, 'status': result.returncode})
                candidate.require(result.returncode == 0, result.stderr)
        env = dict(os.environ)
        if sys.platform != 'darwin':
            env['ASAN_OPTIONS'] = 'detect_leaks=0'
        result = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
        (output / ('run-' + name + '.log')).write_text(result.stdout + result.stderr)
        commands.append({'name': 'run-' + name, 'command': [str(binary)], 'status': result.returncode})
        candidate.require(result.returncode == 0, result.stderr)
        value = json.loads(result.stdout)
        candidate.require(value['status'] == 'passed' and value['actual_loader_state'] is True,
                          'Actual frozen loader state failed decoder controls')
        decoded[name] = value
        checks.append('actual-loader-state-' + name)
    if sys.platform != 'darwin':
        forbidden = output / 'must-not-be-a-package'
        try:
            candidate.package(argparse.Namespace(cc=args.cc, cxx=args.cc, output=forbidden,
                report=output / 'absent-report.json', report_sha256='a' * 64,
                kernel_sdk=output, assets_dir=output))
        except ValueError:
            candidate.require(not forbidden.exists(), 'Non-native packaging emitted an output')
            checks.append('reject-non-native-package-before-output')
        else:
            raise ValueError('Non-native packaging was accepted')
    candidate.require(all(candidate.sha(Path(name)) == expected for name, expected in frozen.items()),
                      'A checked source changed during controls')
    result = {'format': 1, 'status': 'passed', 'checks': checks, 'check_count': len(checks),
        'firmware_notice_mapping': notice, 'actual_acquired_notice_verified': notice_verified,
        'archive_license_name_refused_without_fallback': archive_alias_refused,
        'actual_loader_state_decoder': decoded, 'commands': commands, 'source_sha256': frozen,
        'temporary_payload_ownership_controls': ownership,
        'executing_verifier_source_sha256': candidate.verifier_bindings(bindings),
        'synthetic_image_scope': 'signature invariance comparison only; not a native image or signature validation',
        'schema_fixture_scope': 'JSON contract only; no independently verified image result',
        'bundle_emitted': False, 'native_build_pass_observed': False, 'native_macos_packaging_tested': False,
        'signature_verification_tested': False, 'target_loader_abi_observed': False, **candidate.CLOSED}
    candidate.write_json(output / 'control-results.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative-report', type=Path, action='append', default=[])
    parser.add_argument('--assets-dir', type=Path)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'source_checks': result['check_count'],
                      'actual_loader_state_decoder': result['actual_loader_state_decoder'], 'bundle_emitted': False}))


if __name__ == '__main__':
    main()
