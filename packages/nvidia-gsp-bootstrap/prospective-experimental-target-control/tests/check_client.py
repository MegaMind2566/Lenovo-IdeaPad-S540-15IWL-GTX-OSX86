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
PREPARATION = FRONT.parent / 'prospective-preparation-observation'
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


def check_diagnostics(case, fixture, row):
    checks = 0
    def check(value, message):
        nonlocal checks
        checks += 1
        if not value: raise ValueError('Client diagnostic case %u: %s' % (case, message))
    outer_valid = case not in (29, 46, 64, 65, 84, 85)
    check(row['snapshot_valid'] is outer_valid, 'outer RPC validity was erased')
    expected_format = 1 if case == 64 else (0 if case in (29, 46) else (2 if case == 84 else 3))
    expected_bytes = 0 if case in (29, 46) else fixture['expected_snapshot_bytes'] - (case == 65)
    check(row['snapshot_format'] == expected_format, 'snapshot version was not preserved')
    check(row['snapshot_bytes'] == expected_bytes,
        'snapshot byte size was not preserved')
    p = row['preparation']
    valid = outer_valid and 49 <= case <= 66 and case not in (53, 54, 55)
    check(p['valid'] is valid, 'unknown or malformed preparation was labeled valid')
    if not valid or case == 66:
        for key in ('stage_valid', 'last_completed_valid', 'last_status_valid', 'first_failure_observed',
                    'first_failure_valid', 'host_facts_valid', 'device_facts_valid'):
            check(p[key] is False, 'invalid preparation granted ' + key)
        for fact in p['host_facts'].values():
            check(fact == {'known': None, 'missing': None}, 'unknown host fact became a boolean')
        for predicate in p['device_predicates'].values():
            check(predicate == {'observed': False, 'satisfied': None}, 'unknown device predicate became satisfied')
        if case == 66:
            check(p['format'] == 1 and p['bytes'] == 104 and p['observed_mask'] == 32,
                'unknown PM-mask fixture lost its independently valid preparation record')
    else:
        expected_stages = {50: (7, 'power-start'), 51: (9, 'host-facts'), 52: (10, 'device-facts'),
            56: (0xffffffff, 'unknown'), 58: (31, 'complete')}
        stage, label = expected_stages.get(case, (16, 'context-create'))
        check(p['format'] == 1 and p['bytes'] == 104, 'preparation nested ABI changed')
        check(p['stage'] == stage and p['stage_label'] == label, 'preparation stage or label changed')
        check(p['stage_valid'] is (case != 56), 'unknown stage acquired valid semantics')
        check(p['first_failure_observed'] is (case != 58), 'first-failure observation bit was erased')
        check(p['first_failure_valid'] is (case not in (56, 58)), 'first-failure validity changed')
        check(p['last_status_valid'] is True, 'observed preparation status was lost')
        check(p['first_failure_status'] == (0 if case == 58 else fixture['expected_preparation_failure']),
            'first failure status changed')
        if case != 58:
            check(p['first_failure_stage'] == stage and p['first_failure_stage_label'] == label,
                'first failure stage changed')
        if 49 <= case <= 52:
            check(row['preparation_attempted'] == 1 and row['preparation_returned'] == 1 and
                row['preparation_status'] == fixture['expected_preparation_failure'], 'prepare return facts changed')
            check(row['retained_stop']['cleanup_complete'] == 1 and row['stop_status'] == 0,
                'fixture did not reach the post-cleanup observation')
            check(row['initialization_attempted'] == 0 and row['original_entry_observed'] == 0,
                'prepare failure invented original entry')
            check(row['retained_until_reboot'] == 1, 'cleanup diagnostics invented unload permission')
        host_valid = case not in (50, 59)
        device_valid = case not in (50, 51, 59)
        check(p['host_facts_valid'] is host_valid and p['device_facts_valid'] is device_valid,
            'host/device observation masks changed')
        if case == 51:
            check(p['host_known_mask'] == 0x1f and p['host_missing_mask'] == 0x20,
                'host missing/known masks changed')
            check(p['host_facts']['s0ix'] == {'known': False, 'missing': True}, 'missing S0ix fact was hidden')
        if not host_valid:
            for fact in p['host_facts'].values():
                check(fact == {'known': None, 'missing': None}, 'unobserved nonzero host mask granted knowledge')
        if not device_valid:
            for predicate in p['device_predicates'].values():
                check(predicate == {'observed': False, 'satisfied': None}, 'unobserved device bits granted predicates')
        if case == 52:
            check(p['device_observed_mask'] == 127 and p['device_predicates_mask'] == 123 and
                p['device_predicates']['bars'] == {'observed': True, 'satisfied': False}, 'failed BAR predicate erased')
        if case == 62:
            check(p['device_observed_mask'] == 2 and p['device_predicates_mask'] == 127,
                'partial device observation mask changed')
            check(p['device_predicates']['pci'] == {'observed': True, 'satisfied': True} and
                p['device_predicates']['bars'] == {'observed': False, 'satisfied': None},
                'unobserved positive predicate bits acquired authority')
        if case == 58:
            check(p['last_status'] == 0 and p['first_failure_stage'] == 0,
                'complete observation confused absence of failure with an observed failure')
    power = p['power']
    power_valid = valid and case not in (60, 61, 66)
    check(power['valid'] is power_valid, 'invalid PM nested observation was labeled valid')
    if not power_valid:
        for key in ('stage_valid', 'last_completed_valid', 'first_failure_valid', 'raw_io_return_valid',
                    'first_failure_raw_io_return_valid', 'wait_result_valid'):
            check(power[key] is False, 'invalid PM observation granted ' + key)
        for predicate in power['predicates'].values():
            check(predicate == {'observed': False, 'value': None}, 'unknown PM predicate became a boolean')
        check(all(value is None for value in power['protocol_flags'].values()), 'unknown PM flags became booleans')
        if case == 66:
            check(power['format'] == 1 and power['bytes'] == 56 and power['observed_mask'] == 0x80000000 and
                power['raw_io_return'] == 0, 'unknown-only PM mask or zero raw return was erased')
    elif case == 50:
        check(power['stage'] == power['first_failure_stage'] == 10 and
            power['stage_label'] == power['first_failure_stage_label'] == 'wait-domain', 'PM failure stage erased')
        check(power['first_failure_valid'] is True and
            power['first_failure_status'] == fixture['expected_preparation_failure'], 'PM first failure erased')
        check(power['raw_io_return'] == power['first_failure_raw_io_return'] == 0xe00002d8 and
            power['raw_io_return_valid'] is True and power['first_failure_raw_io_return_valid'] is True,
            'raw PM IOReturn failure was erased')
        check(power['wait_result'] == 7 and power['wait_result_valid'] is True, 'PM wait result erased')
        check(power['predicates']['ready'] == {'observed': True, 'value': True} and
            power['predicates']['domain'] == {'observed': True, 'value': False} and
            power['predicates']['active'] == {'observed': True, 'value': True}, 'PM predicates changed')
        check(power['protocol_flags']['on_requested'] is True and power['protocol_flags']['on_set'] is False,
            'observed PM protocol flags changed')
    else:
        check(power['stage'] == 12 and power['stage_label'] == 'complete' and power['stage_valid'] is True,
            'observed PM completion stage changed')
        check(power['first_failure_valid'] is False and power['raw_io_return'] == 0 and
            power['raw_io_return_valid'] is False and power['first_failure_raw_io_return_valid'] is False,
            'zero/unobserved raw PM returns were treated as observed success')
    return checks


