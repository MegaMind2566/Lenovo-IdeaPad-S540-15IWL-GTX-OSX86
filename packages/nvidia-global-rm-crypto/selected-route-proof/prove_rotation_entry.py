#!/usr/bin/env python3
"""Recheck the exact checkpoint3 rotation-entry exclusion; never admit crypto."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
NAMES = ('knvlinkRotateEncryptionKeys', 'knvlinkRotateEncryptionKeys_IMPL',
         '__knvlinkRotateEncryptionKeys__')
TARGET = '_s540Global_knvlinkRotateEncryptionKeys_IMPL'
COMMENTS = re.compile(r'/\*.*?\*/|//[^\n]*', re.S)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def raw_relocations(image, section):
    # SUBTRACTOR pairs overlap by design. This is a complete symbol-reference
    # census, not the narrower metaclass loader relocation interpreter.
    for index in range(section.relocation_count):
        offset, info = struct.unpack_from('<II', image.data, section.relocation_offset + index * 8)
        symbol, external = info & 0xffffff, bool(info & (1 << 27))
        width = 1 << ((info >> 25) & 3)
        require(not offset & 0x80000000 and offset + width <= section.size, 'Invalid relocation range.')
        require(symbol < len(image.symbols) if external else 1 <= symbol <= len(image.sections),
                'Invalid relocation symbol.')
        yield dict(offset=offset, symbol=symbol, pc_relative=bool(info & (1 << 24)),
                   width=width, external=external, kind=info >> 28)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', required=True, type=Path)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--source-tree', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--decoder', nargs='+', help='Optional otool/LLVM Mach-O disassembly command.')
    args = parser.parse_args()
    artifact, repo, source = (p.resolve(strict=True) for p in
                              (args.artifact_root, args.repo, args.source_tree))
    capsule = json.loads((HERE / 'checkpoint3-proof.json').read_text())
    expected = capsule['identity']
    require(sha(Path(__file__)) == expected['proof_script_sha256'], 'Proof script identity changed.')
    helper = repo / 'builders/nvidia_metaclass_initializers.py'
    require(sha(helper) == expected['macho_parser_sha256'], 'Mach-O parser identity changed.')
    macho = load_module(helper)
    report_path = artifact / 'kernel-checks/execution-kernel-build.json'
    require(sha(report_path) == expected['native_report_sha256'], 'Not the reviewed checkpoint3 report.')
    report = json.loads(report_path.read_text())
    manifest_path = artifact / 'original-rm/checked-source-manifest.json'
    require(sha(manifest_path) == expected['source_manifest_sha256'], 'Checked source manifest changed.')
    manifest = json.loads(manifest_path.read_text())
    require(manifest['commit'] == expected['commit'] and manifest['file_count'] == 4005
            and manifest['tree_sha256'] == expected['source_tree_sha256']
            and len(manifest['patches']) == 10, 'Not the exact ten-overlay source profile.')
    observed = {}
    for path in sorted(source.rglob('*')):
        require(not path.is_symlink(), 'Source tree contains a symlink.')
        if path.is_dir():
            continue
        require(path.is_file(), 'Source tree contains non-regular content.')
        observed[path.relative_to(source).as_posix()] = {
            'sha256': sha(path), 'mode': '100755' if path.stat().st_mode & 0o111 else '100644'}
    require(observed == manifest['files'], 'Source tree differs from exact composed manifest.')
    for patch in manifest['patches']:
        require(sha(repo / 'packages/nvidia-global-rm' / patch['path']) == patch['sha256'],
                'Reviewed repository patch changed.')
    pattern = re.compile(r'\b(?:' + '|'.join(NAMES) + r')\b')
    inventory, occurrences = [], []
    for relative in sorted(observed):
        path = source / relative
        if path.suffix not in ('.c', '.h', '.cpp', '.hpp', '.inc'):
            continue
        inventory.append([relative, observed[relative]['sha256']])
        text = COMMENTS.sub(lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), path.read_text())
        for match in pattern.finditer(text):
            occurrences.append(dict(source=relative, line=text.count('\n', 0, match.start()) + 1,
                                    symbol=match[0]))
    inventory_sha = hashlib.sha256(json.dumps(inventory).encode()).hexdigest()
    require(len(inventory) == 3957 and inventory_sha == expected['source_inventory_sha256'],
            'Complete compiled-profile source inventory changed.')
    require(occurrences == capsule['evidence']['identifier_occurrences'], 'New caller/address/member use.')
    object_dir = artifact / 'original-rm/checked-namespaced'
    objects = sorted(object_dir.glob('*.o'))
    hashes = report['original_rm']['object_sha256']
    require(len(objects) == len(hashes) == 1100 and report['original_rm']['native_apple_compiler'] is True,
            'Requires all1100 actual Apple-native checkpoint3 original objects.')
    incoming, definitions = [], []
    for path in objects:
        require(sha(path) == hashes[path.name], 'Actual original object changed: ' + path.name)
        image = macho.Object(path, allow_empty_code_without_symbols=True)
        for symbol in image.symbols:
            if symbol.name == TARGET:
                definitions.append(dict(object=path.name, defined=bool(symbol.section),
                                        kind=symbol.kind, address=symbol.value))
        for section in image.sections:
            for rel in raw_relocations(image, section):
                if rel['external'] and image.symbols[rel['symbol']].name == TARGET:
                    incoming.append(dict(object=path.name, section=section.name, relocation=rel))
    require(definitions == capsule['evidence']['rotation_symbol_records'] and not incoming,
            'Rotation definition/binding or incoming code/data reference changed.')
    rotation = object_dir / 'kernel_nvlink.o'
    image = macho.Object(rotation)
    symbol = next(s for s in image.symbols if s.name == TARGET)
    text = image.sections[symbol.section - 1]
    local_incoming = []
    for section in image.sections:
        for rel in raw_relocations(image, section):
            if rel['external'] or image.sections[rel['symbol'] - 1].name != '__text':
                continue
            offset, width = rel['offset'], rel['width']
            raw = int.from_bytes(image.data[section.offset + offset:section.offset + offset + width],
                                 'little', signed=rel['pc_relative'])
            address = raw + (section.address + offset + width + {6: 1, 7: 2, 8: 4}.get(rel['kind'], 0)
                             if rel['pc_relative'] else 0)
            if address == symbol.value:
                local_incoming.append(rel)
    decoder = args.decoder
    if decoder is None:
        llvm = next((shutil.which(name) for name in ('llvm-objdump', 'llvm-objdump-18')
                     if shutil.which(name)), None)
        otool = shutil.which('otool')
        require(llvm is not None or otool is not None, 'Provide --decoder for actual Mach-O instructions.')
        decoder = [llvm, '--macho', '--disassemble', '--no-show-raw-insn'] if llvm else [otool, '-tvV']
    disassembly = subprocess.run([*decoder, str(rotation)], text=True, capture_output=True, check=True).stdout
    # Decode actual instruction boundaries; never search arbitrary code bytes.
    require(sha(repo / 'builders/nvidia_stack_usage.py') == expected['instruction_parser_sha256'],
            'Instruction parser identity changed.')
    sys.path.insert(0, str(repo / 'builders'))
    import nvidia_stack_usage as stack
    relocated = {r['offset'] for r in raw_relocations(image, text)}
    direct_incoming = []
    for instruction in stack.parse_disassembly(disassembly):
        require(instruction['mnemonic'] != '<undecoded>', 'Undecoded machine instruction remains.')
        address = instruction['address']
        offset = address - text.address
        code = image.data[text.offset + offset:text.offset + offset + 6]
        if code[:1] in (b'\xe8', b'\xe9', b'\xeb'):
            relative, width = 1, 1 if code[0] == 0xeb else 4
        elif code and 0x70 <= code[0] <= 0x7f:
            relative, width = 1, 1
        elif len(code) > 1 and code[0] == 0x0f and 0x80 <= code[1] <= 0x8f:
            relative, width = 2, 4
        else:
            continue
        if offset + relative in relocated:
            continue
        destination = address + relative + width + int.from_bytes(code[relative:relative + width], 'little', signed=True)
        if destination == symbol.value:
            direct_incoming.append(instruction)
    require(not local_incoming and not direct_incoming, 'Same-object direct entry reference exists.')
    generated = object_dir / 'g_kernel_nvlink_nvoc.o'
    image = macho.Object(generated)
    export = next(s for s in image.symbols if s.name == '_s540Global___nvoc_export_info__KernelNvlink')
    section = image.sections[export.section - 1]
    offset = export.value - section.address
    end = min((s.value for s in image._defined(export.section) if s.value > export.value),
              default=section.address + section.size)
    atom = image.data[section.offset + offset:section.offset + end - section.address]
    relocs = [r for r in raw_relocations(image, section) if offset <= r['offset'] < end - section.address]
    require(atom == bytes(16) and not relocs, 'KernelNvlink reflection export table changed.')
    bridge = artifact / 'kernel-checks/execution-bridge.o'
    require(sha(bridge) == expected['project_bridge_sha256'] == report['execution_closure']['linked_project_sha256'],
            'Actual project bridge identity changed.')
    image = macho.Object(bridge)
    defined = {s.name[1:] for s in image.symbols if s.kind & 0xe0 == 0 and s.kind & 1 and s.kind & 0xe == 0xe and s.section}
    referenced = {s.name[1:] for s in image.symbols if s.kind == 1 and not s.section and not s.value}
    original = set(report['original_rm']['namespace_contract']['defined'])
    require(not defined & original, 'Project replaces an original definition.')
    roots = sorted((referenced - defined) & original)
    gated = report['execution_closure']['source_gated_global_lifecycle_roots']
    require(roots == capsule['evidence']['compiled_original_roots'] and len(roots) == 23
            and gated == capsule['evidence']['source_gated_roots'] and len(gated) == 2
            and sorted(set(roots) | set(gated)) == report['execution_closure']['original_roots']
            and TARGET[1:] not in roots + gated, 'Actual admitted root set changed.')
    project_refs = []
    project_pattern = re.compile(r'\b(?:s540Global_)?(?:' + '|'.join(NAMES) + r')\b')
    for package in (repo / 'packages').iterdir():
        for path in (package / 'src').rglob('*') if (package / 'src').is_dir() else []:
            if path.suffix in ('.c', '.h', '.cpp', '.hpp') and project_pattern.search(COMMENTS.sub('', path.read_text())):
                project_refs.append(path.relative_to(repo).as_posix())
    require(not project_refs, 'Project production references rotation.')
    result = dict(format=1, status='exact-checkpoint3-selected-rotation-entry-exclusion-rechecked',
        identity=expected, evidence=capsule['evidence'], actual_object_hashes_rechecked=1100,
        actual_source_files_rechecked=4005, actual_source_inventory_files_rechecked=3957,
        external_incoming_relocations=0, local_incoming_relocations=0, direct_incoming_branches=0,
        export_info_bytes=atom.hex(), export_info_relocations=0, compiled_root_count=23,
        source_gated_root_count=2, crypto_operation_implemented=False, whole_crypto_admission=False,
        aggregate_stack_proven=False, kernel_execution='not_tested', gpu_access=False,
        production_candidate_allowed=False)
    encoded = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(encoded)
    print(encoded)


if __name__ == '__main__':
    main()
