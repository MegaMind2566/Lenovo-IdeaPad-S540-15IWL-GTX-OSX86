#!/usr/bin/env python3
"""Run exact original RC, plain 1Hz list and BIF callback bodies.

Explicit lock, power, hardware and object-layout fixtures remain visible in
the report. This is a CPU source control and does not grant kernel entry.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCES = {
    'src/nvidia/arch/nvalloc/unix/src/osapi.c': 'e4336f0e3bb55122680e0d344f970c123664122c2415134b7a6b517c98fcbe75',
    'src/nvidia/src/kernel/os/os_timer.c': '78da8c6f23d9732dc4ff393b83553ecf06d800699362b70bc67a5f867dd41b4c',
    'src/nvidia/src/kernel/gpu/bif/kernel_bif.c': '8d3339e2c6ec332b709d6c194532c5827f99521c36372f76a9a9df13ac99e078',
}
FUNCTIONS = {
    'osapi.c': ['rm_run_rc_callback'],
    'os_timer.c': ['osInit1HzCallbacks', 'osDestroy1HzCallbacks',
        '_os1HzCallbackIsOnList', 'osSchedule1HzCallback', 'osRemove1HzCallback',
        '_osRunAll1HzCallbacks', 'osRun1HzCallbacksNow', 'osRunQueued1HzCallbacksUnderLock', '_os1HzCallback'],
    'kernel_bif.c': ['_kbifCheckIfGpuExists'],
}


def body(source, name):
    pattern = (r'(?m)^(?:static\s+)?(?:NV_STATUS|NvBool|NvU32|void)\s+'
        r'(?:NV_API_CALL\s+)?' + re.escape(name) + r'\s*\(')
    matches = [m for m in re.finditer(pattern, source)
        if ';' not in source[m.end():source.index('{', m.end())]]
    if len(matches) != 1:
        raise ValueError('Exact original body missing or ambiguous: '+name)
    match = matches[0]
    brace = source.index('{', match.end())
    depth = 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[brace:], re.S):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if not depth:
                return source[match.start():brace+token.end()]+'\n'
    raise ValueError('Unterminated original body: '+name)


def check(upstream, sanitize=False, output=None):
    upstream = Path(upstream).resolve(strict=True)
    inputs = {}
    text = {}
    for relative, expected in SOURCES.items():
        path = upstream/relative
        if path.is_symlink():
            raise ValueError('Symlink source refused: '+relative)
        value = path.read_bytes()
        observed = hashlib.sha256(value).hexdigest()
        if observed != expected:
            raise ValueError('Pinned NVIDIA source changed: '+relative)
        inputs[relative] = observed
        text[path.name] = value.decode()
    compiler = shutil.which('clang') or shutil.which('gcc')
    if not compiler:
        raise RuntimeError('A C11 compiler is required')
    with tempfile.TemporaryDirectory(prefix='s540-original-1hz-') as temporary:
        work = Path(temporary)
        # Full NVIDIA MIT notice accompanies the extracted complete bodies.
        notice = text['os_timer.c'][:text['os_timer.c'].index('/*!')]
        contents = notice + '\n' + '\n'.join(
            '\n#line 1 "'+filename+':'+name+'"\n'+body(text[filename], name)
            for filename, names in FUNCTIONS.items() for name in names)
        (work/'actual-1hz-bodies.inc').write_text(contents)
        flags = ['-std=c11', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-parameter']
        if sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command = [compiler, *flags, '-I'+str(work), str(HERE/'check_actual_1hz.c'), '-o', str(work/'control')]
        subprocess.run(command, check=True, capture_output=True, text=True)
        environment = dict(os.environ)
        if sanitize:
            environment['ASAN_OPTIONS'] = environment.get('ASAN_OPTIONS', '')+':detect_leaks=0'
        run = subprocess.run([str(work/'control')], capture_output=True, text=True,
            timeout=20, env=environment)
        if run.returncode or run.stderr:
            raise RuntimeError('Actual original 1Hz body control failed:\n'+run.stdout+run.stderr)
        result = json.loads(run.stdout)
        result.update({
            'profile': 'actual-original-rc-plain-1hz',
            'upstream_commit': '1a82fbfda8f321b056eb3568850f9316c5e465c5',
            'source_sha256': inputs,
            'extracted_body_sha256': hashlib.sha256(contents.encode()).hexdigest(),
            'fixture_sha256': hashlib.sha256((HERE/'check_actual_1hz.c').read_bytes()).hexdigest(),
            'complete_original_bodies': sum(map(len, FUNCTIONS.values())),
            'compiler': compiler, 'sanitizers': sanitize,
            'original_layout_headers_used': False,
            'lock_and_hardware_dependencies': 'explicit POSIX lock and power/existence fixtures',
            'master_thread_enforced_by_original': False,
            'event_owner_rows_added': 0,
            'whole_profile_1hz_reachability_proved': False,
            'hardware_admission': False, 'kernel_execution': False,
        })
    for relative, expected in inputs.items():
        if hashlib.sha256((upstream/relative).read_bytes()).hexdigest() != expected:
            raise ValueError('NVIDIA input changed during controls: '+relative)
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.upstream, args.sanitize, args.output), indent=2, sort_keys=True))
