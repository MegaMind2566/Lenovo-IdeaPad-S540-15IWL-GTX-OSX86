"""CPU control orchestration; input bindings, actual bodies and fatal modes."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE_SHA = '72b7d5a5d93504218e8a7953d79c90c1609e4580c55922deb2ec5dab13de24d8'
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def sha(path):
    if path.is_symlink(): raise ValueError('CPU control source symlink refused')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def body(text, name, result='NV_STATUS'):
    first, last = function_span(text, name)
    return result + '\n' + text[first:last] + '\n'


def run_command(command, log, *, expected=0, environment=None):
    result = subprocess.run([str(value) for value in command], text=True,
        capture_output=True, timeout=180, env=environment)
    log.write_text(result.stdout + result.stderr)
    if result.returncode != expected:
        raise ValueError('Actual-body CPU control failed: ' + str(log) + '\n' + result.stderr[-5000:])
    return result


def run(here, component, args):
    here = here.resolve(strict=True)
    base = args.base.resolve(strict=True)
    output = args.output.resolve()
    cc = args.cc.resolve(strict=True)
    if output.exists() or output.is_relative_to(here) or base.is_relative_to(output):
        raise ValueError('Fresh isolated CPU controls output required')
    if sha(base / 'composition.json') != BASE_SHA:
        raise ValueError('Exact reviewed shutdown source parent required')
    module = load('s540_' + component.replace('-', '_') + '_prepare', here / 'prepare.py')
    selected = module.transforms({name: (base / 'project' / name).read_text() for name in module.INPUTS})
    if module.ORIGINAL_INPUTS:
        selected.update(module.original_transforms({name: (base / 'source' / name).read_text()
            for name in module.ORIGINAL_INPUTS}))
    source_paths = [here / 'prepare.py', here / 'check.py', here / 'tests' / {
        'context': 'check_context.c', 'first-lock': 'check_locks.c', 'dma': 'check_dma.c'}[component],
        Path(__file__), base / 'composition.json']
    source_paths += list(here.glob('*.inc')) + list(here.glob('*.h'))
    source_paths += [base / ('source' if name in module.ORIGINAL_INPUTS else 'project') / name for name in selected]
    ownership_source = base / 'project/packages/nvidia-gsp-bootstrap/prospective-rm-lock-ownership/S540ProspectiveRmLockOwnership.c'
    ownership_header = ownership_source.with_suffix('.h')
    if component == 'first-lock': source_paths += [ownership_source, ownership_header]
    cancellation = args.cancellation_source.resolve(strict=True) if args.cancellation_source else (
        base / 'project/packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c')
    if component == 'dma': source_paths += [cancellation, here / 'tests/check_record.c']
    pm_event = ROOT / 'packages/nvidia-gsp-bootstrap/prospective-pm-event-closure'
    if component == 'dma' and args.cancellation_source:
        source_paths.append(pm_event / 'S540NvidiaPowerCoupling.h')
    contract_path = here / 'SOURCE-CONTRACT.json'
    contract = json.loads(contract_path.read_text())
    if contract['shared_cpu_checker_sha256'] != sha(Path(__file__)):
        raise ValueError('Shared actual-body CPU checker differs from the selected module contract')
    source_paths.append(contract_path)
    bindings = {str(path): sha(path) for path in source_paths}
    compiler_sha = sha(cc)
    output.mkdir(parents=True)
    for name, text in selected.items():
        target = output / 'selected' / ('source' if name in module.ORIGINAL_INPUTS else 'project') / name
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
    if component == 'context':
        text = selected[module.CONTEXT]
        (output / 'actual-context-bodies.inc').write_text(''.join(body(text, name) for name in (
            's540GspContextDisableAdapter', 's540GspContextShutdownAdapter')))
        cases = [None]
        mutations = [('discard-disable-status', 'if (status != NV_OK) { context->state.quarantined = NV_TRUE; return status; }',
            'if (0) { context->state.quarantined = NV_TRUE; return status; }', None),
            ('discard-shutdown-status', 's540RmShutdownAdapterChecked', 's540RmDisableAdapterChecked', None)]
    elif component == 'first-lock':
        text = selected[module.ORIGINAL]
        (output / 'actual-first-lock-body.inc').write_text(body(text, 's540FirstTxnOriginalLocksReleased'))
        ownership = ownership_source.read_text()
        (output / 'actual-ownership-bodies.inc').write_text(''.join(body(ownership, name) for name in (
            's540ProspectiveReadOriginalLockOwnership', 's540ProspectiveOriginalCurrentThreadLocksReleased')))
        types = ownership_header.read_text()
        start = types.index('typedef struct S540ProspectiveRmLockOwnership {')
        end = types.index('} S540ProspectiveRmLockOwnership;', start) + len('} S540ProspectiveRmLockOwnership;')
        (output / 'actual-lock-types.inc').write_text(types[start:end] + '\n')
        cases = list(range(40))
        mutations = [('ignore-allocation-owner', ' || view.allocationOwned', '', 26)]
    else:
        materialize_dma(module, selected, base, output)
        cases = list(range(36))
        mutations = [('accept-unobserved-bme', '    if (!!DRF_VAL(_XVE, _DEV_CTRL, _CMD_BUS_MASTER, regVal) == !!bStop)',
            '    if (0)', 3), ('ignore-cancellation-on-zero', '        if (status != NV_OK) return status;\n        if (value == ~(NvU32)0)',
            '        if (0) return status;\n        if (value == ~(NvU32)0)', 20)]
    package = base / 'project/packages'
    includes = [output, package / 'nvidia-gsp-bootstrap/src', package / 'nvidia-darwin-services/src',
        package / 'nvidia-gsp-bootstrap/prospective-first-transaction/record',
        package / 'nvidia-gsp-bootstrap/prospective-first-transaction/record/deps', package]
    includes += [package / 'nvidia-gsp-bootstrap/prospective-pm-revocation-closure',
        package / 'nvidia-gsp-bootstrap/prospective-irq-callback-closure',
        package / 'nvidia-gsp-bootstrap/prospective-dma-producer-closure',
        base / 'source/src/common/inc', base / 'source/src/common/inc/swref',
        base / 'source/src/common/sdk/nvidia/inc']
    if component == 'dma' and args.cancellation_source: includes.append(pm_event)
    flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
        '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
        '-Wno-unused-function', *[flag for directory in includes for flag in ('-I', str(directory))]]
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    report = dict(format=1, status='running', component=component, source_sha256=bindings,
        compiler_sha256=compiler_sha, base_composition_sha256=BASE_SHA, variants={},
        endpoints='explicit CPU fixtures; complete selected production bodies execute',
        full_original_layout_proven=False, kernel_execution=False, hardware_admission=False,
        original_entry_admission=False, whole_dma_stop_proven=False, pm_acknowledgement_authorized=False)
    def write():
        (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    write()
    try:
        for variant in args.variants:
            work = output / variant; work.mkdir()
            actual_flags = list(flags)
            if variant == 'sanitized':
                actual_flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
            binary = work / 'control'
            command = [cc, *actual_flags, here / 'tests' / {
                'context': 'check_context.c', 'first-lock': 'check_locks.c', 'dma': 'check_dma.c'}[component], '-o', binary]
            if component == 'dma': command[1:1] = [cancellation]
            run_command(command, work / 'compile.log')
            observations = []
            for case in cases:
                raw = run_command([binary] + ([] if case is None else [case]), work / ('case-' + str(case) + '.log'), environment=environment)
                row = json.loads(raw.stdout)
                if row['failures']: raise ValueError('Actual body assertions failed')
                observations.append(row)
            negative = []
            for label, old, replacement, case in mutations:
                name = 'actual-context-bodies.inc' if component == 'context' else (
                    'actual-ownership-bodies.inc' if component == 'first-lock' else 'actual-dma-bodies.inc')
                path = output / name; original = path.read_text()
                if old not in original: raise ValueError('Negative mutation anchor absent: ' + label)
                path.write_text(original.replace(old, replacement, 1))
                mutant = work / label
                try:
                    mutant_command = [*command[:-1], mutant]
                    run_command(mutant_command, work / (label + '-compile.log'))
                    raw = run_command([mutant] + ([] if case is None else [case]), work / (label + '.log'), expected=1, environment=environment)
                    row = json.loads(raw.stdout)
                    if not row['failures']: raise ValueError('Negative mutation escaped: ' + label)
                    negative.append(dict(label=label, failures_detected=row['failures'], binary_sha256=sha(mutant)))
                finally: path.write_text(original)
            report['variants'][variant] = dict(status='passed', command=[str(value) for value in command],
                binary_sha256=sha(binary), observations=observations,
                checks=sum(row['checks'] for row in observations), negative_controls=negative)
            if component == 'dma':
                source = output / 'selected/project' / module.RECORD
                record_binary = work / 'record-control'
                record_command = [cc, *actual_flags, source, here / 'tests/check_record.c', cancellation,
                    '-o', record_binary]
                run_command(record_command, work / 'record-compile.log')
                rows = []
                for case in range(22):
                    raw = run_command([record_binary, case], work / ('record-' + str(case) + '.log'), environment=environment)
                    row = json.loads(raw.stdout)
                    if row['failures']: raise ValueError('Actual record body assertions failed')
                    rows.append(row)
                mutant_source = work / 'mutant-record.c'
                original = source.read_text()
                marker = 'if (checkedMaster(nv) != NV_OK || !exactGlobalMaster())'
                if original.count(marker) != 1: raise ValueError('Exact record mutation anchor changed')
                mutant_source.write_text(original.replace(marker, 'if (NV_FALSE)', 1))
                mutant_binary = work / 'mutant-record'
                mutant_command = [cc, *actual_flags, mutant_source, here / 'tests/check_record.c', cancellation,
                    '-o', mutant_binary]
                run_command(mutant_command, work / 'mutant-record-compile.log')
                raw = run_command([mutant_binary, 1], work / 'mutant-record-run.log', expected=1, environment=environment)
                refused = json.loads(raw.stdout)
                if not refused['failures']: raise ValueError('Foreign cleanup master mutation escaped')
                report['variants'][variant]['record_controls'] = dict(command=[str(value) for value in record_command],
                    binary_sha256=sha(record_binary), observations=rows, checks=sum(row['checks'] for row in rows),
                    negative_control=dict(failures_detected=refused['failures'], binary_sha256=sha(mutant_binary)))
                report['variants'][variant]['checks'] += sum(row['checks'] for row in rows)
            write()
        if sha(cc) != compiler_sha or any(sha(Path(path)) != expected for path, expected in bindings.items()):
            raise ValueError('Actual CPU input/compiler changed during controls')
        report['status'] = 'passed-selected-production-' + component + '-body-controls'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error)); raise
    finally: write()


def main(here, component):
    parser = argparse.ArgumentParser(description='Selected complete production-body CPU controls')
    for name in ('base', 'output', 'cc'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--variants', nargs='+', choices=('plain', 'sanitized'), default=['plain', 'sanitized'])
    parser.add_argument('--cancellation-source', type=Path)
    report = run(here, component, parser.parse_args())
    print(json.dumps({'status': report['status'], 'checks': {name: row['checks'] for name, row in report['variants'].items()}}))


def materialize_dma(module, selected, base, output):
    text = ''.join(body(selected[name], function) for name, function in (
        (module.GM107, 'kbifStopSysMemRequests_GM107'), (module.TU102, 'kbifWaitForTransactionsComplete_TU102')))
    (output / 'actual-dma-bodies.inc').write_text(text)