def check_runtime_diagnostics(case, row):
    checks = 0
    def check(value, message):
        nonlocal checks
        checks += 1
        if not value: raise ValueError('Client runtime diagnostic case %u: %s' % (case, message))
    r = row['runtime']; q = row['irq_source']
    outer = case not in (29, 46, 64, 65, 84, 85)
    active = 67 <= case <= 86
    valid = outer and active and case not in (70, 71, 72, 73, 74, 75, 76)
    check(r['valid'] is valid, 'malformed, unavailable or raced runtime acquired validity')
    if not valid:
        check(all(call == {'attempted': None, 'returned': None, 'status': None}
                  for call in r['calls'].values()), 'unknown runtime call became an observed status')
        check(all(value is None for value in r['facts'].values()), 'unknown runtime fact became a boolean')
        check(r['global_original_status'] is None and not r['first_failure_valid'],
            'unknown runtime invented a global return or first failure')
    else:
        returned = 31 if case in (68, 69) else (7 if case == 77 else 15)
        attempted = 31 if case in (68, 69) else 15
        check(r['returned_mask'] == returned and r['attempted_mask'] == attempted,
            'attempted and returned masks changed')
        for name, bit in (('global', 1), ('context', 2), ('bind', 4), ('irq', 8), ('original_adapter', 16)):
            call = r['calls'][name]
            expected_status = (85 if case == 78 else 86) if name == 'irq' and case not in (68, 69, 77) else 0
            check(call == {'attempted': bool(attempted & bit), 'returned': bool(returned & bit),
                           'status': expected_status if returned & bit else None},
                  'call %s conflates a status sentinel with a genuine return' % name)
        check(r['facts']['global_initialized'] is True and r['facts']['global_original_returned'] is True and
              r['global_original_status'] == 0 and r['facts']['any_original_entry_observed'] is True,
              'successful original global call was lost')
        adapter = case in (68, 69)
        check(r['facts']['adapter_attempted'] is adapter and r['facts']['adapter_initialized'] is adapter and
              r['facts']['adapter_original_returned'] is adapter,
              'global entry was confused with adapter original entry')
        failed = case not in (68, 69, 77)
        check(r['first_failure_valid'] is failed, 'first failure validity changed')
        if failed:
            check(r['stage'] == 12 and r['stage_label'] == 'failed' and r['last_stage'] == 9 and
                  r['last_stage_label'] == 'irq' and r['first_failure_stage'] == 9 and
                  r['first_failure_stage_label'] == 'irq' and r['first_status'] == (85 if case == 78 else 86),
                  'FAILED stage erased first failed operation or original return status')
        if case == 77:
            check(r['stage_label'] == 'irq' and r['calls']['irq']['status'] is None,
                  'inflight status85 became a returned NV_ERR_NOT_READY')
        check(r['generation'] == 17 and r['observed_host_stack_bytes'] == 16384 and
              r['required_worker_stack_bytes'] == r['required_irq_stack_bytes'] == 16384,
              'runtime generation or actual stack records changed')
    route_valid = outer and active and case not in (79, 80, 81)
    check(q['valid'] is route_valid, 'malformed or incomplete IRQ probe was labeled returned')
    selected = route_valid and case in (68, 69)
    check(q['selection_valid'] is selected, 'IRQ diagnostic accepted missing/ambiguous MSI selection')
    if selected:
        check(q['selected_source'] == (1 if case == 68 else 0) and q['selected_interrupt_type'] == 0x10000,
              'selected source zero was confused with unknown or source1 was erased')
    else:
        check(q['selected_source'] is None and q['selected_interrupt_type'] is None,
              'unknown/refused/ambiguous source acquired an index or type')
    if route_valid:
        check(q['probe_attempted'] is True and q['probe_returned'] is True and
              q['probe_status'] == (0 if case in (68, 69, 82, 86) else 86), 'real IRQ probe return status changed')
        check(q['source_count'] == (1 if case == 69 else 2) and
              q['sources_observed'] == (1 if case == 69 else 2) and
              q['messaged_sources'] == (1 if case in (68, 69, 86) else (2 if case == 82 else 0)),
              'actual source/probe/MSI counts changed')
        check(q['inventory_valid'] is True and q['msi_capable'] is True and q['msix_capable'] is False and
              q['msi_vectors'] == 1, 'hardware MSI capability was confused with selected controller mode')
    else:
        check(q['probe_status'] is None and q['source_count'] is None and q['sources_observed'] is None and
              q['messaged_sources'] is None and q['inventory_valid'] is None and q['msi_capable'] is None and
              q['msix_capable'] is None and q['msi_vectors'] is None,
              'unknown IRQ probe created success, source count or capability facts')
        if case == 81:
            check(q['probe_attempted'] is True and q['probe_returned'] is False,
                  'an inflight probe was confused with unknown or returned')
    return checks


