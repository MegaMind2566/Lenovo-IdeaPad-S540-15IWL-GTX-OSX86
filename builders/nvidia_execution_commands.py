"""Persistent command diagnostics for development-only NVIDIA execution checks."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
from pathlib import Path
import shlex
import subprocess

import compile_nvidia_global_rm as original

_ACTIVE = ContextVar('nvidia_execution_command_diagnostics', default=None)


def _text(value: str | bytes | None) -> str:
    return value.decode(errors='replace') if isinstance(value, bytes) else value or ''


def _save(state: dict) -> None:
    (state['directory'] / 'command-records.json').write_text(json.dumps(
        {'format': 1, 'status': state['status'], 'commands': state['commands'],
         'scope': 'Command diagnostics only; no kernel or GPU runtime evidence.'},
        indent=2, sort_keys=True) + '\n')


def _start(args: list[str], diagnostic_log: Path | None) -> tuple[dict | None, Path | None]:
    state = _ACTIVE.get()
    if state is None:
        return None, diagnostic_log
    index = len(state['commands']) + 1
    log = diagnostic_log or state['directory'] / ('command-%04d.log' % index)
    item = {'index': index, 'argv': args, 'log': str(log), 'status': 'running'}
    state['commands'].append(item)
    _save(state)
    return item, log


def run(*args: str, timeout: int = 180,
        diagnostic_log: Path | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    item, log = _start(list(args), diagnostic_log)
    try:
        result = original.execute(list(args), timeout=timeout, diagnostic_log=log, cwd=cwd)
    except Exception:
        if item is not None:
            item['status'] = 'failed'
            _save(_ACTIVE.get())
        raise
    if item is not None:
        item['status'] = 'passed'
        _save(_ACTIVE.get())
    return result


@contextmanager
def diagnostics(output: Path):
    """Also retain errors from unchanged nested v9 compiler/SDK helpers."""
    directory = output / 'command-logs'
    directory.mkdir(parents=True, exist_ok=True)
    state = {'directory': directory, 'commands': [], 'status': 'running'}
    token = _ACTIVE.set(state)
    _save(state)
    try:
        yield
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        args = [str(value) for value in error.cmd]
        item, log = _start(args, None)
        stdout, stderr = _text(error.stdout), _text(error.stderr)
        log.write_text('stdout:\n' + stdout + '\nstderr:\n' + stderr)
        item['status'] = 'failed'
        detail = (stderr.strip() or stdout.strip() or 'No diagnostic output was returned.')[-8000:]
        reason = ('timed out after ' + str(error.timeout) + ' seconds'
                  if isinstance(error, subprocess.TimeoutExpired)
                  else 'failed with exit status ' + str(error.returncode))
        raise RuntimeError('Nested build command ' + reason + ': ' + shlex.join(args[:2]) +
                           ' (' + str(len(args)) + ' arguments)\n' + detail +
                           '\nFull diagnostics: ' + str(log)) from None
    except Exception:
        state['status'] = 'failed'
        raise
    else:
        state['status'] = 'passed'
    finally:
        if state['status'] == 'running':
            state['status'] = 'failed'
        _save(state)
        _ACTIVE.reset(token)


def logged(*, output_argument: int = 0, report: str | None = None):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            output = args[output_argument] if len(args) > output_argument else kwargs['output']
            path = Path(output) / report if report is not None else None
            try:
                with diagnostics(Path(output)):
                    if path is not None:
                        # A reused output directory must never retain a prior
                        # successful report after this invocation refuses early.
                        initial = {'format': 1, 'status': 'running', 'phase': 'invocation-start',
                                   'previous_report_discarded': path.exists(),
                                   'native_execution': {}, 'production_candidate_allowed': False,
                                   'kernel_runtime': 'not_tested', 'gpu_access': False}
                        path.write_text(json.dumps(initial, indent=2, sort_keys=True) + '\n')
                    return function(*args, **kwargs)
            except Exception as error:
                if path is not None and path.exists():
                    record = json.loads(path.read_text())
                    record.update(status='failed', failure_type=type(error).__name__)
                    if record.get('phase') == 'invocation-start':
                        record['early_refusal'] = True
                    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
                raise
        return wrapped
    return decorate


class ComponentProgress:
    """Save each completed component before attempting the following one."""
    def __init__(self, path: Path, fields: dict):
        self.path = path
        self.record = {'format': 1, 'status': 'running', 'native_execution': {}, **fields}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.record, indent=2, sort_keys=True) + '\n')

    def component(self, name: str, operation):
        self.record['active_component'] = name
        self.save()
        try:
            result = operation()
        except Exception as error:
            self.record.update(status='failed', failure_type=type(error).__name__)
            self.save()
            raise
        self.record['native_execution'][name] = result
        self.record['active_component'] = None
        self.save()
        return result
