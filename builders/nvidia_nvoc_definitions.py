"""Bind the one measured GPU reset NVOC dispatch to actual defining atoms.

Evidence only: receiver initialization/lifetime/alias closure and every callee
and aggregate stack bound remain pending. No stack graph or admission is changed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

import nvidia_metaclass_initializers as macho
import nvidia_nvoc_stack_dispatch as dispatch
import nvidia_stack_usage as stack

FIELD = '__gpuMarkDeviceForReset__'
TARGETS = ['gpuMarkDeviceForReset_395e98', 'gpuMarkDeviceForReset_IMPL']
REGISTERS = ['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi',
             'r8','r9','r10','r11','r12','r13','r14','r15']

def require(value, message):
    if not value:
        raise ValueError(message)

class Paths:
    """Explicit prefix relocation, followed by exact recorded content hashes."""
    def __init__(self, mappings=()):
        self.mappings = []
        for old, new in mappings:
            old = Path(old)
            require(old.is_absolute(), 'Relocation source must be absolute.')
            self.mappings.append((old, Path(new).resolve(strict=True)))
        require(len({str(a) for a,b in self.mappings}) == len(self.mappings), 'Duplicate relocation prefix.')
        self.mappings.sort(key=lambda pair: len(str(pair[0])), reverse=True)
        self.checked = {}

    def path(self, value):
        original = Path(value)
        require(original.is_absolute(), 'Recorded path must be absolute.')
        selected = original
        for old, new in self.mappings:
            if original.is_relative_to(old):
                selected = new / original.relative_to(old)
                break
        return selected.resolve(strict=True)

    def checked_file(self, value, expected):
        path = self.path(value)
        require(path.is_file() and stack.sha(path) == expected, 'Recorded input hash changed: ' + str(path))
        previous = self.checked.setdefault(path, expected)
        require(previous == expected, 'Conflicting identity for one physical input.')
        return path

    def unchanged(self):
        for path, expected in self.checked.items():
            require(stack.sha(path) == expected, 'Input changed during definition proof: ' + str(path))

def descriptors(image):
    """The shared parser omits n_desc; require exact strong/local linkage here."""
    position = 32
    for _ in range(struct.unpack_from('<I', image.data, 16)[0]):
        command, size = struct.unpack_from('<II', image.data, position)
        if command == 2:
            offset, count = struct.unpack_from('<II', image.data, position + 8)
            require(count == len(image.symbols), 'Symbol descriptor count differs.')
            return [struct.unpack_from('<H', image.data, offset + 16*i + 6)[0] for i in range(count)]
        position += size
    require(not image.symbols, 'Missing symbol descriptors.')
    return []

def atom(image, name, *, external):
    found = [(i,s) for i,s in enumerate(image.symbols) if s.name == name]
    require(len(found) == 1, 'Exact target symbol is absent or ambiguous: ' + name)
    index, symbol = found[0]
    require(symbol.kind == (15 if external else 14) and descriptors(image)[index] == 0,
            'Target must have exact strong/local N_SECT linkage: ' + name)
    require(symbol.section != 0, 'Target is not defined code.')
    section = image.sections[symbol.section-1]
    require(section.name == '__text' and section.segment == '__TEXT' and
            section.flags & 0x80000400 and section.address <= symbol.value < section.address+section.size,
            'Target is not an executable text atom: ' + name)
    aliases = sorted(s.name for s in image._defined(symbol.section) if s.value == symbol.value)
    require(aliases == [name], 'Target code aliases require separate review.')
    end = min([s.value for s in image._defined(symbol.section) if s.value > symbol.value],
              default=section.address+section.size)
    begin = symbol.value-section.address
    relocations = []
    for relocation in image.relocations(section):
        if relocation.offset < end-section.address and relocation.offset+relocation.width > begin:
            require(begin <= relocation.offset and relocation.offset+relocation.width <= end-section.address,
                    'Relocation crosses a target atom boundary.')
            target, resolved = image.target(section, relocation)
            # Names alone do not distinguish a weak import, an absolute/common
            # symbol or a different local/external binding. Preserve the actual
            # nlist linkage as well as the parser's exact symbol/addend target.
            target_symbol = image.symbols[relocation.symbol] if relocation.external else resolved
            target_index = None if target_symbol is None else next(
                index for index, candidate in enumerate(image.symbols) if candidate is target_symbol)
            linkage = None if target_symbol is None else {
                'name': target_symbol.name, 'kind': target_symbol.kind,
                'descriptor': descriptors(image)[target_index],
                'section': None if not target_symbol.section else {
                    'name': image.sections[target_symbol.section-1].name,
                    'segment': image.sections[target_symbol.section-1].segment}}
            relocations.append({'offset': relocation.offset-begin, 'width': relocation.width,
                'kind': relocation.kind, 'pc_relative': relocation.pc_relative, 'external': relocation.external,
                'target': target, 'target_linkage': linkage})
    code = image.data[section.offset+begin:section.offset+end-section.address]
    return {'symbol': name, 'section_index': symbol.section, 'section': section.name,
            'start': symbol.value, 'end': end, 'bytes_sha256': hashlib.sha256(code).hexdigest(),
            'relocations': relocations}

def load_manifest(path, paths, *, expected_count=1100):
    manifest = json.loads(path.read_text())
    require(manifest.get('format') == 1 and manifest.get('status') == 'compiler-stack-usage-collected' and
            manifest.get('unit_count') == expected_count and len(manifest['units']) == expected_count,
            'Expected the complete measured object manifest.')
    units, captures, objects = [], set(), set()
    for reference in manifest['units']:
        capture = paths.checked_file(reference['path'], reference['sha256'])
        require(capture not in captures, 'Repeated capture in measured manifest.')
        captures.add(capture)
        unit = json.loads(capture.read_text())
        require(unit.get('status') == 'compiler-stack-usage-captured' and unit.get('format') == 1,
                'Unsupported measured unit.')
        command = unit['command']
        require(isinstance(command, list) and all(isinstance(value, str) for value in command) and
                command.count('-fstack-usage') == command.count('-c') == command.count('-o') == 1 and
                '-fno-stack-usage' not in command,
                'Expected one actual measured compile command.')
        require(hashlib.sha256(json.dumps(command).encode()).hexdigest() == unit['command_sha256'],
                'Measured compiler command identity changed.')
        source = paths.checked_file(unit['source'], unit['source_sha256'])
        obj = paths.checked_file(unit['object'], unit['object_sha256'])
        def command_path(option):
            position = command.index(option) + 1
            require(position < len(command), 'Measured compile command lacks an operand.')
            value = Path(command[position])
            if not value.is_absolute():
                require(unit.get('cwd') and Path(unit['cwd']).is_absolute(),
                        'Relative compile operand lacks a recorded absolute working directory.')
                value = Path(unit['cwd']) / value
            return paths.path(str(value))
        require(command_path('-c') == source and command_path('-o') == obj and
                capture == obj.with_suffix('.stack.json'),
                'Measured command/capture does not identify its exact source and object.')
        require(obj not in objects, 'Repeated object in measured manifest.')
        objects.add(obj)
        image = macho.Object(obj, allow_empty_code_without_symbols=True)
        if unit['usage_file'] is not None:
            usage = paths.checked_file(unit['usage_file'], unit['usage_sha256'])
            require(usage == obj.with_suffix('.su'), 'Measured stack output is not the actual object sidecar.')
            require(stack.parse_usage(usage.read_text()) == unit['functions'], 'Measured frame records changed.')
            definitions = {symbol.name for symbol in image.symbols if symbol.section and
                image.sections[symbol.section-1].name == '__text' and
                symbol.kind & 0xe0 == 0 and symbol.kind & 0x0e == 0x0e}
            require(all(function['symbol'] in definitions for function in unit['functions']),
                    'Measured frame record lacks an actual text definition.')
        else:
            require(unit.get('usage_emission') == 'not-emitted-for-object-without-executable-code' and
                    unit['usage_sha256'] is None and not unit['functions'] and not obj.with_suffix('.su').exists() and
                    not any(s.size and (s.name == '__text' or s.flags & 0x80000400) for s in image.sections),
                    'Absent stack records lack empty-object evidence.')
        units.append({'capture': capture, 'unit': unit, 'object': obj, 'image': image})
    parents = {p.parent for p in objects}
    require(len(parents) == 1 and next(iter(parents)) == path.parent.resolve(), 'Measured object directory is ambiguous.')
    observed = {p.resolve() for p in path.parent.glob('*.o')}
    require(observed == objects, 'Missing or extra measured object files.')
    return units

def unique_external(units, name):
    found = []
    for unit in units:
        image = unit['image']; desc = descriptors(image)
        for index,symbol in enumerate(image.symbols):
            if symbol.name != name:
                continue
            if symbol.section:
                value = atom(image,name,external=True)
                found.append((unit,value))
            else:
                require(symbol.kind == 1 and symbol.value == 0 and desc[index] == 0,
                        'Common, absolute or weak target reference is not admitted.')
    require(len(found) == 1, 'External target requires one exact definition in the measured manifest.')
    return found[0]

def local_identity(actual_image,probe_image,name):
    actual=atom(actual_image,name,external=False)
    probe=atom(probe_image,name,external=False)
    require(all(actual[key]==probe[key] for key in ('bytes_sha256','relocations')),
            'Actual defining local stub differs from the typed probe atom/relocations.')
    return actual

def decode(path, decoder):
    run = subprocess.run([*decoder,str(path)], capture_output=True,text=True,timeout=180)
    require(run.returncode == 0, 'Actual defining-object disassembly failed: '+run.stderr[-1000:])
    return stack.parse_disassembly(run.stdout), hashlib.sha256(run.stdout.encode()).hexdigest()

def initializer_stores(image, initializer, symbols, field_offset, instructions, *, expected_count=5):
    owner = atom(image,initializer,external=True)
    local_atom = atom(image,symbols[0],external=False)
    section = image.sections[owner['section_index']-1]
    insn = {value['address']: value for value in instructions}
    rows=[]
    for relocation in image.relocations(section):
        target,_ = image.target(section,relocation)
        name = target.get('external',target.get('function'))
        if name not in symbols:
            continue
        address = section.address+relocation.offset
        require(owner['start'] <= address and address+relocation.width <= owner['end'],
                'Target reference occurs outside the reviewed initializer.')
        local = name == symbols[0]
        require(relocation.pc_relative and relocation.width == 4 and relocation.kind == (1 if local else 3),
                'Unexpected initializer relocation kind/width/pcrel.')
        if relocation.external:
            symbol = image.symbols[relocation.symbol]
            require(descriptors(image)[relocation.symbol] == 0 and
                    (symbol.kind == 14 and symbol.section if local else symbol.kind == 1 and not symbol.section and symbol.value == 0),
                    'Initializer target linkage is not exact.')
        if local:
            raw_target=int.from_bytes(image.data[section.offset+relocation.offset:
                section.offset+relocation.offset+relocation.width],'little',signed=relocation.pc_relative)
            if relocation.external:
                symbol=image.symbols[relocation.symbol]
                require(symbol.name==symbols[0] and symbol.section==local_atom['section_index'] and raw_target==0,
                        'Local initializer relocation must name the exact zero-addend stub atom.')
                target_address=symbol.value
            else:
                require(relocation.symbol==local_atom['section_index'],'Local initializer target section changed.')
                target_address=raw_target+address+relocation.width
            require(target_address==local_atom['start'],'Local initializer points inside a code atom.')
        else:
            require(target.get('addend') == 0, 'Initializer target has an interior/common addend.')
        start = address-3
        raw = image.data[section.offset+start-section.address:section.offset+start-section.address+14]
        require(owner['start']<=start and start+14<=owner['end'] and len(raw) == 14 and
                start in insn and start+7 in insn and start+14 in insn,
                'Initializer relocation/load/store lacks exact instruction boundaries.')
        rex,opcode,modrm = raw[:3]
        require(rex in (0x48,0x4c) and opcode == (0x8d if local else 0x8b) and modrm & 0xc7 == 5,
                'Initializer is not an exact RIP-relative pointer load.')
        register = ((modrm>>3)&7) + (8 if rex & 4 else 0)
        rex2,opcode2,modrm2 = raw[7:10]
        require(rex2 in (0x48,0x4c) and opcode2 == 0x89 and modrm2 & 0xc7 == 0x87 and
                ((modrm2>>3)&7)+(8 if rex2&4 else 0) == register and
                int.from_bytes(raw[10:14],'little',signed=True) == field_offset,
                'Initializer store has wrong width/register/base/member offset.')
        load,store=insn[start],insn[start+7]
        require(load['mnemonic'] == ('leaq' if local else 'movq') and store['mnemonic']=='movq' and
                re.fullmatch('%'+REGISTERS[register]+r',\s*(?:0x'+format(field_offset,'x')+'|'+str(field_offset)+r')\(%rdi\)',store['operands']),
                'Decoder does not confirm the exact adjacent receiver-member store.')
        rows.append({'relocation_offset':relocation.offset,'kind':relocation.kind,'width':relocation.width,
            'pc_relative':True,'target':target,'load':load,'store':store,'instruction_bytes':raw.hex()})
    require(len(rows)==expected_count and sum(r['target'].get('function')==symbols[0] for r in rows)==1,
            'Reviewed initializer target/store count changed.')
    # Explicit stores of this slot must all be the exact bound stores above.
    slot_stores=[]
    widths={'movb':1,'movw':2,'movl':4,'movq':8,'movups':16,'movaps':16,'movdqa':16,'movdqu':16}
    for instruction in instructions:
        if not owner['start']<=instruction['address']<owner['end']:continue
        operands=instruction['operands'];mnemonic=instruction['mnemonic']
        if mnemonic.startswith(('cmp','test')):continue
        require(not re.search(r',\s*[^ ]*\(%rdi,',operands),'Indexed receiver write requires separate review.')
        destination=re.search(r',\s*(0x[0-9a-f]+|\d+)?\(%rdi\)$',operands)
        if not destination:continue
        require(mnemonic in widths,'Unknown receiver memory operation requires separate review.')
        begin=int(destination[1],0) if destination[1] else 0
        if begin<field_offset+8 and begin+widths[mnemonic]>field_offset:slot_stores.append(instruction)
    require([r['store']['address'] for r in rows]==[i['address'] for i in slot_stores],
            'Extra receiver member store requires separate review.')
    return owner,rows

def prove(proof_path, manifest_path, paths, *, decoder=None, namespace='s540Global_'):
    require(re.fullmatch(dispatch.IDENTIFIER,namespace), 'Expected exact private namespace prefix.')
    proof_sha=stack.sha(proof_path);manifest_sha=stack.sha(manifest_path)
    paths.checked_file(str(proof_path),proof_sha);paths.checked_file(str(manifest_path),manifest_sha)
    tools={str(Path(module.__file__).resolve()):stack.sha(Path(module.__file__)) for module in (macho,dispatch,stack)}
    tools[str(Path(__file__).resolve())]=stack.sha(Path(__file__))
    proof=json.loads(proof_path.read_text())
    require(proof.get('status')=='one-typed-nvoc-dispatch-target-set-established' and
            proof['function']=='kgspRecvPoll_IMPL' and proof['source_catalog']['field']==FIELD and
            proof['source_catalog']['targets']==TARGETS and proof['typed_probe_abi']['field_offset_bytes']==264,
            'This binder only admits the reviewed reset dispatch.')
    units=load_manifest(manifest_path,paths)
    for value,expected in proof['evidence_sha256'].items(): paths.checked_file(value,expected)
    catalog=proof['source_catalog']
    root=paths.path(catalog['source_root']);header=paths.path(catalog['header']);generated=paths.path(catalog['generated'])
    actual=dispatch.catalog(root,header,generated,FIELD)
    for key in ('targets','references','header_sha256','generated_sha256','source_inventory_sha256','source_inventory_file_count'):
        require(actual[key]==catalog[key], 'Typed source catalog identity changed: '+key)
    probes=[paths.path(p) for p in proof['evidence_sha256'] if Path(p).name=='typed-nvoc-probe.o']
    require(len(probes)==1,'Expected one measured typed probe object.')
    probe=macho.Object(probes[0])
    require(dispatch.probe_object(probes[0],TARGETS,namespace=namespace)==proof['typed_probe_abi'], 'Typed probe ABI changed.')
    generated_units=[u for u in units if paths.path(u['unit']['source'])==generated]
    require(len(generated_units)==1,'Generated initializer defining unit is ambiguous.')
    owner_unit=generated_units[0]
    local_name='_'+TARGETS[0];external_name='_'+namespace+TARGETS[1]
    local=local_identity(owner_unit['image'],probe,local_name)
    external_unit,external=unique_external(units,external_name)
    decoder=decoder or ['/usr/bin/xcrun','otool','-tv']
    instructions,decoder_sha=decode(owner_unit['object'],decoder)
    initializer,stores=initializer_stores(owner_unit['image'],'_'+namespace+'__nvoc_init_funcTable_OBJGPU',
        [local_name,external_name],264,instructions)
    capture=paths.checked_file(proof['stack_capture']['path'],proof['stack_capture']['sha256'])
    callers=[u for u in units if u['capture']==capture]
    require(len(callers)==1,'Measured caller is not in the same complete manifest.')
    caller=callers[0];caller_atom=atom(caller['image'],'_'+namespace+proof['function'],external=True)
    caller_instructions,caller_decoder_sha=decode(caller['object'],decoder)
    site=proof['machine_site'];sites=[i for i in caller_instructions if i['address']==site['address']]
    require(len(sites)==1 and sites[0]['mnemonic']+' '+sites[0]['operands']==site['instruction'] and
            caller_atom['start']<=site['address']<caller_atom['end'] and
            site['address']-caller_atom['start']==proof['machine_offset_in_function'], 'Measured indirect machine site changed.')
    paths.unchanged()
    for path,expected in tools.items():require(stack.sha(Path(path))==expected,'Definition binder changed during proof.')
    return {'format':1,'status':'one-nvoc-target-definition-binding-established',
        'scope':'exact definitions in this complete measured object manifest only',
        'proof_sha256':proof_sha,'manifest_sha256':manifest_sha,'tool_sha256':tools,
        'manifest_object_count':len(units),'verified_input_count':len(paths.checked),
        'source_catalog':actual,'function':proof['function'],'machine_site':site,'field_offset_bytes':264,
        'local_target':{'object':str(owner_unit['object']),'object_sha256':owner_unit['unit']['object_sha256'],
                        'capture_sha256':stack.sha(owner_unit['capture']),'source_sha256':owner_unit['unit']['source_sha256'],**local},
        'external_target':{'object':str(external_unit['object']),'object_sha256':external_unit['unit']['object_sha256'],
                           'capture_sha256':stack.sha(external_unit['capture']),'source_sha256':external_unit['unit']['source_sha256'],**external},
        'initializer':initializer,'actual_initializer_stores':stores,
        'decoder_output_sha256':decoder_sha,'caller_decoder_output_sha256':caller_decoder_sha,
        'target_definition_binding':'established-for-measured-manifest',
        'receiver_ownership_and_initialization':'pending; factory dominance, lifetime, aliases and external/project writers not proved',
        'callee_stack_bounds':'not_established','aggregate_stack_proven':False,
        'stack_graph_updated':False,'kernel_execution':'not_tested','production_candidate_allowed':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('proof','manifest','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--path-map',action='append',default=[],metavar='OLD=NEW')
    parser.add_argument('--llvm-objdump',type=Path)
    args=parser.parse_args()
    paths=Paths([value.split('=',1) for value in args.path_map])
    decoder=([str(args.llvm_objdump),'--macho','--disassemble','--no-show-raw-insn','--no-symbolic-operands'] if args.llvm_objdump else None)
    output=args.output.resolve()
    require(not output.exists(),'Fresh evidence output required.')
    source_root=paths.path(json.loads(args.proof.read_text())['source_catalog']['source_root'])
    require(not output.is_relative_to(source_root),'Definition evidence must not modify the reviewed source tree.')
    result=prove(args.proof.resolve(strict=True),args.manifest.resolve(strict=True),paths,decoder=decoder)
    output.parent.mkdir(parents=True,exist_ok=True);stack.write(output,result)
    print(json.dumps({'path':str(output),'sha256':stack.sha(output),'aggregate_stack_proven':False}))

if __name__=='__main__':main()
