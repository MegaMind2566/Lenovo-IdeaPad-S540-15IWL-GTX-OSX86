#!/usr/bin/env python3
"""Execute genuine cancellation and source-bound timer/IRQ/TX endpoint bodies."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as composer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def execute(argv, log, environment=None, expected=0):
    value = subprocess.run([str(x) for x in argv], text=True, capture_output=True,
        timeout=180, env=environment)
    log.write_text(value.stdout + value.stderr)
    if expected is not None and value.returncode != expected:
        raise ValueError('PM control failed: ' + str(log) + '\n' + value.stderr[-4000:])
    return value


def body(text, name, return_type):
    first, last = prepare.function_span(text, name)
    return return_type + ' ' + text[first:last] + '\n'


def tx_control(base, changed):
    source = (base / 'source' / prepare.TX).read_text()
    msgq = (base / 'source/src/nvidia/src/libraries/msgq/msgq.c').read_text()
    exact = ''.join(body(msgq, name, result) for name, result in (
        ('msgqTxGetFreeSpace', 'unsigned'), ('msgqTxGetWriteBuffer', 'void *'),
        ('msgqTxSubmitBuffers', 'int')))
    exact += body(source, 'GspMsgQueueSendCommand', 'NV_STATUS').replace(
        'GspMsgQueueSendCommand(', 's540TxUnmodifiedOriginal(', 1)
    exact += body(changed, 'GspMsgQueueSendCommand', 'NV_STATUS')
    fixture = (HERE.parent / 'prospective-session-lifetime-closure/tests/tx-control.c.inc').read_text()
    fixture = prepare.once(fixture,
        'expect(send(NV_FALSE)==NV_OK&&headWrites==1&&head==5&&memcmp(expectedRing,ringBytes,sizeof(ringBytes))==0,\n'
        '        "no matching cancellation binding preserves exact original queue publication and bytes");',
        'expect(send(NV_FALSE)==NV_ERR_INVALID_STATE&&headWrites==0&&head==3&&metadata.txWritePtr==3,\n'
        '        "unbound submit refuses before publishing actual queue metadata");')
    fixture = prepare.once(fixture,
        'expect(send(NV_FALSE)==NV_OK&&headWrites==1&&head==5,"foreign GPU identity retains original behavior rather than borrowing cancellation authority");',
        'expect(send(NV_FALSE)==NV_ERR_INVALID_STATE&&headWrites==0&&head==3,"foreign GPU identity cannot borrow bound commit authority");')
    fixture = prepare.once(fixture, 'int main(void){',
        'int main(void){\n    {S540GspCancellationCommitLease absent=8;\n'
        '    expect(s540GspCancellationSubmitEnterGpu(NULL,&absent)==NV_ERR_INVALID_ARGUMENT&&!absent,"NULL GPU refuses and clears output");\n'
        '    expect(s540GspCancellationCommitLeaveGpu(NULL,8)==NV_ERR_INVALID_ARGUMENT,"NULL GPU cannot release a commit");}\n')
    fixture = prepare.once(fixture,
        'if(scenario==7&&fences==2)expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,\n'
        '        "real revoke inside authentic submit before TX_HEAD commit");',
        'if(scenario==7&&fences==2){\n'
        '        S540GspCancellationCommitSnapshot observed={0};\n'
        '        expect(s540GspCancellationCommitReadState(&exactState,&observed)==NV_OK&&observed.inFlight,"authentic submit retains its accepted commit");\n'
        '        expect(s540GspCancellationFinish(token)==NV_ERR_IN_USE,"actual submit cannot finish while producer commit is live");\n'
        '        expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"real revoke inside accepted authentic submit");}\n')
    preamble = changed[:changed.index('static void _gspMsgQueueCleanup')]
    return preamble + '\n' + prepare.once(fixture, '/* EXACT_ACTUAL_BODIES */', exact)


def original_host_flags(base, project):
    path = base / 'project-compilation.json'
    if sha(path) != '5317a8cccf5189be42da338a8c0f7b2f1b0de30950c79d0679d59292b3f37a0e':
        raise ValueError('Exact reviewed operational compiler command report required.')
    rows = json.loads(path.read_text())['results']
    row = next(row for row in rows if row['source'] == prepare.BRIDGE)
    values = row['command'][1:row['command'].index('-c')]
    omitted = {'-msoft-float', '-mno-red-zone', '-mcmodel=kernel', '-mno-mmx',
        '-mno-sse', '-mno-sse2', '-mno-3dnow', '-fno-pic', '-mkernel',
        '-DKERNEL', '-D__KERNEL__', '-MD', '-MMD', '-fstack-usage',
        '-Wframe-larger-than=4096', '-Werror=frame-larger-than'}
    flags, index = [], 0
    while index < len(values):
        value = values[index]
        if value in ('-target', '-arch', '-MF'):
            index += 2; continue
        if value not in omitted:
            flags.append(value.replace(str(base / 'project'), str(project)))
        index += 1
    return [*flags, '-fPIC', '-U__linux__', '-U__linux', '-O1', '-g',
        '-Werror', '-Wno-unused-parameter', '-I', str(project / prepare.DIRECTORY)]


def run(args):
    base = args.base.resolve(strict=True)
    manifest = composer.verify_composition(base)
    if sha(base / 'composition.json') != '40f0fd1fc279421464c14f9b98f7fa84f6850e6fafb61d46aa60663ce471dd4c':
        raise ValueError('Exact final operational source parent required.')
    output = composer.new_output(args.output, [base, HERE])
    output.mkdir(parents=True)
    selected = output / 'successor'
    preparation = prepare.prepare(base, selected)
    project = output / 'project'
    shutil.copytree(base / 'project', project)
    shutil.copytree(selected / 'project', project, dirs_exist_ok=True)
    actual = {name: (project / name).read_text() for name in prepare.INPUTS}
    device = actual[prepare.BACKEND]
    first = device.index('struct Platform {'); last = device.index('\n};', first) + 3
    (output / 'actual-platform.inc').write_text('struct RegisterView { void *address; NvU64 bytes; };\n' + device[first:last])
    (output / 'actual-arm.inc').write_text(body(device, 'armInterrupt', 'NV_STATUS'))
    (output / 'actual-timer-arm.inc').write_text(body(actual[prepare.TIMERS], 's540PmTimerArm', 'static NV_STATUS'))
    tx = output / 'actual-tx-control.c'
    tx.write_text(tx_control(base, (selected / 'source' / prepare.TX).read_text()))
    mock = HERE.parent / 'prospective-public-callback-closure/tests/mock'
    includes = [output, project / 'packages', project / prepare.DIRECTORY,
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps',
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        project / 'packages/nvidia-darwin-services/src', project / 'packages/nvidia-device-transport/src',
        project / 'packages/nvidia-gsp-bootstrap/prospective-irq-installation', mock]
    common = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-ffunction-sections',
        '-fdata-sections', *[x for p in includes for x in ('-I', str(p))]]
    compiler_bindings = {str(p.resolve(strict=True)): sha(p.resolve(strict=True)) for p in (args.cc, args.cxx)}
    bound = {str(p): sha(p) for p in (HERE / 'prepare.py', HERE / 'commit-api.c.inc', HERE / 'S540NvidiaGspCommit.h',
        Path(__file__), HERE / 'tests/check_commit.c', HERE / 'tests/check_endpoints.cpp',
        HERE.parent / 'prospective-session-lifetime-closure/tests/tx-control.c.inc')}
    report = dict(format=1, status='running', parent_composition_sha256=sha(base / 'composition.json'),
        preparation=preparation, source_sha256=bound, compiler_sha256=compiler_bindings, variants={},
        original_entry_admission=False, hardware_stop_proven=False, pm_30_second_shutdown_bound_proven=False,
        physical_release_authorized=False, actual_power_callback_event_atomic_with_commit=False,
        commit_linearization='Genuine cancellation control CAS; earlier PM event timestamp remains the fixed deadline origin.')
    write(output / 'results.json', report)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    commands, dependencies, binaries = [], {}, {}

    def compile_one(compiler, flags, source, obj):
        dep = obj.with_suffix('.d')
        command = [compiler, *flags, '-MD', '-MF', dep, '-c', source, '-o', obj]
        execute(command, obj.with_suffix('.compile.log'))
        commands.append([str(x) for x in command])
        for item in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(item).resolve(strict=True)
            digest = sha(path)
            if dependencies.setdefault(str(path), digest) != digest:
                raise ValueError('Compiler input changed between modes: ' + str(path))
        return obj

    try:
        for label, instrumentation in [('plain', []), ('sanitized', [
                '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])]:
            work = output / label; work.mkdir()
            cflags = ['-std=c11', *common, *instrumentation]
            cppflags = ['-std=c++17', *common, *instrumentation]
            cancellation = compile_one(args.cc, cflags, project / prepare.CANCEL, work / 'cancellation.o')
            observations = {}
            for name, source, compiler, flags in [
                    ('commit', HERE / 'tests/check_commit.c', args.cc, cflags),
                    ('legacy_scope', HERE.parent / 'prospective-irq-callback-closure/tests/check_cancellation.c', args.cc, cflags),
                    ('endpoints', HERE / 'tests/check_endpoints.cpp', args.cxx, cppflags)]:
                obj = compile_one(compiler, flags, source, work / (name + '.o'))
                binary = work / name
                argv = [compiler, *instrumentation, '-pthread', obj, cancellation, '-Wl,--gc-sections', '-o', binary]
                execute(argv, binary.with_suffix('.link.log')); commands.append([str(x) for x in argv])
                result = execute([binary], binary.with_suffix('.run.log'), environment)
                view = json.loads(result.stdout)
                if view['status'] != 'passed': raise ValueError('Failed PM ' + name)
                observations[name] = view; binaries[str(binary)] = sha(binary)
                if name == 'endpoints':
                    for case in ('1', '2'):
                        value = json.loads(execute([binary, case],
                            work / ('irq-leave-failure-' + case + '.log'), environment).stdout)
                        if value['status'] != 'passed': raise ValueError('Failed real IRQ leave-failure control')
                        observations['irq_leave_failure_' + case] = value
            original_flags = original_host_flags(base, project)
            original_objects = [compile_one(args.cc, [*original_flags, *instrumentation], source,
                work / ('tx-%d.o' % index)) for index, source in enumerate((tx, project / prepare.BRIDGE, project / prepare.CANCEL))]
            binary = work / 'tx'
            argv = [args.cc, *instrumentation, *original_objects, '-Wl,--gc-sections', '-o', binary]
            execute(argv, binary.with_suffix('.link.log')); commands.append([str(x) for x in argv])
            value = json.loads(execute([binary], binary.with_suffix('.run.log'), environment).stdout)
            if value['status'] != 'passed': raise ValueError('Failed actual TX')
            observations['tx'] = value; binaries[str(binary)] = sha(binary)
            report['variants'][label] = observations
            write(output / 'results.json', report)

        negative = {}
        production = actual[prepare.CANCEL]
        mutations = {
            'ignore_origin_revocation': prepare.modify(production, 'commitEnter', lambda body:
                body.replace('checkOrigin(value, origin)', 'NV_OK')),
            'hide_payload_publication_window': prepare.once(production,
                'result.inFlight = !!(value & COMMIT_BUSY);', 'result.inFlight = !!serial;'),
            'allow_cleanup_during_commit': prepare.modify(production, 's540GspCancellationBeginCleanupState', lambda body:
                prepare.once(body, '(CAPTURE_BUSY | COMMIT_BUSY)', 'CAPTURE_BUSY'))}
        for name, source in mutations.items():
            work = output / name; work.mkdir()
            changed = work / 'cancellation.c'; changed.write_text(source)
            obj = compile_one(args.cc, ['-std=c11', *common], changed, work / 'mutant.o')
            binary = work / 'check'
            execute([args.cc, '-pthread', obj, output / 'plain/commit.o', '-Wl,--gc-sections', '-o', binary], work / 'link.log')
            failed = execute([binary], work / 'run.log', environment, expected=None)
            if failed.returncode != 1 or 'commit check failed line' not in failed.stderr:
                raise ValueError('Required PM negative mutation was not detected: ' + name)
            negative[name] = dict(exit_status=failed.returncode, log_sha256=sha(work / 'run.log'))
        for path, digest in {**bound, **compiler_bindings, **dependencies, **binaries}.items():
            if sha(Path(path)) != digest: raise ValueError('Bound PM input/artifact changed: ' + path)
        if composer.verify_composition(base) != manifest: raise ValueError('Parent changed during PM controls.')
        report.update(status='passed-actual-revocation-commit-controls', negative_mutants=negative,
            commands=commands, dependencies_sha256=dependencies, binary_sha256=binaries,
            selected_output_sha256={name: sha(project / name) for name in prepare.INPUTS})
        return report
    except Exception as error:
        report.update(status='failed', error=str(error)); raise
    finally:
        write(output / 'results.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'cc', 'cxx', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'checks': {mode: {key: value['checks'] for key, value in rows.items()}
        for mode, rows in result['variants'].items()}, 'negative_mutants': len(result['negative_mutants'])}))