def run(args):
    output = args.output.resolve(); cc = args.cc.resolve(strict=True)
    if output.exists() or output.is_relative_to(FRONT): raise ValueError('Fresh isolated client controls output required')
    paths = [Path(__file__), HERE / 'check_client.c', FRONT / 'experimental_ctl.c',
        FRONT / 'S540ExperimentalTargetProtocol.h', PREPARATION / 'S540PreparationObservation.h',
        FRONT.parent.parent / 'nvidia-os-adapter/upstream/include/nvtypes.h',
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
                '-Wno-unused-parameter', '-Wno-misleading-indentation',
                '-I', str(fake), '-I', str(FRONT), '-I', str(PREPARATION)]
            if variant == 'sanitized': flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
            binary = work / 'actual-client-fixture'
            command = [cc, *flags, HERE / 'check_client.c', '-o', binary]
            raw = subprocess.run([str(value) for value in command], text=True, capture_output=True, timeout=180)
            (work / 'compile.log').write_text(raw.stdout + raw.stderr)
            if raw.returncode: raise ValueError('Actual client fixture compilation failed: ' + raw.stderr[-7000:])
            rows = []
            diagnostic_checks = 0
            for case in range(87):
                fixture, observations = execute([binary, case], work / ('case-%02d.log' % case), environment)
                if fixture['failures']: raise ValueError('Actual client fixture assertions failed')
                if case in (0, 1, 2, 3, 4, 5, 29, 40, 44, 45, 46) or (case >= 49 and case not in (63,83)):
                    if len(observations) != 1: raise ValueError('Actual client JSON report missing')
                    row = observations[0]
                    if row['request_rpc_attempted'] != bool(fixture['requests']):
                        raise ValueError('Client JSON conflates run/snapshot/stop routes')
                    if case in (2,45) and row['stop_rpc_status'] != 0xe00002d5:
                        raise ValueError('Client JSON erased the actual STOP RPC failure')
                    if case in (29,46,85) and row['snapshot_rpc_status'] != 0xe00002bc:
                        raise ValueError('Client JSON erased the failed post-call observation')
                    if case in (64,65,84) and row['snapshot_rpc_status'] != 0xe00002c2:
                        raise ValueError('Client JSON accepted malformed post-call snapshot ABI')
                    if (case == 1 or 49 <= case <= 52) and row['request_rpc_status'] != 0xe00002bc:
                        raise ValueError('Client JSON erased REQUEST RPC failure')
                    diagnostic_checks += check_diagnostics(case, fixture, row)
                    diagnostic_checks += check_runtime_diagnostics(case, row)
                rows.append(dict(**fixture, client_json=observations))
            negative = []
            original = (FRONT / 'experimental_ctl.c').read_text()
            for label, before, after, case in (
                ('skip-stop-after-request-error',
                 'stopped=IOConnectCallStructMethod(connection,S540_EXPERIMENTAL_SELECTOR_STOP,NULL,0,&output,&bytes);',
                 'stopped=KERN_SUCCESS;', 1),
                ('ignore-native-code-identity', '!memcmp(observed->nativeCodeContractSha256,expectedNative,32)', '1', 18),
                ('accept-duplicate-target', 'valid && matches==1 ? 0:1', 'matches>=1 ? 0:1', 32),
                ('accept-old-snapshot-version', 'out->format!=S540_EXPERIMENTAL_SNAPSHOT_VERSION', '0', 12),
                ('accept-mismatched-snapshot-metadata-bytes', 'out->bytes!=sizeof(*out)', '0', 63)):
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
            for label, before, after, case in (
                ('accept-malformed-preparation-format', 'snapshotValid && p->format==1', 'snapshotValid && 1', 54),
                ('zero-preparation-is-valid',
                 'int valid=snapshotValid && p->format==1 && p->bytes==sizeof(*p) && (p->observedMask&knownMask)!=0;',
                 'int valid=(snapshotValid && p->format==1 && p->bytes==sizeof(*p) && (p->observedMask&knownMask)!=0) || (snapshotValid && p->format==0);', 53),
                ('zero-raw-pm-return-is-valid', 'powerValid && power->rawIOReturnValid==1', 'powerValid', 57),
                ('unknown-only-pm-mask-is-valid', '(power->observedMask&powerKnownMask)!=0',
                 '((void)powerKnownMask,power->observedMask!=0)', 66),
                ('raced-runtime-is-valid', 'r->snapshotStatus==NV_OK && masksValid',
                 '((void)r->snapshotStatus,1) && masksValid', 71),
                ('attempted-runtime-status-is-returned', 'int returned=valid && (r->returnedMask&calls[i].bit);',
                 'int returned=valid && (r->attemptedMask&calls[i].bit);', 77),
                ('zero-source-is-unknown', 'r->selectedSource<r->sourceCount &&',
                 'r->selectedSource>0 && r->selectedSource<r->sourceCount &&', 69),
                ('ambiguous-message-source-is-selected', 'r->messagedSources==1 &&',
                 'r->messagedSources>0 &&', 82),
                ('non-message-type-is-selected', '(r->selectedInterruptType&0x00010000U)!=0 &&',
                 '', 86)):

                if original.count(before) != 1: raise ValueError('Diagnostic negative control anchor changed: ' + label)
                mutant_source = work / (label + '.c'); mutant_source.write_text(original.replace(before, after, 1))
                mutant = work / label
                mutant_command = [cc, *flags, '-DS540_CLIENT_SOURCE="' + str(mutant_source) + '"', HERE / 'check_client.c', '-o', mutant]
                compiled = subprocess.run([str(value) for value in mutant_command], text=True, capture_output=True, timeout=180)
                (work / (label + '-compile.log')).write_text(compiled.stdout + compiled.stderr)
                if compiled.returncode: raise ValueError('Diagnostic negative control did not compile: ' + compiled.stderr[-3000:])
                fixture, observations = execute([mutant, case], work / (label + '.log'), environment)
                if fixture['failures'] or len(observations) != 1: raise ValueError('Diagnostic negative control did not reach reporting')
                try:
                    check_diagnostics(case, fixture, observations[0])
                    check_runtime_diagnostics(case, observations[0])
                except ValueError as error: detected = str(error)
                else: raise ValueError('Diagnostic source mutation escaped: ' + label)
                negative.append(dict(label=label, diagnostic_assertion=detected,
                    binary_sha256=sha(mutant), source_sha256=sha(mutant_source)))
            report['variants'][variant] = dict(status='passed', command=[str(value) for value in command],
                binary_sha256=sha(binary), observations=rows, checks=sum(row['checks'] for row in rows),
                diagnostic_checks=diagnostic_checks, negative_controls=negative)
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
