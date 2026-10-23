#!/usr/bin/env python3
"""Execute the unchanged real client against explicit fake IOKit/CF/sysctl APIs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent
FRONT = HERE.parent
CF = r'''#ifndef S540_FAKE_CF_H
#define S540_FAKE_CF_H
#include <stdint.h>
typedef const void *CFTypeRef;
typedef const void *CFStringRef;
typedef const void *CFDataRef;
typedef const void *CFAllocatorRef;
typedef const void *CFDictionaryRef;
typedef void *CFMutableDictionaryRef;
typedef unsigned long CFTypeID;
typedef long CFIndex;
typedef unsigned long CFStringEncoding;
typedef unsigned char UInt8;
#define kCFAllocatorDefault ((CFAllocatorRef)0)
#define kCFStringEncodingUTF8 0U
CFStringRef CFStringCreateWithCString(CFAllocatorRef,const char *,CFStringEncoding);
CFTypeID CFGetTypeID(CFTypeRef);
CFTypeID CFDataGetTypeID(void);
CFIndex CFDataGetLength(CFDataRef);
const UInt8 *CFDataGetBytePtr(CFDataRef);
void CFRelease(CFTypeRef);
#endif
'''
IOKIT = r'''#ifndef S540_FAKE_IOKIT_H
#define S540_FAKE_IOKIT_H
#include <stdint.h>
#include <stddef.h>
#include <CoreFoundation/CoreFoundation.h>
typedef unsigned int mach_port_t;
typedef unsigned int task_port_t;
typedef unsigned int io_object_t;
typedef io_object_t io_service_t;
typedef io_object_t io_registry_entry_t;
typedef io_object_t io_iterator_t;
typedef io_object_t io_connect_t;
typedef int kern_return_t;
typedef int boolean_t;
#define KERN_SUCCESS 0
#define kIOReturnError ((kern_return_t)0xe00002bcU)
#define kIOReturnBadArgument ((kern_return_t)0xe00002c2U)
#define kIOReturnBusy ((kern_return_t)0xe00002d5U)
#define IO_OBJECT_NULL 0U
#define kIOMainPortDefault 0U
CFMutableDictionaryRef IOServiceMatching(const char *);
kern_return_t IOServiceGetMatchingServices(mach_port_t,CFDictionaryRef,io_iterator_t *);
io_service_t IOServiceGetMatchingService(mach_port_t,CFDictionaryRef);
boolean_t IOIteratorIsValid(io_iterator_t);
io_object_t IOIteratorNext(io_iterator_t);
CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t,CFStringRef,CFAllocatorRef,uint32_t);
kern_return_t IOObjectRelease(io_object_t);
kern_return_t IORegistryEntryGetRegistryEntryID(io_registry_entry_t,uint64_t *);
mach_port_t mach_task_self(void);
kern_return_t IOServiceOpen(io_service_t,task_port_t,uint32_t,io_connect_t *);
kern_return_t IOServiceClose(io_connect_t);
kern_return_t IOConnectCallStructMethod(io_connect_t,uint32_t,const void *,size_t,void *,size_t *);
#endif
'''
SYSCTL = r'''#ifndef S540_FAKE_SYSCTL_H
#define S540_FAKE_SYSCTL_H
#include <stddef.h>
int sysctlbyname(const char *,void *,size_t *,const void *,size_t);
#endif
'''


def sha(path):
    path = Path(path)
    if path.is_symlink(): raise ValueError('Fake API control source symlink refused')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command, log, environment, expected=0):
    result = subprocess.run([str(value) for value in command], text=True, capture_output=True,
        timeout=180, env=environment)
    log.write_text(result.stdout + result.stderr)
    if result.returncode != expected:
        raise ValueError('Actual client fake API control failed: ' + str(log) + '\n' + result.stderr[-5000:])
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    fixture = next((row for row in lines if 'fixture_case' in row), None)
    if fixture is None: raise ValueError('Actual client fixture observation is missing')
    return fixture, [row for row in lines if 'fixture_case' not in row]


def run(args):
    output = args.output.resolve(); cc = args.cc.resolve(strict=True)
    if output.exists() or output.is_relative_to(FRONT): raise ValueError('Fresh isolated client controls output required')
    paths = [Path(__file__), HERE / 'check_client.c', FRONT / 'experimental_ctl.c',
        FRONT / 'S540ExperimentalTargetProtocol.h', FRONT.parent.parent / 'nvidia-os-adapter/upstream/include/nvtypes.h',
        FRONT.parent.parent / 'nvidia-os-adapter/upstream/include/nvstatus.h']
    bindings = {str(path): sha(path) for path in paths}; compiler = sha(cc)
    output.mkdir(parents=True)
    fake = output / 'fake'
    for name, text in {'CoreFoundation/CoreFoundation.h': CF, 'IOKit/IOKitLib.h': IOKIT, 'sys/sysctl.h': SYSCTL}.items():
        path = fake / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    report = dict(format=1, status='running', source_sha256=bindings, compiler_sha256=compiler,
        fake_header_sha256={str(path.relative_to(fake)): sha(path) for path in fake.rglob('*.h')},
        endpoint_scope='explicit CPU-only fake IOKit/CoreFoundation/sysctl/privilege calls; actual client unchanged',
        actual_native_iokit_used=False, native_darwin_execution=False, module_loaded=False, gpu_initialization_tested=False,
        variants={})
    def write(): (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    write()
    try:
        for variant in args.variants:
            work = output / variant; work.mkdir()
            flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                '-Wno-unused-parameter', '-I', str(fake), '-I', str(FRONT)]
            if variant == 'sanitized': flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
            binary = work / 'actual-client-fixture'
            command = [cc, *flags, HERE / 'check_client.c', '-o', binary]
            raw = subprocess.run([str(value) for value in command], text=True, capture_output=True, timeout=180)
            (work / 'compile.log').write_text(raw.stdout + raw.stderr)
            if raw.returncode: raise ValueError('Actual client fixture compilation failed: ' + raw.stderr[-7000:])
            rows = []
            for case in range(49):
                fixture, observations = execute([binary, case], work / ('case-%02d.log' % case), environment)
                if fixture['failures']: raise ValueError('Actual client fixture assertions failed')
                if case in (0, 1, 2, 3, 4, 5, 29, 40, 44, 45, 46):
                    if len(observations) != 1: raise ValueError('Actual client JSON report missing')
                    row = observations[0]
                    if row['request_rpc_attempted'] != (case not in (3,44,45,46)):
                        raise ValueError('Client JSON conflates run/snapshot/stop routes')
                    if case in (2,45) and row['stop_rpc_status'] != 0xe00002d5:
                        raise ValueError('Client JSON erased the actual STOP RPC failure')
                    if case in (29,46) and row['snapshot_rpc_status'] != 0xe00002bc:
                        raise ValueError('Client JSON erased the failed post-call observation')
                    if case == 1 and row['request_rpc_status'] != 0xe00002bc:
                        raise ValueError('Client JSON erased REQUEST RPC failure')
                rows.append(dict(**fixture, client_json=observations))
            negative = []
            original = (FRONT / 'experimental_ctl.c').read_text()
            for label, before, after, case in (
                ('skip-stop-after-request-error',
                 'stopped=IOConnectCallStructMethod(connection,S540_EXPERIMENTAL_SELECTOR_STOP,NULL,0,&output,&bytes);',
                 'stopped=KERN_SUCCESS;', 1),
                ('ignore-native-code-identity', '!memcmp(observed->nativeCodeContractSha256,expectedNative,32)', '1', 18),
                ('accept-duplicate-target', 'valid && matches==1 ? 0:1', 'matches>=1 ? 0:1', 32)):
                if before not in original: raise ValueError('Client negative control source anchor changed: ' + label)
                mutant_source = work / (label + '.c'); mutant_source.write_text(original.replace(before, after, 1))
                mutant = work / label
                mutant_command = [cc, *flags, '-DS540_CLIENT_SOURCE="' + str(mutant_source) + '"', HERE / 'check_client.c', '-o', mutant]
                compiled = subprocess.run([str(value) for value in mutant_command], text=True, capture_output=True, timeout=180)
                (work / (label + '-compile.log')).write_text(compiled.stdout + compiled.stderr)
                if compiled.returncode: raise ValueError('Client negative control did not compile: ' + compiled.stderr[-3000:])
                fixture, observations = execute([mutant, case], work / (label + '.log'), environment, expected=1)
                if not fixture['failures']: raise ValueError('Actual client negative source mutation escaped')
                negative.append(dict(label=label, failures_detected=fixture['failures'], binary_sha256=sha(mutant), source_sha256=sha(mutant_source)))
            report['variants'][variant] = dict(status='passed', command=[str(value) for value in command],
                binary_sha256=sha(binary), observations=rows, checks=sum(row['checks'] for row in rows), negative_controls=negative)
            write()
        if sha(cc) != compiler or any(sha(path) != expected for path, expected in bindings.items()):
            raise ValueError('Actual client source/helper/compiler changed during controls')
        report['status'] = 'passed-actual-client-fake-api-controls'
        return report
    except Exception as error: report.update(status='failed', error=str(error)); raise
    finally: write()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variants', nargs='+', choices=('plain', 'sanitized'), default=['plain', 'sanitized'])
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'checks': {name: row['checks'] for name, row in result['variants'].items()}}))
