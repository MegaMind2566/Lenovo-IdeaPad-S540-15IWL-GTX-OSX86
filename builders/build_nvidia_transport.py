#!/usr/bin/env python3
"""Build the integrated NVIDIA runtime/RM consumer and bounded TU117 probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-transport'
ADAPTER = ROOT / 'packages/nvidia-os-adapter'
CALLERS = ROOT / 'packages/nvidia-caller-integration'
LIFECYCLE = ROOT / 'packages/nvidia-nvport-lifecycle'
RUNTIME = ROOT / 'packages/nvidia-nvport-runtime'
PACKAGE = 'S540-nvidia-transport-v7'
VERSION = '0.7.0'
SDK_COMMIT = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
BUNDLE = 'S540NvidiaPCIProbe.kext'
EXECUTABLE = 'S540NvidiaPCIProbe'
# The reserve/mutex backend replaces the earlier allocator/sync OS hooks.
# Linking those earlier translation units here would duplicate NVIDIA symbols.
ADAPTER_CPP = ('S540NvidiaClock', 'S540NvidiaMemory', 'S540NvidiaRuntime')
ADAPTER_C = ('nvport_time_uptime', 'nvport_memory_primitives')
CALLER_CPP = ('S540NvidiaReserve', 'S540NvidiaMutex',
              'S540NvidiaCallerAssertions', 'S540NvidiaCallerRuntime')
# The v6 original owned-mutex extraction includes the five v5 operations.
# Keep only the v5 untracked allocator object to avoid duplicate caller symbols.
CALLER_C = ('nvport_allocator_callers',)
LIFECYCLE_CPP = ('S540NvidiaSpinlock', 'S540NvidiaLifecycleRuntime',
                 'S540NvidiaLifecycleDiagnostics')
LIFECYCLE_C = ('nvport_memory_lifecycle', 'nvport_owned_sync')
RUNTIME_CPP = ('S540NvidiaSupportRuntime', 'S540NvidiaRmConsumer')
RUNTIME_C = ('nvport_runtime_strings', 'nvport_runtime_prng', 'nvport_runtime_core')
CONSUMER_C = ('vector', 'list')
CALLER_SYMBOLS = (
    'os_alloc_mem', 'os_free_mem', 'os_alloc_mutex', 'os_free_mutex',
    'os_acquire_mutex', 'os_cond_acquire_mutex', 'os_release_mutex',
    '_portMemAllocPagedUntracked', '_portMemAllocNonPagedUntracked', '_portMemFreeUntracked',
    'portSyncMutexInitialize', 'portSyncMutexDestroy', 'portSyncMutexAcquire',
    'portSyncMutexAcquireConditional', 'portSyncMutexRelease', 's540NvidiaCallerAssertionFailed',
    'os_alloc_spinlock', 'os_free_spinlock', 'os_acquire_spinlock', 'os_release_spinlock',
    'portSyncSpinlockInitialize', 'portSyncSpinlockDestroy', 'portSyncSpinlockAcquire',
    'portSyncSpinlockRelease', 'portSyncSpinlockCreate', 'portSyncMutexCreate',
    's540NvportMemoryInitialize', 's540NvportMemoryIsInitialized', 's540NvportMemoryIsCold',
    's540NvportMemoryAllocatorCount', 'portMemShutdown', 'portMemAllocPaged',
    'portMemAllocNonPaged', 'portMemFree', 'portMemAllocatorCreatePaged',
    'portMemAllocatorCreateNonPaged', 'portMemAllocatorRelease',
    'portMemAllocatorGetGlobalNonPaged', 'portMemAllocatorGetGlobalPaged',
    'portMemInitializeAllocatorTracking', '_portMemAllocatorAlloc', '_portMemAllocatorFree',
    'portMemExTrackingGetActiveStats', 'portMemExTrackingGetTotalStats',
    'portMemExTrackingGetPeakStats', 'portMemPrintTrackingInfo', 'portMemPrintAllTrackingInfo',
    'portMemRegisterOomReportCb', 'portMemReportOom', 'portDbgPrintf',
    's540NvportLifecycleContextAllowed',
)
CALLER_DATA_SYMBOLS = ('portSyncSpinlockSize', 'portSyncMutexSize')
RUNTIME_SYMBOLS = (
    's540NvportRuntimeInitialize', 's540NvportRuntimeShutdown',
    's540NvportRuntimeIsInitialized', 's540NvportRuntimeIsCold',
    'portStringLength', 'portStringLengthSafe', 'portStringCompare',
    'portStringCompareIgnoreCase', 'portStringCopy', 'portStringCat',
    'portStringConvertAsciiToUtf16', 'portStringBufferToHex', 'portStringTok',
    'portStringStrStr', 'portStringStrChar',
    'portCryptoInitialize', 'portCryptoShutdown',
    'portCryptoPseudoRandomGeneratorCreate', 'portCryptoPseudoRandomGeneratorDestroy',
    'portCryptoPseudoRandomGeneratorGetU32', 'portCryptoPseudoRandomGeneratorGetU64',
    'portCryptoPseudoRandomGeneratorFillBuffer', 'portCryptoPseudoRandomSetSeed',
    'portCryptoPseudoRandomGetU32', 'portCryptoPseudoRandomGetU64',
    'portCryptoPseudoRandomFillBuffer',
)
RUNTIME_DATA_SYMBOLS = ('portCryptoDefaultGenerator',)
CONSUMER_SYMBOLS = (
    'vectAppend_IMPL', 'vectAt_IMPL', 'vectCapacity_IMPL', 'vectClear_IMPL',
    'vectCount_IMPL', 'vectDestroy_IMPL', 'vectInit_IMPL', 'vectInsert_IMPL',
    'vectIsEmpty_IMPL', 'vectIsValid_IMPL', 'vectIterNext_IMPL', 'vectIterPrev_IMPL',
    'vectIterRange_IMPL', 'vectPrepend_IMPL', 'vectRemove_IMPL', 'vectReserve_IMPL',
    'vectTrim_IMPL',
    'listAppendExisting_IMPL', 'listAppendNew_IMPL', 'listAppendValue_IMPL',
    'listCount_IMPL', 'listDestroyIntrusive_IMPL', 'listDestroy_IMPL',
    'listFindByValue_IMPL', 'listHead_IMPL', 'listInitIntrusive_IMPL', 'listInit_IMPL',
    'listInsertExisting_IMPL', 'listInsertNew_IMPL', 'listInsertValue_IMPL',
    'listIsValid_IMPL', 'listIterNext_IMPL', 'listIterRange_IMPL', 'listNext_IMPL',
    'listPrependExisting_IMPL', 'listPrependNew_IMPL', 'listPrependValue_IMPL',
    'listPrev_IMPL', 'listRemoveAllByValue_IMPL', 'listRemoveFirstByValue_IMPL',
    'listRemoveIntrusive_IMPL', 'listRemove_IMPL', 'listTail_IMPL',
)
FORBIDDEN_RUNTIME_SYMBOLS = ('portInitialize', 'portShutdown',
                             'portStringBufferToHexGroups')
KPI_LIBRARIES = {
    'com.apple.kpi.iokit': '8.0.0', 'com.apple.kpi.libkern': '8.0.0',
    'com.apple.kpi.mach': '8.0.0', 'com.apple.iokit.IOPCIFamily': '2.9.0',
}
# The combined adapter must leave only these ordinary Darwin CPU/RAM APIs
# unresolved. Audit it before adding the existing IOKit PCI probe.
ADAPTER_IMPORTS = {
    '_clock_get_uptime', '_absolutetime_to_nanoseconds', '_clock_timebase_info',
    '_memcpy', '_memset', '_memcmp',
    # Compiler-emitted ordinary-RAM zeroing: pinned XNU Libkern.exports and
    # osfmk/x86_64/bzero.s export and implement this alias of bzero.
    '___bzero',
    '_IOMallocAligned', '_IOFreeAligned', '_IOMalloc', '_IOFree',
    '_IOSimpleLockAlloc', '_IOSimpleLockFree', '_IOSimpleLockLock', '_IOSimpleLockUnlock',
    '_ml_at_interrupt_context', '_ml_get_interrupts_enabled', '_ml_set_interrupts_enabled',
    '_assert_wait', '_thread_block', '_thread_wakeup_prim', '_panic',
    # Real bounded formatted lifecycle diagnostics; pinned XNU IOKit.exports
    # and Libkern.exports expose these through the existing KPI dependencies.
    '_IOLog', '_vsnprintf',
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=180)


def plain(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError('A required regular file is missing: ' + path.name)


def macho(path: Path, expected_type: int) -> None:
    header = path.read_bytes()[:16]
    if len(header) != 16 or struct.unpack('<IIII', header)[0:2] != (0xFEEDFACF, 0x01000007) or struct.unpack('<IIII', header)[3] != expected_type:
        raise ValueError('The output has the wrong Intel Mach-O type: ' + path.name)
    if run('/usr/bin/lipo', '-archs', str(path)).stdout.strip() != 'x86_64':
        raise ValueError('The build must contain only x86_64.')


def native_check(binary: Path) -> dict:
    macho(binary, 2)
    run('/usr/bin/codesign', '--force', '--sign', '-', str(binary))
    run('/usr/bin/codesign', '--verify', '--strict', str(binary))
    result = json.loads(run(str(binary)).stdout)
    if (result.get('status') != 'passed' or result.get('execution') != 'native-user-space'
            or result.get('gpu_access') is not False
            or result.get('kernel_runtime') != 'not_tested'
            or type(result.get('checks')) is not int or result['checks'] < 1):
        raise ValueError('Unexpected native check result: ' + binary.name)
    return result


def adapter_sources() -> tuple[list[Path], list[Path]]:
    """Preserve the reviewed v6 closure and its independent native checks."""
    cpp = [ADAPTER / 'src' / (stem + '.cpp') for stem in ADAPTER_CPP]
    cpp += [CALLERS / 'src' / (stem + '.cpp') for stem in CALLER_CPP]
    cpp += [LIFECYCLE / 'src' / (stem + '.cpp') for stem in LIFECYCLE_CPP]
    c = [ADAPTER / 'upstream' / (stem + '.c') for stem in ADAPTER_C]
    c += [CALLERS / 'upstream' / (stem + '.c') for stem in CALLER_C]
    c += [LIFECYCLE / 'upstream' / (stem + '.c') for stem in LIFECYCLE_C]
    return cpp, c


def runtime_sources() -> tuple[list[Path], list[Path]]:
    """The v7 extension, linked together with the confirmed v6 closure."""
    cpp = [RUNTIME / 'src' / (stem + '.cpp') for stem in RUNTIME_CPP]
    c = [RUNTIME / 'upstream' / (stem + '.c') for stem in RUNTIME_C]
    c += [RUNTIME / 'upstream/consumer' / (stem + '.c') for stem in CONSUMER_C]
    return cpp, c


def production_sources() -> tuple[list[Path], list[Path]]:
    cpp, c = adapter_sources()
    extra_cpp, extra_c = runtime_sources()
    return [*cpp, *extra_cpp], [*c, *extra_c]


def native_flags() -> list[str]:
    return ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-O2',
            '-Wall', '-Wextra', '-Werror',
            '-I', str(ADAPTER / 'upstream/include'),
            '-I', str(ADAPTER / 'src'), '-I', str(CALLERS / 'src'),
            '-I', str(LIFECYCLE / 'src'), '-I', str(LIFECYCLE / 'upstream'),
            '-I', str(RUNTIME / 'src'), '-I', str(RUNTIME / 'upstream'),
            '-I', str(RUNTIME / 'upstream/consumer/include')]


def source_flags(source: Path) -> list[str]:
    # These unchanged container translation units use the narrow consumer
    # NvPort profile. Other adapter units must retain the original nvport.h
    # first, particularly S540NvidiaAtomic.h and its pinned atomic headers.
    if source in {
            RUNTIME / 'upstream/consumer/vector.c',
            RUNTIME / 'upstream/consumer/list.c',
            RUNTIME / 'src/S540NvidiaRmConsumer.cpp',
            RUNTIME / 'tests/check_rm_consumer_native.cpp'}:
        return ['-I', str(RUNTIME / 'upstream/consumer/include')]
    return []


def source_warning_flags(source: Path) -> list[str]:
    # Apply the narrow exception after -Wextra/-Werror. Clang otherwise
    # re-enables the warning through the later umbrella warning option.
    # The original release-profile validity functions and type-safety header
    # templates accept unused container parameters; their bodies remain
    # unchanged. Only translation units that include this container closure
    # receive the exception.
    if source in {RUNTIME / 'upstream/consumer/vector.c',
                  RUNTIME / 'upstream/consumer/list.c',
                  RUNTIME / 'src/S540NvidiaRmConsumer.cpp',
                  RUNTIME / 'tests/check_rm_consumer_native.cpp'}:
        return ['-Wno-unused-parameter']
    return []


def compile_native_harness(work: Path, label: str, harness: Path,
                           sanitizer: list[str], *, with_runtime: bool = False) -> Path:
    cpp_sources, c_sources = production_sources() if with_runtime else adapter_sources()
    common = native_flags()
    objects = []
    for source in c_sources:
        obj = work / (label + '-' + source.stem + '.o')
        run('/usr/bin/xcrun', 'clang', *source_flags(source), *common,
            *source_warning_flags(source),
            '-std=gnu11', '-ffreestanding', *sanitizer,
            '-c', str(source), '-o', str(obj))
        objects.append(str(obj))
    for source in cpp_sources:
        obj = work / (label + '-' + source.stem + '.o')
        run('/usr/bin/xcrun', 'clang++', *source_flags(source), *common,
            *source_warning_flags(source),
            '-std=c++17', *sanitizer, '-pthread', '-c', str(source), '-o', str(obj))
        objects.append(str(obj))
    binary = work / ('check-' + label)
    run('/usr/bin/xcrun', 'clang++', *source_flags(harness), *common,
        *source_warning_flags(harness),
        '-std=c++17', *sanitizer, '-pthread', str(harness), *objects,
        '-o', str(binary))
    return binary


def check_integrated_runtime(work: Path) -> dict:
    """Run the exact bounded startup entry point used by the kernel probe."""
    results = {}
    for name, sanitizer in (('integrated-runtime', []),
                            ('integrated-runtime-sanitized',
                             ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                              '-fno-omit-frame-pointer'])):
        binary = compile_native_harness(
            work, name, LIFECYCLE / 'tests/check_lifecycle_native.cpp', sanitizer)
        result = native_check(binary)
        if (result.get('format') != 1
                or result.get('entrypoint') != 'S540NvidiaLifecycleRuntime::checkIntegrated'
                or result.get('reserve_cold_after') is not True
                or result.get('component') != 'nvport-lifecycle-runtime'
                or result.get('checks') != 72
                or result.get('foundation_checks') != 23
                or result.get('caller_checks') != 35
                or result.get('failures') != 0
                or any(result.get(key) is not True for key in
                       ('lifecycle', 'tracked_allocation', 'owned_mutex', 'spinlocks',
                        'cleanup', 'acquired', 'foundations_passed', 'callers_passed'))):
            raise ValueError('The native integration did not exercise and release probe startup.')
        results[name] = result
    return results


def build(sdk: Path, output: Path, *, allow_legacy_probe: bool = False) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS build host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the build commit.')
    sdk = sdk.resolve(strict=True)
    if run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != SDK_COMMIT:
        raise ValueError('The kernel SDK does not match its pinned commit.')
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (PACKAGE + '.zip')
    sidecar = output / (archive.name + '.sha256')
    if archive.exists() or sidecar.exists():
        raise ValueError('The output already exists.')
    kernel_sources = [SOURCE / 'src/S540NvidiaPCIProbe.cpp', SOURCE / 'src/kmod_start.cpp']
    adapter_cpp, adapter_c = production_sources()
    # Preserve the entire adapter source subtree, including NVIDIA and LLVM
    # notices, exact upstream inputs, adaptation records, and test sources.
    source_inputs = [*sorted((ADAPTER / 'src').rglob('*')),
                     *sorted((ADAPTER / 'upstream').rglob('*')),
                     *sorted((ADAPTER / 'tests').rglob('*')),
                     *sorted((SOURCE / 'src').rglob('*')),
                     *sorted(CALLERS.rglob('*')),
                     *sorted(LIFECYCLE.rglob('*')),
                     *sorted(RUNTIME.rglob('*')),
                     ADAPTER / 'README.md',
                     ROOT / 'builders/build_nvidia_transport.py',
                     ROOT / 'builders/check_nvidia_foundations.py',
                     ROOT / 'builders/check_nvidia_callers.py',
                     ROOT / 'builders/check_nvidia_lifecycle.py',
                     ROOT / 'builders/check_nvidia_runtime.py',
                     ROOT / 'tests/test_nvidia_runtime_provenance.py',
                     ROOT / 'tests/test_nvidia_rm_consumer_provenance.py',
                     ROOT / 'tests/test_nvidia_lifecycle_provenance.py',
                     ROOT / 'tests/test_nvidia_caller_provenance.py',
                     ROOT / 'tests/test_nvidia_transport_kernel.py',
                     *(ROOT / ('tests/test_nvidia_' + name + '_provenance.py')
                       for name in ('clock', 'memory', 'atomic')),
                     SOURCE / 'Info.plist', SOURCE / 'CHECK-TRANSPORT.command',
                     SOURCE / 'README.md', SOURCE / 'LICENSE']
    source_inputs = [item for item in source_inputs
                     if item.is_file() and '__pycache__' not in item.parts
                     and item.suffix != '.pyc']
    required = [*kernel_sources, *adapter_cpp, *adapter_c, *source_inputs,
                SOURCE / 'src/S540NvidiaPCIProbe.hpp',
                SOURCE / 'src/check_nvidia_transport.c', SOURCE / 'Info.plist',
                SOURCE / 'CHECK-TRANSPORT.command', SOURCE / 'README.md',
                SOURCE / 'LICENSE', sdk / 'LICENSE.txt', sdk / 'Library/x86_64/libkmod.a']
    for item in required:
        plain(item)
    info = plistlib.loads((SOURCE / 'Info.plist').read_bytes())
    if (info.get('CFBundleExecutable') != EXECUTABLE
            or any(info.get(key) != VERSION for key in
                   ('CFBundleVersion', 'CFBundleShortVersionString', 'OSBundleCompatibleVersion'))):
        raise ValueError('The kernel bundle version or executable is inconsistent.')
    if info.get('OSBundleLibraries') != KPI_LIBRARIES:
        raise ValueError('The pinned kernel KPI dependency mapping changed.')
    module_source = (SOURCE / 'src/kmod_start.cpp').read_text(encoding='utf-8')
    module_declarations = re.findall(
        r'^\s*KMOD_EXPLICIT_DECL\(\s*([A-Za-z0-9_.]+)\s*,\s*"([^"]+)"\s*,'
        r'\s*_start\s*,\s*_stop\s*\)\s*$', module_source, re.M)
    if module_declarations != [(info.get('CFBundleIdentifier'), VERSION)]:
        raise ValueError('The kernel module declaration identity or version differs from Info.plist.')
    with tempfile.TemporaryDirectory(prefix='s540-nvidia-transport-', dir=output) as temporary:
        work = Path(temporary)
        bundle = work / BUNDLE
        (bundle / 'Contents/MacOS').mkdir(parents=True)
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info, sort_keys=False))
        foundation_output = work / 'foundation-checks'
        foundations = run(sys.executable, str(ROOT / 'builders/check_nvidia_foundations.py'),
                          '--kernel-sdk', str(sdk), '--output-dir', str(foundation_output))
        print(foundations.stdout.strip())
        foundation_record = json.loads((foundation_output / 'foundation-checks.json').read_text())
        if foundation_record.get('status') != 'passed' or foundation_record.get('github_sha') != commit:
            raise ValueError('The foundational native checks do not match this source revision.')
        caller_output = work / 'caller-checks'
        caller_checks = run(sys.executable, str(ROOT / 'builders/check_nvidia_callers.py'),
                            '--kernel-sdk', str(sdk), '--output-dir', str(caller_output))
        print(caller_checks.stdout.strip())
        caller_record = json.loads((caller_output / 'caller-checks.json').read_text())
        if (caller_record.get('status') != 'passed'
                or caller_record.get('github_sha') != commit):
            raise ValueError('The real NVIDIA caller checks do not match this source revision.')
        lifecycle_output = work / 'lifecycle-checks'
        lifecycle_checks = run(sys.executable, str(ROOT / 'builders/check_nvidia_lifecycle.py'),
                               '--kernel-sdk', str(sdk), '--output-dir', str(lifecycle_output))
        print(lifecycle_checks.stdout.strip())
        lifecycle_record = json.loads((lifecycle_output / 'lifecycle-checks.json').read_text())
        if (lifecycle_record.get('status') != 'passed'
                or lifecycle_record.get('github_sha') != commit):
            raise ValueError('The NVIDIA lifecycle checks do not match this source revision.')
        native_results = check_integrated_runtime(work)
        runtime_output = work / 'runtime-checks'
        runtime_checks = run(sys.executable, str(ROOT / 'builders/check_nvidia_runtime.py'),
                             '--kernel-sdk', str(sdk), '--output-dir', str(runtime_output))
        print(runtime_checks.stdout.strip())
        runtime_record = json.loads((runtime_output / 'runtime-checks.json').read_text())
        if (runtime_record.get('status') != 'passed'
                or runtime_record.get('github_sha') != commit):
            raise ValueError('The NVIDIA runtime/RM checks do not match this source revision.')
        flags = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-mkernel',
                 '-fno-builtin', '-ffreestanding', '-fno-common', '-fno-stack-protector',
                 '-fno-asynchronous-unwind-tables', '-fno-unwind-tables',
                 '-mno-red-zone', '-DKERNEL', '-D__KERNEL__', '-O2',
                 '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
                 '-nostdinc', '-isystem', str(sdk / 'Headers'),
                 '-I', str(SOURCE / 'src'), '-I', str(ADAPTER / 'src'),
                 '-I', str(ADAPTER / 'upstream/include'), '-I', str(CALLERS / 'src'),
                 '-I', str(LIFECYCLE / 'src'), '-I', str(LIFECYCLE / 'upstream'),
                 '-I', str(RUNTIME / 'src'), '-I', str(RUNTIME / 'upstream'),
                 '-I', str(RUNTIME / 'upstream/consumer/include')]
        cpp_flags = ['-fapple-kext', '-fno-exceptions', '-fno-rtti',
                     '-fno-threadsafe-statics', '-nostdinc++', '-std=c++17']
        objects, adapter_objects = [], []
        for source in [*kernel_sources, *adapter_cpp, *adapter_c]:
            obj = work / (source.stem + '.o')
            compiler = 'clang' if source.suffix == '.c' else 'clang++'
            language_flags = ['-std=gnu11'] if source.suffix == '.c' else cpp_flags
            run('/usr/bin/xcrun', compiler, *source_flags(source), *flags,
                *source_warning_flags(source), *language_flags,
                '-c', str(source), '-o', str(obj))
            macho(obj, 1)
            objects.append(str(obj))
            if source in adapter_cpp or source in adapter_c:
                adapter_objects.append(str(obj))
        linked_adapter = work / 'integrated-adapter.o'
        run('/usr/bin/xcrun', 'ld', '-r', '-arch', 'x86_64', *adapter_objects,
            '-o', str(linked_adapter))
        macho(linked_adapter, 1)
        adapter_imports = set(run('/usr/bin/nm', '-u', '-j', str(linked_adapter)).stdout.split())
        if adapter_imports != ADAPTER_IMPORTS:
            unexpected = adapter_imports - ADAPTER_IMPORTS
            import_origins = {}
            # Diagnose only the rejected imports, without relaxing the exact
            # combined import contract or adding work to successful builds.
            for obj in adapter_objects:
                imported = set(run('/usr/bin/nm', '-u', '-j', obj).stdout.split())
                for symbol in sorted(unexpected & imported):
                    import_origins.setdefault(symbol, []).append(Path(obj).name)
            raise ValueError('Integrated kernel imports differ: missing='
                             + str(sorted(ADAPTER_IMPORTS - adapter_imports))
                             + ', unexpected=' + str(sorted(unexpected))
                             + ', importing_objects=' + str(import_origins))
        defined = run('/usr/bin/nm', '-g', str(linked_adapter)).stdout
        for symbol in CALLER_SYMBOLS:
            if not re.search(r'\bT _' + re.escape(symbol) + r'$', defined, re.M):
                raise ValueError('An actual NVIDIA caller or OS hook is missing: ' + symbol)
        for symbol in [*RUNTIME_SYMBOLS, *CONSUMER_SYMBOLS]:
            if not re.search(r'\bT _' + re.escape(symbol) + r'$', defined, re.M):
                raise ValueError('An actual NVIDIA runtime/RM symbol is missing: ' + symbol)
        for symbol in [*CALLER_DATA_SYMBOLS, *RUNTIME_DATA_SYMBOLS]:
            if not re.search(r'\b[SDsd] _' + re.escape(symbol) + r'$', defined, re.M):
                raise ValueError('An original NVIDIA runtime data symbol is missing: ' + symbol)
        for symbol in FORBIDDEN_RUNTIME_SYMBOLS:
            if re.search(r'\b[TSDBtsdb] _' + re.escape(symbol) + r'$', defined, re.M):
                raise ValueError('An excluded NVIDIA runtime entry is linked: ' + symbol)
        sections = run('/usr/bin/otool', '-l', str(linked_adapter)).stdout
        if '__mod_init_func' in sections or '__mod_term_func' in sections:
            raise ValueError('The integrated adapter gained static initialization.')
        binary = bundle / 'Contents/MacOS' / EXECUTABLE
        run('/usr/bin/xcrun', 'clang++', '-arch', 'x86_64',
            '-mmacosx-version-min=15.0', '-mkernel', '-nostdlib',
            '-Wl,-kext', '-Wl,-no_source_version', *objects,
            str(sdk / 'Library/x86_64/libkmod.a'), '-o', str(binary))
        macho(binary, 11)
        # The linker localizes hidden _realmain/_antimain pointers. They must
        # remain defined data symbols, but need not be external exports.
        symbols = run('/usr/bin/nm', '-a', str(binary)).stdout
        for symbol in ('_kmod_info', '__realmain', '__antimain'):
            if not re.search(r'\b[SDsd] ' + re.escape(symbol) + r'$', symbols, re.M):
                raise ValueError('The kext entry metadata is missing: ' + symbol)
        for symbol in ('__start', '__stop'):
            if not re.search(r'\b[Tt] ' + re.escape(symbol) + r'$', symbols, re.M):
                raise ValueError('The module runtime entry is missing: ' + symbol)
        if b'S540NvidiaPCIProbeSnapshot' not in binary.read_bytes():
            raise ValueError('The kernel snapshot marker is absent.')
        if b'Source available under APSL 2.0:' not in binary.read_bytes():
            raise ValueError('The linked module runtime source notice is absent.')
        run('/usr/bin/codesign', '--force', '--sign', '-', str(bundle))
        run('/usr/bin/codesign', '--verify', '--strict', str(bundle))
        checker = work / 'check-nvidia-transport'
        run('/usr/bin/xcrun', 'clang', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
            '-O2', '-fstack-protector-strong', '-arch', 'x86_64',
            '-mmacosx-version-min=15.0', '-framework', 'IOKit', '-framework', 'CoreFoundation',
            str(SOURCE / 'src/check_nvidia_transport.c'), '-o', str(checker))
        macho(checker, 2)
        run('/usr/bin/codesign', '--force', '--sign', '-', str(checker))
        run('/usr/bin/codesign', '--verify', '--strict', str(checker))
        self_test = run(str(checker), '--self-test')
        print(self_test.stdout.strip())
        live = json.loads(run(str(checker)).stdout)
        allowed_statuses = {'not_attached'}
        if allow_legacy_probe:
            allowed_statuses.add('outdated_probe')
        if (live.get('format') != 7 or live.get('tool') != 'nvidia-transport'
                or live.get('version') != VERSION or live.get('complete') is not True
                or live.get('status') not in allowed_statuses):
            raise ValueError('The native reporter returned an unexpected report or loaded probe.')
        live_validation = ('native live enumeration without a loaded probe'
                           if live['status'] == 'not_attached' else
                           'native live recognition of an already-loaded earlier probe; '
                           'the new kernel probe was not loaded by this build')
        imports = run('/usr/bin/nm', '-u', str(checker)).stdout
        if any(name in imports for name in ('IOServiceOpen', 'IOConnectCall', 'IOConnectMapMemory', 'IORegistryEntrySetCFProperty', 'IORegistryEntrySetCFProperties')):
            raise ValueError('The reporter imports a hardware-client or write API.')
        launcher = (SOURCE / 'CHECK-TRANSPORT.command').read_text()
        placeholder = 'NVIDIA_TRANSPORT_BINARY_SHA_PENDING'
        if launcher.count(placeholder) != 1:
            raise ValueError('The report executable checksum placeholder is not unique.')
        payload = {
            'bin/check-nvidia-transport': checker.read_bytes(),
            'CHECK-TRANSPORT.command': launcher.replace(placeholder, digest(checker.read_bytes())).encode(),
            'README.md': (SOURCE / 'README.md').read_bytes(),
            'LICENSE': (SOURCE / 'LICENSE').read_bytes(),
            'licenses/MacKernelSDK-APSL-2.0.txt': (sdk / 'LICENSE.txt').read_bytes(),
            'licenses/LLVM-LICENSE.txt': (ADAPTER / 'upstream/LLVM-LICENSE.txt').read_bytes(),
            'validation/foundation-checks.json': (foundation_output / 'foundation-checks.json').read_bytes(),
            'validation/caller-checks.json': (caller_output / 'caller-checks.json').read_bytes(),
            'validation/lifecycle-checks.json': (lifecycle_output / 'lifecycle-checks.json').read_bytes(),
            'validation/runtime-checks.json': (runtime_output / 'runtime-checks.json').read_bytes(),
            'THIRD-PARTY-NOTICES.txt': (
                'The unmodified kernel module runtime is from MacKernelSDK.\n'
                'Portions Copyright (c) 2000, 2008-2012 Apple Inc. All rights reserved.\n'
                'Source code is available under the Apple Public Source License 2.0 at:\n'
                'https://github.com/acidanthera/MacKernelSDK/tree/' + SDK_COMMIT + '/Library/kmod\n'
                'The corresponding license is included in licenses/MacKernelSDK-APSL-2.0.txt.\n\n'
                'NVIDIA CPU-side types, atomic headers and adapted NVPort memory, time,\n'
                'tracked and untracked allocator, mutex and spinlock callers\n'
                'are from NVIDIA/open-gpu-kernel-modules at commit\n'
                '1a82fbfda8f321b056eb3568850f9316c5e465c5, under MIT. Their complete\n'
                'copyright and license notices are retained in every applicable source file.\n'
                'Corresponding source, original reference inputs, and precise adaptation\n'
                'provenance are included under source/packages/nvidia-os-adapter/ and\n'
                'source/packages/nvidia-caller-integration/ and\n'
                'source/packages/nvidia-nvport-lifecycle/ and\n'
                'source/packages/nvidia-nvport-runtime/.\n'
                'The pinned atomic header closure includes LLVM-derived declarations;\n'
                'licenses/LLVM-LICENSE.txt supplies the accompanying license.\n'
                'Project-authored adapters and probe source use the MIT license in LICENSE.\n').encode(),
            'Kernel-Add-entry.plist': plistlib.dumps({
                'Arch': 'x86_64', 'BundlePath': BUNDLE,
                'Comment': 'S540 NVIDIA integrated OS adapter and TU117 identification', 'Enabled': True,
                'ExecutablePath': 'Contents/MacOS/' + EXECUTABLE,
                'MaxKernel': '25.99.99', 'MinKernel': '25.0.0',
                'PlistPath': 'Contents/Info.plist'}, sort_keys=False),
        }
        for item in source_inputs:
            payload['source/' + item.relative_to(ROOT).as_posix()] = item.read_bytes()
        for item in sorted(bundle.rglob('*')):
            if item.is_symlink():
                raise ValueError('The signed bundle contains a symbolic link.')
            if item.is_file():
                payload[BUNDLE + '/' + item.relative_to(bundle).as_posix()] = item.read_bytes()
        record = {'format': 1, 'package': PACKAGE, 'version': VERSION,
                  'github_sha': commit, 'architecture': 'x86_64',
                  'kernel_module_version': VERSION,
                  'kernel_sdk_repository': 'acidanthera/MacKernelSDK', 'kernel_sdk_commit': SDK_COMMIT,
                  'target': {'vendor_id': '0x10de', 'device_id': '0x1f91',
                             'subsystem_vendor_id': '0x17aa', 'subsystem_device_id': '0x3806'},
                  'source_sha256': {item.relative_to(ROOT).as_posix(): digest(item.read_bytes())
                                    for item in required if item.is_relative_to(ROOT)},
                  'native_report_status': live['status'],
                  'native_adapter_checks': native_results,
                  'native_runtime_checks': runtime_record['native_execution'],
                  'kernel_adapter_imports': sorted(adapter_imports),
                  'kernel_compiler_helpers': {
                      '___bzero': {
                          'purpose': 'compiler-emitted ordinary-RAM byte zeroing',
                          'kpi': 'com.apple.kpi.libkern',
                          'xnu_commit': 'f6217f891ac0bb64f3d375211650a4c1ff8ca1ea',
                          'export_reference': 'config/Libkern.exports',
                          'implementation_reference': 'osfmk/x86_64/bzero.s',
                      }},
                  'kernel_lifecycle_diagnostics': {
                      'imports': ['_IOLog', '_vsnprintf'],
                      'xnu_commit': 'f6217f891ac0bb64f3d375211650a4c1ff8ca1ea',
                      'export_references': ['config/IOKit.exports', 'config/Libkern.exports'],
                      'profile': 'bounded ordinary-thread formatting; startup cleanup remains silent',
                      'buffer_bytes': 512,
                  },
                  'kernel_adapter_resolved_caller_symbols': list(CALLER_SYMBOLS),
                  'kernel_adapter_resolved_caller_data': list(CALLER_DATA_SYMBOLS),
                  'kernel_adapter_resolved_runtime_symbols': list(RUNTIME_SYMBOLS),
                  'kernel_adapter_resolved_runtime_data': list(RUNTIME_DATA_SYMBOLS),
                  'kernel_adapter_resolved_rm_consumer_symbols': list(CONSUMER_SYMBOLS),
                  'kernel_adapter_excluded_runtime_entries': list(FORBIDDEN_RUNTIME_SYMBOLS),
                  'kernel_kpi_libraries': KPI_LIBRARIES,
                  'kernel_adapter_static_initializers': False,
                  'kernel_adapter_object_sha256': digest(linked_adapter.read_bytes()),
                  'package_file_sha256_excluding_BUILD': {name: digest(data) for name, data in payload.items()},
                  'validation': ['targeted native memory, timer and C/C++ atomic foundational checks',
                                 'pinned provenance of original NVIDIA tracked/untracked allocation and owned synchronization callers',
                                 'native bounded reserve allocation, exhaustion, reuse and failure checks',
                                 'native original mutex caller contention and mandatory assertion checks',
                                 'native lifecycle reserve exhaustion, allocation rollback and tracked concurrent use',
                                 'native spinlock exclusion, simulated interrupt-state restoration and fatal misuse checks',
                                 'checked NvPort core lifecycle, original string/PRNG utility bodies and real RM container consumer',
                                 'native runtime failure rollback, shared-lease contention and complete cold cleanup',
                                 'same bounded startup entry point as probe, with reserve lifecycle cleanup',
                                 'address and undefined-behavior sanitizers with fatal recovery policy',
                                 'native Intel kernel compile and link with adapter import allowlist',
                                 'thin x86_64 Mach-O and module entry metadata',
                                 'ad-hoc signature verification', 'native report decoder self-test',
                                 live_validation],
                  'hardware_status': 'Version 0.6.0 is confirmed on the laptop: 72 lifecycle checks, 35 caller/reserve checks, 23 foundation checks and two-read TU117 identification. Version 0.7.0 adds the checked core, string/PRNG utilities and a real CPU-side RM container consumer. Execution of this new combined kernel startup is not established by this CI build. The complete NVPort profile, NVIDIA HAL and GPU resource manager are not instantiated. GPU initialization, firmware, DMA and acceleration remain unimplemented.'}
        payload['BUILD.json'] = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
        payload['SHA256SUMS'] = ''.join(digest(data) + '  ' + name + '\n' for name, data in sorted(payload.items())).encode('ascii')
        pending = work / archive.name
        with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle_zip:
            for name, data in sorted(payload.items()):
                entry = zipfile.ZipInfo(PACKAGE + '/' + name, (2026, 10, 15, 0, 0, 0))
                entry.create_system = 3
                executable = name.endswith('.command') or name.startswith('bin/') or name.endswith('/MacOS/' + EXECUTABLE)
                entry.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                bundle_zip.writestr(entry, data)
        with zipfile.ZipFile(pending) as bundle_zip:
            if bundle_zip.testzip() is not None or len(bundle_zip.namelist()) != len(payload):
                raise ValueError('The package archive failed verification.')
        os.replace(pending, archive)
    sidecar.write_text(digest(archive.read_bytes()) + '  ' + archive.name + '\n', encoding='ascii')
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-sdk', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--allow-legacy-probe', action='store_true',
                        help='Allow an already-loaded earlier probe during a local build.')
    args = parser.parse_args()
    try:
        archive = build(args.kernel_sdk, args.output_dir,
                        allow_legacy_probe=args.allow_legacy_probe)
        print('Verified integrated NVIDIA OS-adapter package: ' + str(archive))
        print('ZIP SHA256: ' + digest(archive.read_bytes()))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print('NVIDIA transport package not created: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-6000:], file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stdout:
            print(error.stdout[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
