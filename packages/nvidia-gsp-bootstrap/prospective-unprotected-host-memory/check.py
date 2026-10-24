#!/usr/bin/env python3
"""Execute complete selected memory services with synthetic raw CPU observations."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import resource
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module():
    spec = importlib.util.spec_from_file_location('s540_unprotected_memory', HERE / 'prepare.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def fixture(project, device):
    # Only this private raw-instruction primitive is replaced. The complete
    # observation, policy, allocation ABI, mappings and diagnostics stay actual.
    start, end = function_span(device, 'unprotectedCpuid')
    body = device.index('{', start)
    device = device[:body] + '{\n    MemoryFixture::cpuid(leaf,subleaf,out.eax,out.ebx,out.ecx,out.edx);\n}' + device[end:]
    text = (HERE / 'tests/check_memory.cpp.inc').read_text()
    for key, value in {
        'SERVICE_HEADER': str(project / 'packages/nvidia-device-transport/src/nv_device_services.h'),
        'COMMIT_HEADER': str(project / 'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure/S540NvidiaGspCommit.h'),
        'SERVICES_BODY': device,
    }.items():
        marker = '@' + key + '@'
        require(text.count(marker) == 1, 'Exact memory fixture token required: ' + key)
        text = text.replace(marker, value)
    return text


def dependencies(path):
    return {str(Path(name).resolve(strict=True)): sha(Path(name).resolve(strict=True))
            for name in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1])}


def run(args):
    require(args.host_control, 'Explicit --host-control is required for synthetic CPU controls')
    project = args.input_project.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists(), 'Fresh memory-policy controls output required')
    prepare = module()
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_text())
    backend_contract = contract['unchanged_owned_zeroed_backend']
    require(sha(project / backend_contract['path']) == backend_contract['sha256'],
            'The unchanged owned zeroed Darwin backend differs from the reviewed B6 source')
    original = {name: (project / name).read_text() for name in prepare.INPUTS}
    selected = prepare.transforms(original)
    if args.composed_project:
        composed = args.composed_project.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected.items()),
                'Composed memory/context sources differ from exact selected profile')
    refusals = []
    for invalid in ({}, dict(original, unknown='not allowed'),
                    dict(original, **{prepare.DEVICE: original[prepare.DEVICE] + '\n'}),
                    dict(original, **{prepare.CONTEXT: original[prepare.CONTEXT] + '\n'})):
        try:
            prepare.transforms(invalid)
        except ValueError:
            refusals.append('missing-extra-or-changed-source-refused')
        else:
            raise ValueError('Changed exact source accepted')
    source_files = [HERE / 'prepare.py', *(HERE / name for name in prepare.SOURCE_FILES)]
    hashes = {str(path.relative_to(ROOT)): sha(path) for path in source_files}
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    output.mkdir(parents=True)
    copy = output / 'project'
    shutil.copytree(project, copy)
    for name, text in selected.items():
        (copy / name).write_text(text)
    compiler = args.cxx.expanduser().absolute()  # Preserve C++ driver's lexical alias.
    compiler_target = compiler.resolve(strict=True)
    require(compiler_target.is_file() and os.access(compiler, os.X_OK), 'Executable C++ compiler required')
    flags = ['-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-I' + str(copy / 'packages/nvidia-device-transport/src'),
             '-I' + str(copy / 'packages/nvidia-gsp-bootstrap/prospective-dma-producer-closure')]
    variants, commands = {}, []

    # Compile the unreplaced private native CPUID instruction as well. This is
    # host C++ compilation only; its policy is exercised below with synthetic
    # raw observations, and no physical target result is inferred from it.
    native = copy / prepare.DEVICE
    native_object, native_dep = output / 'native-instruction.o', output / 'native-instruction.d'
    native_command = [str(compiler), *flags, '-MD', '-MF', str(native_dep),
                      '-c', str(native), '-o', str(native_object)]
    built = subprocess.run(native_command, capture_output=True, text=True, timeout=120)
    (output / 'native-instruction-compile.log').write_text(built.stdout + built.stderr)
    require(built.returncode == 0, 'Actual native CPUID primitive did not compile: ' + built.stderr[-4000:])
    commands.append(native_command)

    def execute(label, device, sanitize=False, negative=False):
        source = output / (label + '.cpp')
        source.write_text(fixture(copy, device))
        session = copy / 'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.cpp'
        executable = output / label
        # A separate full Session TU keeps its actual private namespace intact.
        command = [str(compiler), *flags]
        if sanitize:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        objects, deps, compilation = [], [], []
        for unit, name in ((source, 'services'), (session, 'session')):
            obj, dep = output / (label + '-' + name + '.o'), output / (label + '-' + name + '.d')
            compile_command = command + ['-MD', '-MF', str(dep), '-c', str(unit), '-o', str(obj)]
            built = subprocess.run(compile_command, capture_output=True, text=True, timeout=120)
            compilation.append(built.stdout + built.stderr)
            require(built.returncode == 0, 'Whole Services/Session did not compile ' + label + ': ' + built.stderr[-7000:])
            commands.append(compile_command)
            objects.append(obj)
            deps.append(dep)
        link_command = command + [str(obj) for obj in objects] + ['-o', str(executable)]
        built = subprocess.run(link_command, capture_output=True, text=True, timeout=120)
        compilation.append(built.stdout + built.stderr)
        (output / (label + '-compile.log')).write_text(''.join(compilation))
        require(built.returncode == 0, 'Whole Services/Session did not link ' + label + ': ' + built.stderr[-7000:])
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30, env=env)
        (output / (label + '-run.log')).write_text(result.stdout + result.stderr)
        commands.append(link_command)
        row = dict(source_sha256=sha(source), session_sha256=sha(session), binary_sha256=sha(executable),
                   dependency_sha256={name: value for dep in deps for name, value in dependencies(dep).items()}, returncode=result.returncode,
                   sanitized=sanitize, negative_control=negative)
        if negative:
            require(result.returncode != 0, 'Actual production policy mutant survived: ' + label)
            row['killed'] = True
        else:
            require(result.returncode == 0, 'Actual memory fixture failed ' + label + ': ' + result.stderr[-5000:])
            lines = [line for line in result.stderr.splitlines() if line.startswith('S540 NVIDIA memory: ')]
            require(len(lines) == 17, 'Allocation logging is not bounded to seventeen actual records')
            require('stage=published' in lines[0] and 'pages=2 page_bytes=4096 contiguous=0 cache=0 zeroed=1 unprotected=1 node=-1' in lines[0]
                    and 'cpu_observed=0x7 max_basic=0x7' in lines[0] and 'model=0x8e' in lines[0],
                    'First unprotected diagnostic does not report actual request/raw profile')
            row.update(json.loads(result.stdout))
            row['allocation_diagnostic_records'] = len(lines)
        variants[label] = row

    device = selected[prepare.DEVICE]
    execute('selected', device)
    execute('selected_sanitized', device, sanitize=True)
    require(variants['selected']['checks'] == variants['selected_sanitized']['checks'], 'Plain/sanitized checks differ')
    mutations = {
        'wrong_tme_bit': ('cpu.structured.ecx & (1U << 13)', 'cpu.structured.ecx & (1U << 12)'),
        'ignore_hypervisor': ('!(cpu.signature.ecx & (1U << 31))', '(cpu.signature.ecx || true)'),
        'ignore_vendor_ebx': ('cpu.basic.ebx == 0x756e6547U', '(cpu.basic.ebx || true)'),
        'ignore_vendor_edx': ('cpu.basic.edx == 0x49656e69U', '(cpu.basic.edx || true)'),
        'ignore_vendor_ecx': ('cpu.basic.ecx == 0x6c65746eU', '(cpu.basic.ecx || true)'),
        'ignore_family': ('cpu.family == 6U', '(cpu.family || true)'),
        'ignore_model': ('cpu.model == 0x8eU', '(cpu.model || true)'),
        'probe_unsupported_leaf': ('if (value.basic.eax >= 7U)', 'if (value.basic.eax >= 1U)'),
        'allow_huge_geometry': ('pageSize != kPageBytes || ', ''),
        'ignore_numa': (' || node != -1', ''),
        'ignore_bool': (' || unencrypted > 1', ''),
        'lose_session_error': ('return fail(status, "session");', 'return fail(NV_ERR_NOT_SUPPORTED, "session");'),
        'unbounded_failure_logging': ('while (count < 16U)', 'while (count < 160U)'),
    }
    for name, (before, after) in mutations.items():
        require(device.count(before) == 1, 'Exact production mutation anchor changed: ' + name)
        execute('mutant_' + name, device.replace(before, after), negative=True)
    report = dict(format=1, status='passed-complete-memory-services-and-session-CPU-controls',
                  exact_input_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in original.items()},
                  exact_output_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in selected.items()},
                  source_file_sha256=hashes, exact_source_refusal_controls=refusals, variants=variants, commands=commands,
                  unchanged_owned_zeroed_backend_sha256={backend_contract['path']: backend_contract['sha256']},
                  compiler_invocation_path=str(compiler), compiler_resolved_path=str(compiler_target), compiler_sha256=sha(compiler_target),
                  unreplaced_native_CPUID_compile=dict(object_sha256=sha(native_object),
                      dependency_sha256=dependencies(native_dep), physical_CPU_executed=False,
                      native_Darwin_compilation=False),
                  CPU_observations='explicit synthetic raw CPUID observations; only private primitive body replaced in generated fixture',
                  resource_endpoints='explicit ordinary zeroed host pages and DMA translation fixture; actual IOKit backend not executed',
                  sanitizer_policy=dict(address_and_undefined_fatal=True, leak_sanitizer_enabled=False,
                      leak_sanitizer_reason='Traced host cannot enumerate /proc tasks; disabled explicitly, not reported passed.'),
                  original_RM_executed=False, IOKit_executed=False, native_Darwin_compilation=False,
                  hardware_executed=False, GPU_initialization_proven=False, whole_DMA_stop_proven=False,
                  system_security_changed=False, github_workflows_started=0)
    require({str(path.relative_to(ROOT)): sha(path) for path in source_files} == hashes,
            'Checked production/helper source changed during memory controls')
    (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-project', type=Path, required=True)
    parser.add_argument('--composed-project', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], cases=result['variants']['selected']['cases'],
                         checks=result['variants']['selected']['checks'],
                         mutants_killed=sum(bool(row.get('killed')) for row in result['variants'].values()))))
