#!/usr/bin/env python3
"""Compile the isolated original RM and actual Darwin execution bridge.

The caller owns the final kext link and must validate its complete imports.
No compilation result is evidence that kernel GPU initialization succeeded.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import platform
import sys

import compile_nvidia_global_rm as original
import nvidia_execution_commands as commands
import nvidia_execution_closure as closure
import embed_nvidia_firmware as firmware
import nvidia_metaclass_initializers as metaclass
import nvidia_stack_usage as stack_usage

ROOT = Path(__file__).resolve().parents[1]
GLOBAL = ROOT / 'packages/nvidia-global-rm'
SERVICES = ROOT / 'packages/nvidia-darwin-services'
DEVICE = ROOT / 'packages/nvidia-device-transport'
GSP = ROOT / 'packages/nvidia-gsp-bootstrap'
CRYPTO = ROOT / 'packages/nvidia-global-rm-crypto'
ASSETS = ROOT / 'packages/nvidia-firmware-assets'


@dataclass
class KernelBuild:
    objects: list[Path]
    sources: list[Path]
    namespace_header: Path
    unexported_symbols: Path
    validation: dict


def project_sources() -> tuple[list[Path], list[Path], list[Path]]:
    """Select all reviewed production units in the declared component dirs."""
    directories = [GLOBAL / 'src', SERVICES / 'src', DEVICE / 'src',
                   GSP / 'src', GSP / 'platform', GSP / 'evidence', GSP / 'timers']
    cpp = sorted({path for directory in directories for path in directory.glob('*.cpp')})
    original_c = sorted({path for directory in (GLOBAL / 'src', DEVICE / 'src', GSP / 'src', GSP / 'evidence', GSP / 'timers')
                         for path in directory.glob('*.c')} |
                        {GSP / 'cancellation/S540NvidiaGspCancellation.c'})
    plain_c = [CRYPTO / 'src/S540NvidiaGlobalCrypto.c']
    cpp += [ASSETS / 'src/S540NvidiaFirmwareAssets.cpp']
    required = {GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp',
                GLOBAL / 'src/S540NvidiaGlobalRmOs.c',
                GLOBAL / 'src/S540NvidiaGlobalRmLifecycle.c',
                DEVICE / 'src/S540NvidiaDarwinDevice.cpp',
                GSP / 'src/S540NvidiaGspFirmwareOriginal.c',
                GSP / 'src/S540NvidiaGspFirmware.cpp',
                GSP / 'src/S540NvidiaGspBootstrap.cpp',
                GSP / 'src/S540NvidiaGspDispatcher.cpp',
                GSP / 'src/S540NvidiaGspContext.c',
                GSP / 'timers/S540NvidiaGspTimersOriginal.c'}
    selected = set(cpp + original_c + plain_c)
    if not required <= selected or len(selected) != len(cpp + original_c + plain_c):
        raise ValueError('The full RM execution source profile is incomplete or duplicated.')
    return cpp, original_c, plain_c


def audit_platform_imports(output: Path, kernel_flags: list[str], cpp_flags: list[str],
                           linked_project: Path, original_definitions: list[str],
                           metaclass_reference: Path) -> dict:
    """New imports must match authored SDK operations, never observed allowlists."""
    import build_nvidia_transport as transport
    baseline = set(transport.ADAPTER_IMPORTS)
    _, hardware = transport.compile_hardware_import_reference(output, kernel_flags, cpp_flags)
    _, services = transport.compile_services_import_reference(output, kernel_flags, cpp_flags)
    baseline.update(hardware)
    baseline.update(services)
    references = [SERVICES / 'tests/sdk_import_reference.cpp',
                  GLOBAL / 'tests/sdk_import_reference.cpp',
                  DEVICE / 'tests/sdk_import_reference.cpp',
                  GSP / 'platform/tests/sdk_import_reference.cpp',
                  GSP / 'platform/tests/sdk_power_reference.cpp',
                  GSP / 'tests/sdk_dispatcher_reference.cpp']
    approved, component_imports = set(), {}
    for index, source in enumerate(references):
        obj = output / ('execution-sdk-reference-' + str(index) + '.o')
        commands.run('/usr/bin/xcrun', 'clang++', *kernel_flags, *cpp_flags,
                      '-c', str(source), '-o', str(obj))
        transport.macho(obj, 1)
        transport.verify_no_static_initializers(obj, 'An independent execution SDK reference')
        imports = transport.kernel_imports(obj)
        approved.update(imports)
        component_imports[source.relative_to(ROOT).as_posix()] = sorted(imports)
    # An actual IOService subclass also needs all inherited SDK virtual slots.
    # Derive them from the independent same-declaration reference, after its
    # exact loader proof, excluding only actual private project definitions.
    inherited, project_dependencies = metaclass.framework_imports(linked_project, metaclass_reference)
    approved.update(inherited)
    component_imports['verified-power-metaclass-framework'] = sorted(inherited)
    previous_exports = set()
    dependencies = [ROOT / 'packages/nvidia-hardware-transport/src/S540NvidiaPci.cpp',
                    ROOT / 'packages/nvidia-hardware-transport/firmware/S540NvidiaFirmware.cpp']
    for source in dependencies:
        obj = output / ('prior-dependency-' + source.stem + '.o')
        commands.run('/usr/bin/xcrun', 'clang++', *kernel_flags, *cpp_flags,
                      '-c', str(source), '-o', str(obj))
        transport.macho(obj, 1)
        previous_exports.update(commands.run('/usr/bin/nm', '-g', '-j', '-U', str(obj)).stdout.split())
    platform_imports = (transport.kernel_imports(linked_project) - previous_exports -
                        {'_' + symbol for symbol in original_definitions})
    actual_new = platform_imports - baseline
    expected_new = approved - baseline
    if actual_new != expected_new:
        raise ValueError('The actual execution bridge imports differ from the independent pinned SDK operations: '
                         'unreviewed=' + str(sorted(actual_new - expected_new)) +
                         '; missing=' + str(sorted(expected_new - actual_new)))
    return {'format': 1, 'status': 'matched',
            'platform_import_count': len(platform_imports),
            'new_sdk_import_count': len(actual_new),
            'platform_imports': sorted(platform_imports),
            'additional_sdk_imports': sorted(actual_new),
            'independent_references': component_imports,
            'metaclass_reference_project_dependencies': sorted(project_dependencies),
            'existing_v9_approved_imports': sorted(baseline),
            'unreviewed_imports': [], 'missing_expected_imports': [],
            'reference_source_sha256': {source.relative_to(ROOT).as_posix():
                hashlib.sha256(source.read_bytes()).hexdigest()
                for source in [*references, *dependencies]}}


@commands.logged(output_argument=1, report='execution-kernel-build.json')
def kernel_objects(upstream: Path, output: Path, assets: Path,
                   kernel_flags: list[str], cpp_flags: list[str],
                   *, compiled_directory: Path | None = None,
                   checked_cleanup_overlays: bool = False) -> KernelBuild:
    import build_nvidia_transport as transport
    cpp_flags = kernel_cpp_flags(cpp_flags)
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    partial = {'format': 1, 'status': 'running', 'phase': 'verify-original-compilation',
               'completed_project_sources': [], 'production_candidate_allowed': False,
               'checked_cleanup_overlays': checked_cleanup_overlays,
               'global_rm_executed': False, 'adapter_initialized': False,
               'gsp_initialized': False, 'gpu_operations': False}
    report = output / 'execution-kernel-build.json'
    def save_partial() -> None:
        report.write_text(json.dumps(partial, indent=2, sort_keys=True) + '\n')
    save_partial()
    upstream = upstream.resolve(strict=True)
    if original.execute(['git', '-C', str(upstream), 'rev-parse', 'HEAD']).stdout.strip() != original.COMMIT:
        raise ValueError('The full original RM source differs from its pinned revision.')
    if original.execute(['git', '-C', str(upstream), 'status', '--porcelain']).stdout:
        raise ValueError('Full original RM bridge compilation requires an unchanged source checkout.')
    compilation_root = (compiled_directory.resolve(strict=True) if compiled_directory else
                        output / 'original-rm')
    checked_source = None
    if checked_cleanup_overlays:
        if not compiled_directory:
            original.compile_with_namespace(upstream, compilation_root, Path('/usr/bin/clang'))
            original.compile_checked_overlays(upstream, compilation_root, Path('/usr/bin/clang'))
        compiled, checked_source, namespace, original_objects = original.load_checked_compilation(
            upstream, compilation_root)
    elif compiled_directory:
        compiled = json.loads((compilation_root / 'darwin-compile.json').read_text())
        if (compiled.get('status') != 'compiled' or compiled.get('native_apple_compiler') is not True
                or compiled.get('cross_compile_probe') is not False
                or compiled.get('namespace_applied') is not True
                or compiled.get('source_namespace_verified') is not True
                or compiled.get('commit') != original.COMMIT):
            raise ValueError('Only this pinned native Apple compilation can be reused.')
    else:
        compiled = original.compile_with_namespace(upstream, compilation_root, Path('/usr/bin/clang'))
    if not checked_cleanup_overlays:
        namespace = compilation_root / 'original/contract/S540GlobalRmNamespace.h'
        original_objects = sorted((compilation_root / 'namespaced').glob('*.o'))
    if len(original_objects) != 1100:
        raise ValueError('The actual full RM kernel closure lost an original translation unit.')
    actual_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in original_objects}
    if actual_hashes != compiled.get('object_sha256'):
        raise ValueError('The reused native original RM object bytes changed.')
    actual_namespace = original.audit_namespace(original_objects, namespace)
    if actual_namespace != compiled['namespace_contract']:
        raise ValueError('The reused original RM private namespace changed.')
    cpp, c, plain_c = project_sources()
    metaclass_reference = metaclass.compile_reference(output, kernel_flags, cpp_flags)
    metaclass_object_review = None
    partial.update(phase='compile-project-bridges', original_source_objects=len(original_objects))
    save_partial()
    bridge = original.original_bridge_flags(
        upstream, compilation_root / ('checked-namespaced' if checked_cleanup_overlays else 'namespaced'),
        Path('/usr/bin/clang'), namespace, checked_source=checked_source)
    stack_capability = {
        'c': stack_usage.verify_codegen(['/usr/bin/xcrun', 'clang'],
            [*kernel_flags, '-std=c11'], output / 'stack-usage-capability-c', native_apple=True),
        'cpp': stack_usage.verify_codegen(['/usr/bin/xcrun', 'clang++'],
            [*kernel_flags, *cpp_flags], output / 'stack-usage-capability-cpp',
            cpp=True, native_apple=True)}
    objects = list(original_objects)
    project_objects = []
    project_stack = []
    for source in [*cpp, *c, *plain_c]:
        obj = output / (source.stem + '.o')
        if source in c:
            # Original headers receive the full original NVRM/NvPort/NVOC ABI.
            # Only these C bridge units receive the private namespace macros.
            flags = [*bridge, '-mkernel', '-arch', 'x86_64',
                     '-mmacosx-version-min=15.0', '-DKERNEL', '-D__KERNEL__',
                     '-Wframe-larger-than=4096', '-Werror=frame-larger-than']
            compiler = 'clang'
        elif source in plain_c:
            flags = [*kernel_flags, '-std=c11', '-Wframe-larger-than=4096']
            compiler = 'clang'
        else:
            flags = [*kernel_flags, *cpp_flags, '-Wframe-larger-than=4096']
            compiler = 'clang++'
        command = ['/usr/bin/xcrun', compiler, *flags, '-fstack-usage',
                   '-c', str(source), '-o', str(obj)]
        commands.run(*command,
                      diagnostic_log=output / (source.stem + '-compile.log'))
        transport.macho(obj, 1)
        project_stack.append(stack_usage.capture_usage(source, obj, command, native_apple=True))
        if source == GSP / 'platform/S540NvidiaGspPower.cpp':
            metaclass_object_review = metaclass.verify_metaclass_initializers(obj, metaclass_reference)
        else:
            metaclass.verify_no_initializers(obj)
        objects.append(obj)
        project_objects.append(obj)
        partial['completed_project_sources'].append(source.relative_to(ROOT).as_posix())
        save_partial()
    project_stack_manifest = stack_usage.usage_manifest(
        project_stack, output / 'stack-usage-manifest.json')
    partial['phase'] = 'audit-compiler-stack-usage'
    save_partial()
    stack_audit = stack_usage.audit(
        [compiled.get('stack_usage'), project_stack_manifest], output / 'stack-audit.json',
        expected_objects=[*original_objects, *project_objects])
    partial['phase'] = 'embed-firmware'
    save_partial()
    assembly, embedding = firmware.emit_assembly(assets, output)
    firmware_object = output / 'S540NvidiaFirmwareBytes.o'
    commands.run('/usr/bin/xcrun', 'clang', '-arch', 'x86_64',
                 '-mmacosx-version-min=15.0', '-c', str(assembly),
                 '-o', str(firmware_object), cwd=assets.resolve(strict=True),
                 diagnostic_log=output / 'firmware-compile.log')
    embedded = firmware.verify_embedded_firmware(firmware_object)
    objects.append(firmware_object)
    defined = compiled['namespace_contract']['defined']
    if not defined or any(not symbol.startswith(original.PREFIX) for symbol in defined):
        raise ValueError('Original full RM exports escaped the private namespace audit.')
    hidden = output / 'original-rm-private-symbols.txt'
    hidden.write_text(''.join('_' + symbol + '\n' for symbol in defined))
    linked = output / 'execution-bridge.o'
    commands.run('/usr/bin/xcrun', 'ld', '-r', '-arch', 'x86_64',
                  *(str(path) for path in project_objects), '-o', str(linked),
                  diagnostic_log=output / 'execution-bridge-link.log')
    transport.macho(linked, 1)
    if metaclass_object_review is None:
        raise ValueError('The execution bridge lost the reviewed power metaclass.')
    linked_metaclass_review = metaclass.verify_metaclass_initializers(linked, metaclass_reference)
    partial['phase'] = 'audit-platform-imports'
    save_partial()
    platform_import_audit = audit_platform_imports(
        output, kernel_flags, cpp_flags, linked, defined, metaclass_reference)
    partial['phase'] = 'audit-actual-original-rm-closure'
    save_partial()
    execution_closure = closure.analyze_execution_closure(
        linked, original_objects, compiled, output / 'original-rm-closure', upstream=upstream,
        user_pin_source_tree=checked_source if checked_source is not None else upstream,
        metaclass_reference=metaclass_reference)
    record = {'format': 1, 'status': 'compiled', 'architecture': 'x86_64',
              'production_candidate_allowed': False,
              'milestone_status': 'development-source-only; adapter runtime closure unresolved',
              'original_rm': compiled, 'embedding': embedding,
              'embedded_object': embedded,
              'original_source_objects': len(original_objects),
              'project_source_objects': len(project_objects),
              'private_original_definitions': len(defined),
              'project_imports': sorted(transport.kernel_imports(linked)),
              'platform_import_audit': platform_import_audit,
              'power_metaclass_object_audit': metaclass_object_review,
              'linked_power_metaclass_audit': linked_metaclass_review,
              'stack_usage_capability': stack_capability,
              'stack_usage': project_stack_manifest,
              'aggregate_stack_audit': stack_audit,
              'execution_closure': execution_closure,
              'checked_cleanup_overlays': checked_cleanup_overlays,
              'original_header_profile': 'checked-cleanup-development' if checked_source else 'unchanged-baseline',
              'global_rm_executed': False, 'adapter_initialized': False,
              'gsp_initialized': False, 'gpu_operations': False,
              'source_sha256': {path.relative_to(ROOT).as_posix():
                  hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted([*cpp, *c, *plain_c])}}
    (output / 'execution-kernel-build.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return KernelBuild(objects=objects, sources=[*cpp, *c, *plain_c],
                       namespace_header=namespace, unexported_symbols=hidden,
                       validation=record)


def kernel_cpp_flags(flags: list[str]) -> list[str]:
    result = list(flags)
    if '-fno-use-cxa-atexit' not in result:
        result.append('-fno-use-cxa-atexit')
    # LLVM's Mach-O destructor lowering otherwise synthesizes __cxa_atexit
    # even with the frontend flag. Kext unload uses the explicit term table.
    if '-disable-atexit-based-global-dtor-lowering' not in result:
        result += ['-mllvm', '-disable-atexit-based-global-dtor-lowering']
    return result


def main() -> int:
    import build_nvidia_transport as transport
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--kernel-sdk', type=Path, required=True)
    parser.add_argument('--assets-dir', type=Path)
    parser.add_argument('--metaclass-preflight', action='store_true',
                        help='Verify actual kernel power-service loader code before compiling full RM.')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--compiled-directory', type=Path)
    parser.add_argument('--checked-cleanup-overlays', action='store_true',
                        help='Use the verified composed cleanup sources and checked headers for all RM bridges.')
    args = parser.parse_args()
    if not args.metaclass_preflight and (args.upstream is None or args.assets_dir is None):
        parser.error('--upstream and --assets-dir are required for the full execution build')
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('Authoritative kernel compilation requires Intel macOS.')
    sdk = args.kernel_sdk.resolve(strict=True)
    if commands.run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != transport.SDK_COMMIT:
        raise ValueError('The development kernel SDK differs from its pinned revision.')
    flags = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-mkernel',
             '-fno-builtin', '-ffreestanding', '-fno-common', '-fno-stack-protector',
             '-fno-asynchronous-unwind-tables', '-fno-unwind-tables', '-mno-red-zone',
             '-DKERNEL', '-D__KERNEL__', '-O2', '-Wall', '-Wextra', '-Werror',
             '-Wno-deprecated-declarations', '-nostdinc', '-isystem', str(sdk / 'Headers'),
             '-I', str(ROOT / 'packages/nvidia-os-adapter/upstream/include')]
    cpp = kernel_cpp_flags(['-fapple-kext', '-fno-exceptions', '-fno-rtti',
                           '-fno-threadsafe-statics', '-nostdinc++', '-std=c++17'])
    if args.metaclass_preflight:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        reference = metaclass.compile_reference(args.output_dir, flags, cpp)
        actual = args.output_dir / 'power-service.o'
        commands.run('/usr/bin/xcrun', 'clang++', *flags, *cpp, '-Wframe-larger-than=4096',
                     '-c', str(GSP / 'platform/S540NvidiaGspPower.cpp'), '-o', str(actual),
                     diagnostic_log=args.output_dir / 'power-service-compile.log')
        record = metaclass.verify_metaclass_initializers(actual, reference)
        # ld -r can change symbol/relocation encodings. Exercise the real linker
        # before the expensive original RM build, including unrelated code
        # before and after this one approved class initializer.
        companions = []
        for name in ('Check', 'Runtime'):
            obj = args.output_dir / ('services-' + name + '.o')
            commands.run('/usr/bin/xcrun', 'clang++', *flags, *cpp,
                         '-c', str(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp')),
                         '-o', str(obj), diagnostic_log=args.output_dir / ('services-' + name + '-compile.log'))
            metaclass.verify_no_initializers(obj)
            companions.append(obj)
        linked = args.output_dir / 'power-service-linked.o'
        commands.run('/usr/bin/xcrun', 'ld', '-r', '-arch', 'x86_64',
                     str(companions[0]), str(actual), str(companions[1]), '-o', str(linked),
                     diagnostic_log=args.output_dir / 'power-service-link.log')
        record['linked_metaclass_audit'] = metaclass.verify_metaclass_initializers(linked, reference)
        record['kernel_cpp_flags'] = cpp
        (args.output_dir / 'metaclass-preflight.json').write_text(json.dumps(record, indent=2) + '\n')
        print('Power-service kernel loader preflight passed; no kernel code was executed.')
        return 0
    kernel_objects(args.upstream, args.output_dir, args.assets_dir, flags, cpp,
                   compiled_directory=args.compiled_directory,
                   checked_cleanup_overlays=args.checked_cleanup_overlays)
    print('Development kernel objects compiled; no candidate ZIP or runtime milestone is produced.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
