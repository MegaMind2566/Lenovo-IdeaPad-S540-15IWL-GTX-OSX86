#!/usr/bin/env python3
"""Compile real port callbacks and compare actual SDK instructions; never run them."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / 'builders/check_nvidia_execution.py').is_file())
sys.path.insert(0, str(ROOT / 'builders'))
import compile_nvidia_global_rm as original
import nvidia_metaclass_initializers as macho
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original'))
import common

PAIRS = {
    'os_io_read_byte': ('s540SdkPortReadByte', 'ec'),
    'os_io_read_word': ('s540SdkPortReadWord', '66ed'),
    'os_io_read_dword': ('s540SdkPortReadDword', 'ed'),
    'os_io_write_byte': ('s540SdkPortWriteByte', 'ee'),
    'os_io_write_word': ('s540SdkPortWriteWord', '66ef'),
    'os_io_write_dword': ('s540SdkPortWriteDword', 'ef')}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def text_atoms(path):
    image = macho.Object(path)
    result = {}
    for symbol in image.symbols:
        if not symbol.section or not symbol.kind & 1 or symbol.kind & 0x0e != 0x0e:
            continue
        section = image.sections[symbol.section - 1]
        if section.name != '__text': continue
        if image.relocations(section): raise ValueError('Port-I/O text acquired a relocation')
        end = min([other.value for other in image._defined(symbol.section) if other.value > symbol.value],
                  default=section.address + section.size)
        start = symbol.value - section.address
        code = bytearray(image.data[section.offset + start:section.offset + end - section.address])
        result[symbol.name.removeprefix('_')] = macho._without_alignment_nops(code, 0).hex()
    return result

def check(args):
    upstream = original._pinned_upstream(args.upstream)
    namespace = args.namespace.resolve(strict=True)
    output = args.output.resolve()
    sdk = args.sdk.resolve(strict=True)
    if output.exists() or any(output.is_relative_to(path) or path.is_relative_to(output)
            for path in [upstream, HERE, sdk]):
        raise ValueError('A fresh output outside all source inputs is required')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / 'build'):
        raise ValueError('Repository output must be below build/')
    cc = common.compiler(str(args.cc))
    identity = common.execution_identity(cc, cc, args.host_control)
    identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
    sdk_record = common.validate_sdk(sdk, args.sdk_archive, args.host_control)
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_text())
    for group, root in [('source_sha256', HERE), ('original_source_sha256', upstream),
                        ('sdk_source_sha256', sdk)]:
        for name, expected in contract[group].items():
            path = root / name
            if path.is_symlink() or sha(path) != expected:
                raise ValueError('Port-I/O source contract changed: ' + name)
    ns = json.loads((ROOT / 'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    if sha(namespace) != ns['namespace_sha256']:
        raise ValueError('Port-I/O callbacks require the exact baseline namespace')
    output.mkdir(parents=True)
    flags = original.original_bridge_flags(upstream, output / 'profile', cc, namespace)
    flags += ['-target', 'x86_64-apple-macos15', '-mkernel', '-DKERNEL', '-D__KERNEL__',
        '-nostdinc', '-isystem', str(sdk / 'Headers'), '-std=gnu11', '-Werror',
        '-Wno-unused-parameter', '-Wframe-larger-than=4096', '-Werror=frame-larger-than',
        '-DS540_NVIDIA_DARWIN_PORT_IO=1']
    objects, commands = {}, {}
    for label, name in [('actual', 'S540ProspectivePortIo.c'), ('sdk-reference', 'sdk_port_io_reference.c')]:
        obj = output / (label + '.o')
        command = [str(cc), *flags, '-c', str(HERE / name), '-o', str(obj)]
        original.execute(command, diagnostic_log=output / (label + '.log'))
        objects[label], commands[label] = obj, command
    defined, imported, _ = original.macho_symbols(objects['actual'])
    if defined != {original.PREFIX + name for name in PAIRS} or imported:
        raise ValueError('Port-I/O implementation changed its exact six-export/zero-import profile')
    actual, reference = text_atoms(objects['actual']), text_atoms(objects['sdk-reference'])
    rows = {}
    for name, (target, opcode) in PAIRS.items():
        code = actual[original.PREFIX + name]
        if code != reference[target] or bytes.fromhex(opcode) not in bytes.fromhex(code):
            raise ValueError('Real callback differs from its actual SDK I/O instruction: ' + name)
        rows[name] = {'sdk_reference': target, 'actual_code_hex': code,
            'expected_io_opcode_hex': opcode, 'exact_sdk_machine_code_match': True}
    negatives = []
    for label, options in [('missing-profile', []), ('zero-profile', ['-DS540_NVIDIA_DARWIN_PORT_IO=0']),
                           ('foreign-profile', ['-DS540_NVIDIA_DARWIN_PORT_IO=2'])]:
        negative_flags = [flag for flag in flags if not flag.startswith('-DS540_NVIDIA_DARWIN_PORT_IO=')]
        command = [str(cc), *negative_flags, *options, '-c', str(HERE / 'S540ProspectivePortIo.c'),
                   '-o', str(output / ('refused-' + label + '.o'))]
        result = subprocess.run(command, text=True, capture_output=True)
        (output / ('refused-' + label + '.log')).write_text(result.stdout + result.stderr)
        if not result.returncode or 'Explicit selected Darwin port-I/O source profile required' not in result.stderr:
            raise ValueError('Unselected port-I/O source profile did not fail compilation')
        negatives.append({'case': label, 'refused': True})
    report = {'format': 1, 'status': 'matched-real-sdk-port-instructions', **identity,
        'sdk': sdk_record, 'callbacks': rows, 'negative_compile_controls': negatives,
        'object_sha256': {name: sha(path) for name, path in objects.items()}, 'commands': commands,
        'kernel_execution': 'not_tested', 'gpu_access': False, 'port_instructions_executed': False,
        'original_entry_admission': False, 'production_candidate_allowed': False,
        'source_contract_sha256': sha(HERE / 'SOURCE-CONTRACT.json')}
    (output / 'port-io-checks.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream', 'namespace', 'sdk', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--cc', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--sdk-archive', type=Path)
    parser.add_argument('--host-control', action='store_true')
    value = check(parser.parse_args())
    print(json.dumps({'status': value['status'], 'callbacks': len(value['callbacks']), 'port_instructions_executed': False}))
