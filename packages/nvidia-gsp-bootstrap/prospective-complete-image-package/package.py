#!/usr/bin/env python3
"""Package only an independently pinned, verified native closed idle image."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import macho_signing

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import link_nvidia_first_transaction as link
import compose_nvidia_first_transaction as compose
import nvidia_combined_metaclasses as combined
import embed_nvidia_firmware as firmware

BUNDLE_ID = 'org.osx86.S540ProspectiveLoader'
BUNDLE = 'S540IdleCompleteImage.kext'
EXECUTABLE = 'S540IdleCompleteImage'
LIBRARIES = {**{'com.apple.kpi.' + key: '8.0.0' for key in
              ('bsd', 'iokit', 'libkern', 'mach', 'unsupported')},
             'com.apple.iokit.IOPCIFamily': '2.9.0'}
TARGET = {'label': 'Lenovo IdeaPad S540-15IWL GTX idle complete-image ABI check',
          'architecture': 'x86_64', 'product_version': '26.7.1', 'build': '25G241',
          'darwin_release': '25.6.0', 'gpu_registry_identity': {
              'vendor': 0x10de, 'device': 0x1f91, 'subvendor': 0x17aa,
              'subdevice': 0x3806, 'revision': 0xa1, 'class': 0x030000}}
CLOSED = {key: False for key in ('hardware_admission', 'original_entry_admission',
          'production_candidate_allowed', 'rm_initialization_test', 'gsp_initialization_test',
          'acceleration_test', 'kernel_trust_approval')}
PINNED_HELPERS = {
 'packages/nvidia-gsp-bootstrap/prospective-loader/check_loader.py':
 '93d3059c64edc795855686aa65952c4cc095c23f700c0c350d81b565e28167b2',
 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original/common.py':
 '4f1696dc182fc12058aacc4ee97c0e70de2cbb9c746562a92b5ce90b323644a4'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def require(value, message):
    if not value:
        raise ValueError(message)


def file_in(root, name):
    path = root / compose.checked_relative(name)
    require(path.is_file() and not path.is_symlink(), 'Expected ordinary native build file: ' + str(path))
    require(path.resolve().is_relative_to(root.resolve()), 'Native build file escapes its tree')
    return path


def verifier_bindings(recorded):
    modules = (link, compose, combined, firmware, link.execution, link.transport,
               link.original, link.metaclass)
    actual = {}
    for module in modules:
        path = Path(module.__file__)
        require(not path.is_symlink() and path.resolve().parent == ROOT / 'builders',
                'Executing verifier is outside the canonical builder directory')
        actual[str(path.resolve())] = sha(path)
    require(recorded == actual, 'Strict report does not bind these exact executing verifier files')
    result = dict(actual)
    for relative, expected in PINNED_HELPERS.items():
        path = ROOT / relative
        require(not path.is_symlink() and sha(path) == expected,
                'An independently reviewed helper changed: ' + relative)
        result[str(path)] = expected
    return result


def notice_mapping():
    manifest = firmware.ACQUIRE.MANIFEST
    name = manifest['redistribution']['notice_path']
    require(len(compose.checked_relative(name).parts) == 1, 'Notice mapping escapes acquired asset directory')
    rows = [row for row in manifest['assets'] if row['archive_path'] == 'LICENSE']
    require(len(rows) == 1 and firmware.ACQUIRE.ASSET_NAMES[rows[0]['archive_path']] == name and
            rows[0]['sha256'] == manifest['redistribution']['notice_sha256'],
            'Acquired notice mapping differs from the independent redistribution manifest')
    return {'filename': name, 'size': rows[0]['size'], 'sha256': rows[0]['sha256']}


def verified_notice(assets):
    mapping = notice_mapping()
    directory = assets.resolve(strict=True)
    observed = firmware.ACQUIRE.verify_assets(directory)
    require([row for row in observed if row['filename'] == mapping['filename']] == [mapping],
            'Verified assets lack the exact acquired notice identity')
    path = directory / mapping['filename']
    require(not path.is_symlink() and path.stat().st_size == mapping['size'] and
            sha(path) == mapping['sha256'], 'Acquired notice differs from its pinned bytes')
    return path, mapping


def validate_report_contract(report):
    expected = {'format': 1, 'status': 'linked-native-development-image', 'phase': 'done',
        'host_system': 'Darwin', 'host_control': False, 'native_darwin_compilation': True,
        'actual_link_performed': True, 'relocatable_link_performed': True,
        'final_link_attempted': True, 'original_compilation_performed': True,
        'project_compilation_performed': True, 'native_compilation_reports_verified': True,
        'module_loaded': False, 'installable_bundle_created': False,
        'target_kernel_admission_proven': False, 'kernel_execution': 'not_tested',
        'gpu_access': False, 'hardware_admission': False,
        'original_entry_admission': False, 'production_candidate_allowed': False}
    for name, value in expected.items():
        require(type(report.get(name)) is type(value) and report[name] == value,
                'Strict native report contract refused: ' + name)
    final = report['final_image']
    require(final['filetype'] == 'MH_KEXT_BUNDLE' and final['installable_bundle'] is False and
            re.fullmatch('[0-9a-f]{64}', final['sha256']), 'Strict final image identity is incomplete')
    policy = report['final_link_policy']
    require(policy['dead_strip'] is True and policy['undefined_policy'] == 'error' and
            policy['unresolved_private_imports_permitted'] is False, 'Strict final link policy changed')
    require(type(report['source_plan']['complete_original_translation_units']) is int and
            report['source_plan']['complete_original_translation_units'] == 1100,
            'Strict report lacks all 1100 original translation units')
    require(report['source_plan']['complete_metaclass_classes'] == [
        'S540NvidiaGspPowerService', 'S540ProspectiveLoaderControl', 'S540ProspectiveLoaderClient'],
        'Strict report does not include all three exact metaclasses')
    for name in ('complete-relocatable-link', 'raw-development-kext-link'):
        rows = [row for row in report['commands'] if row['name'] == name]
        require(len(rows) == 1 and type(rows[0]['status']) is int and rows[0]['status'] == 0,
                'Strict native link command is absent or failed: ' + name)


def native_identity(cc, cxx):
    require(sys.platform == 'darwin' and platform.machine() == 'x86_64',
            'Packaging requires native Intel macOS and Apple clang')
    for relative, expected in PINNED_HELPERS.items():
        require(not (ROOT / relative).is_symlink() and sha(ROOT / relative) == expected,
                'A reviewed helper changed before native identity verification')
    common = compose.load('idle_package_common',
                          link.GSP / 'prospective-first-transaction/original/common.py')
    return common, common.execution_identity(cc, cxx, False)


def verify_image(path, approved, entries):
    parsed = link.Image(path, 11)
    audit = link.audit_symbols({path.name: parsed.externals()}, approved)
    for symbol in ('__start', '__stop'):
        parsed.code(symbol)
    for symbol in ('_kmod_info', '__realmain', '__antimain'):
        parsed.named(symbol)
    return {'imports': audit['public_imports'], 'symbols': parsed.symbols,
            'roots': link.verify_roots(path, expected_type=11),
            'loader_pointers': link.verify_final_loader_pointers(path, entries),
            'firmware': firmware.verify_embedded_firmware(path)}


def verify_build(args, execute, scratch):
    require(args.report.is_file() and not args.report.is_symlink(), 'Strict report must be an ordinary file')
    report_path = args.report.resolve(strict=True)
    require(re.fullmatch('[0-9a-f]{64}', args.report_sha256) and sha(report_path) == args.report_sha256,
            'Strict native report differs from independently supplied SHA256')
    report = json.loads(report_path.read_text())
    validate_report_contract(report)
    verifiers = verifier_bindings(report['builder_source_sha256'])
    home = report_path.parent
    composed = home / 'composition'
    require(str(composed.resolve(strict=True)) == report['composition_directory'] and
            sha(composed / 'composition.json') == report['composition_sha256'],
            'Strict native composition identity changed')
    value = compose.verify_composition(composed)
    require(value['original_file_count'] == 4005, 'Original source inventory is incomplete')
    require(link.verify_closed_loader_policy(composed) == report['closed_loader_policy'],
            'Closed loader policy differs from native proof')
    count = link.project_unit_count(value)
    require(report['source_plan']['canonical_project_translation_units'] == count,
            'Canonical native project source count changed')
    originals = json.loads((composed / 'full-original-compilation.json').read_text())
    projects = json.loads((composed / 'project-compilation.json').read_text())
    for kind, filename in (('original', 'full-original-compilation.json'), ('project', 'project-compilation.json')):
        require(sha(composed / filename) == report['compilation_reports'][kind + '_sha256'],
                'Native compilation report bytes changed')
    objects = link.compilation_inputs(composed, originals, original_units=True,
        planned_original_sources=report['source_plan']['declared_original_sources'])
    objects += link.compilation_inputs(composed, projects, original_units=False, expected_project_units=count)
    expected_objects = {str(path) for path in objects} | {
        str(home / name) for name in ('firmware-bytes.o', 'c_start.o', 'c_stop.o')}
    require(set(report['input_object_sha256']) == expected_objects and len(expected_objects) == 1100 + count + 3,
            'Native complete image object inventory changed')
    for name, expected in report['input_object_sha256'].items():
        path = Path(name)
        require(not path.is_symlink() and sha(path) == expected, 'Native image input bytes changed: ' + name)
    common, _ = native_identity(args.cc, args.cxx)
    sdk = common.validate_sdk(args.kernel_sdk.resolve(strict=True), None, False)
    require(sdk == report['sdk'], 'Pinned clean native SDK differs from strict report')
    archive = args.kernel_sdk / 'Library/x86_64/libkmod.a'
    runtime = report['pinned_module_runtime']
    require(sha(archive) == runtime['archive_sha256'] and runtime['legacy_libkmod_cpp_used'] is False,
            'Pinned module runtime changed')
    for member in ('c_start.o', 'c_stop.o'):
        raw = subprocess.run(['/usr/bin/ar', 'p', str(archive), member], capture_output=True, check=True).stdout
        require(raw == file_in(home, member).read_bytes(), 'Native C module wrapper differs from pinned archive')
    assets = firmware.ACQUIRE.verify_assets(args.assets_dir.resolve(strict=True))
    require(assets == report['firmware_asset_inventory'], 'Strict native firmware asset inventory changed')
    license_path, mapping = verified_notice(args.assets_dir)
    image = file_in(home, report['final_image']['path'])
    require(sha(image) == report['final_image']['sha256'] and image.stat().st_size == report['final_image']['bytes'],
            'Strict presign image bytes changed')
    reloc = file_in(home, report['relocatable_image']['path'])
    require(sha(reloc) == report['relocatable_image']['sha256'], 'Strict complete relocatable image changed')
    flags, cpp = link.kernel_flags(args.kernel_sdk)
    approved, references, power, loader = link.sdk_import_references(
        scratch, composed, args.cxx, flags, cpp, projects['results'], execute)
    require(sorted(approved) == report['approved_public_imports'], 'Independent public SDK import set changed')
    graph = combined.verify(reloc, power, loader)
    require(graph['entry_inventory_sha256'] == report['combined_metaclasses']['entry_inventory_sha256'],
            'Independent three-metaclass graph differs from native proof')
    entries = link.loader_pointer_names(reloc)
    proof = verify_image(image, approved, entries)
    require(proof['imports'] == report['final_image']['imports'] and proof['roots']['n_no_dead_strip'] is True,
            'Final image imports or typed roots differ from native proof')
    for observed, recorded in (('roots', 'final_original_roots'), ('loader_pointers', 'final_loader_pointers'),
                               ('firmware', 'final_embedded_firmware')):
        require(proof[observed] == report[recorded], 'Final image proof changed: ' + observed)
    frontend = link.verify_closed_character_frontend(link.Image(image, 11), value)
    require(frontend == report['final_character_frontend'], 'Closed character frontend changed')
    prototype = link.LOADER / 'Info.prototype.plist'
    contract = json.loads((link.LOADER / 'LOADER-PROTOTYPE-CONTRACTS.json').read_text())
    require(sha(prototype) == contract['source_sha256']['Info.prototype.plist'], 'Closed loader prototype changed')
    return dict(report=report, report_path=report_path, image=image, composed=composed,
        approved=approved, entries=entries, independent_references=references, metaclasses=graph,
        prototype=prototype, proof=proof, sdk=sdk, assets=assets,
        executing_verifier_source_sha256=verifiers, license_path=license_path, license_mapping=mapping,
        composition=value, character_frontend=frontend)


def bundle_info(prototype):
    value = plistlib.loads(prototype.read_bytes())
    require(value['CFBundleIdentifier'] == BUNDLE_ID and value['CFBundleVersion'] == '0.0.1' and
            value['S540OriginalEntryPolicy'] == 'closed', 'Closed loader bundle identity changed')
    personalities = value['IOKitPersonalities']
    require(list(personalities) == ['IdleControlOnly'], 'Bundle personality must be idle-only')
    idle = personalities['IdleControlOnly']
    require(idle['IOProviderClass'] == 'IOResources' and idle['IOResourceMatch'] == 'IOKit' and
            idle['IOClass'] == 'S540ProspectiveLoaderControl', 'Idle control provider changed')
    value.pop('S540SourceOnly')
    value.update(CFBundleExecutable=EXECUTABLE, CFBundleName='S540 idle complete-image ABI check',
        CFBundlePackageType='KEXT', OSBundleCompatibleVersion='0.0.1', OSBundleLibraries=LIBRARIES,
        S540IdleCompleteImageABIOnly=True, S540OriginalEntryPolicy='closed', S540HardwareEntryAdmission=False,
        S540OriginalRMInitializationTest=False, S540GSPInitializationTest=False, S540AccelerationTest=False)
    return value


def package(args):
    args.cc, args.cxx = args.cc.absolute(), args.cxx.absolute()
    common, identity = native_identity(args.cc, args.cxx)
    destination = args.output.resolve()
    require(not destination.exists(), 'Package output must be a fresh directory')
    for source in (args.report.resolve().parent, args.kernel_sdk.resolve(), args.assets_dir.resolve(),
                   ROOT / 'packages', ROOT / 'builders'):
        require(not destination.is_relative_to(source) and not source.is_relative_to(destination),
                'Package output overlaps a protected source or native build directory')
    require(destination.parent.is_dir(), 'Package output parent must exist')
    helpers = {str(path): sha(path) for path in sorted(HERE.rglob('*'))
               if path.is_file() and path.suffix in ('.py', '.c', '.sh', '.md')}
    commands = []
    with tempfile.TemporaryDirectory(prefix='s540-idle-image-package-', dir=destination.parent) as temporary:
        work = Path(temporary)
        references = work / 'references'; references.mkdir()
        def execute(command, name, *, cwd=None, timeout=120):
            command = [str(part) for part in command]
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
            (work / (name + '.log')).write_text(result.stdout + result.stderr)
            commands.append({'name': name, 'command': command, 'cwd': str(cwd) if cwd else None,
                             'status': result.returncode})
            require(result.returncode == 0, 'Native package step failed: ' + name + '; ' + result.stderr[-2000:])
            return result
        verified = verify_build(args, execute, references)
        staged = work / 'package'; staged.mkdir()
        bundle = staged / BUNDLE
        macos = bundle / 'Contents/MacOS'; macos.mkdir(parents=True)
        resources = bundle / 'Contents/Resources'; resources.mkdir()
        image = macos / EXECUTABLE
        shutil.copyfile(verified['image'], image); image.chmod(0o755)
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(bundle_info(verified['prototype'])))
        notice = resources / verified['license_mapping']['filename']
        shutil.copyfile(verified['license_path'], notice)
        evidence = staged / 'evidence'; evidence.mkdir()
        for source, name in ((verified['report_path'], 'strict-native-image.json'),
             (verified['image'], 'strict-presign-image.macho'),
             (verified['composed'] / 'composition.json', 'composition.json'),
             (references / 'sdk-power-metaclass-reference.o', 'sdk-power-metaclass-reference.o'),
             (references / 'sdk-loader-metaclass-reference.o', 'sdk-loader-metaclass-reference.o')):
            shutil.copyfile(source, evidence / name)
        controller = staged / 's540-idle-image-ctl'
        sdk_path = execute(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'], 'controller-sdk').stdout.strip()
        require(Path(sdk_path).is_dir(), 'Native user-space SDK is absent')
        flags = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-isysroot', sdk_path,
                 '-O2', '-Wall', '-Wextra', '-Werror', '-std=c11', '-I',
                 str(verified['composed'] / 'project/packages/nvidia-gsp-bootstrap/prospective-loader')]
        execute([args.cc, *flags, HERE / 'idle_ctl.c', '-framework', 'IOKit', '-framework',
                 'CoreFoundation', '-o', controller], 'compile-controller')
        decoder = work / 'idle-decoder-control'
        execute([args.cc, *flags, '-DS540_IDLE_CTL_DECODE_CONTROL', HERE / 'idle_ctl.c',
            verified['composed'] / 'project/packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderState.c',
            '-o', decoder], 'compile-idle-decoder')
        execute(['/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', decoder], 'sign-idle-decoder')
        execute(['/usr/bin/codesign', '--verify', '--strict', decoder], 'verify-idle-decoder')
        decoded = json.loads(execute([decoder], 'actual-idle-decoder').stdout)
        require(decoded['status'] == 'passed' and decoded['actual_loader_state'] is True,
                'Actual loader-state decoder control failed')
        for operation in ('load', 'unload', 'showloaded'):
            execute(['/usr/bin/kmutil', operation, '--help'], 'kmutil-' + operation + '-help')
        for source in sorted((HERE / 'scripts').glob('*.sh')):
            shutil.copyfile(source, staged / source.name); (staged / source.name).chmod(0o755)
        shutil.copyfile(HERE / 'TARGET-GUIDE.md', staged / 'READ-ME-FIRST.md')
        execute(['/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', bundle], 'sign-bundle')
        execute(['/usr/bin/codesign', '--verify', '--strict', bundle], 'verify-bundle')
        execute(['/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', controller], 'sign-controller')
        execute(['/usr/bin/codesign', '--verify', '--strict', controller], 'verify-controller')
        execute(['/usr/bin/codesign', '--display', '--verbose=4', bundle], 'display-bundle-signature')
        invariant = macho_signing.compare(verified['image'], image)
        post = verify_image(image, verified['approved'], verified['entries'])
        require(post['imports'] == verified['proof']['imports'] and post['symbols'] == verified['proof']['symbols'],
                'Signing changed actual symbols or imports')
        for key in ('roots', 'loader_pointers'):
            clean = lambda row: {k: v for k, v in row.items() if k != 'image_sha256'}
            require(clean(post[key]) == clean(verified['proof'][key]), 'Signing changed actual ' + key)
        require(post['firmware'] == verified['proof']['firmware'], 'Signing changed embedded firmware')
        frontend = link.verify_closed_character_frontend(link.Image(image, 11), verified['composition'])
        require(frontend == verified['character_frontend'], 'Signing changed closed character frontend')
        require(sha(notice) == verified['license_mapping']['sha256'] and
                sha(verified['license_path']) == verified['license_mapping']['sha256'], 'Redistributed notice changed')
        require(all(sha(Path(path)) == expected for path, expected in helpers.items()), 'Packager source changed')
        require(verifier_bindings(verified['report']['builder_source_sha256']) ==
                verified['executing_verifier_source_sha256'], 'Executing verifier source changed')
        require(sha(verified['report_path']) == args.report_sha256 and
                sha(verified['image']) == invariant['presign_sha256'], 'Strict native input changed during packaging')
        compose.verify_composition(verified['composed'])
        require(link.verify_closed_loader_policy(verified['composed']) == verified['report']['closed_loader_policy'],
                'Closed loader source changed during packaging')
        require(common.validate_sdk(args.kernel_sdk, None, False) == verified['sdk'], 'Pinned SDK changed')
        require(firmware.ACQUIRE.verify_assets(args.assets_dir) == verified['assets'], 'Firmware assets changed')
        for path in staged.rglob('*'):
            path.chmod(0o755 if path.is_dir() or path == image or path == controller or path.suffix == '.sh' else 0o644)
        staged.chmod(0o755)
        execute(['/usr/bin/codesign', '--verify', '--strict', bundle], 'final-verify-bundle')
        execute(['/usr/bin/codesign', '--verify', '--strict', controller], 'final-verify-controller')
        logs = evidence / 'native-logs'; logs.mkdir()
        for path in sorted(work.glob('*.log')):
            shutil.copyfile(path, logs / path.name); (logs / path.name).chmod(0o644)
        inventory = {str(path.relative_to(staged)): sha(path) for path in sorted(staged.rglob('*')) if path.is_file()}
        (staged / 'SHA256SUMS').write_text(''.join(value + '  ' + name + '\n' for name, value in inventory.items()))
        attestation = {'format': 1, 'status': 'packaged-idle-complete-image-abi-check',
            'target': TARGET, 'bundle_identifier': BUNDLE_ID, 'bundle_path': BUNDLE, 'executable': EXECUTABLE,
            'strict_native_report_sha256': args.report_sha256,
            'strict_presign_image_sha256': invariant['presign_sha256'],
            'signed_image': {'sha256': sha(image), 'bytes': image.stat().st_size, 'uuid': invariant['uuid']},
            'signature_invariance': invariant, 'postsign_roots': post['roots'],
            'postsign_loader_pointers': post['loader_pointers'], 'postsign_firmware': post['firmware'],
            'postsign_imports': post['imports'], 'postsign_character_frontend': frontend,
            'combined_metaclasses': verified['metaclasses'], 'firmware_license': verified['license_mapping'],
            'independent_sdk_references': verified['independent_references'], 'sdk': verified['sdk'],
            'closed_loader_policy': verified['report']['closed_loader_policy'],
            'package_manifest_sha256': sha(staged / 'SHA256SUMS'), 'inventory': inventory,
            'packager_source_sha256': helpers,
            'executing_verifier_source_sha256': verified['executing_verifier_source_sha256'],
            'native_packager': identity, 'commands': commands, 'actual_loader_state_control': decoded,
            'declared_apple_dependencies': LIBRARIES, 'target_loader_abi_observed': False,
            'module_loaded': False, 'installable_bundle_created': True, 'system_security_changed': False, **CLOSED}
        for key in ('postsign_roots', 'postsign_loader_pointers'):
            attestation[key] = {k: v for k, v in attestation[key].items() if k not in link.GATES}
        write_json(staged / 'packaging-attestation.json', attestation)
        staged.rename(destination)
    return {'status': 'packaged-idle-complete-image-abi-check', 'output': str(destination),
            'attestation_sha256': sha(destination / 'packaging-attestation.json'), **CLOSED}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'kernel-sdk', 'assets-dir', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--cc', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--cxx', type=Path, default=Path('/usr/bin/clang++'))
    print(json.dumps(package(parser.parse_args()), sort_keys=True))


if __name__ == '__main__':
    main()
