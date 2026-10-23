#!/usr/bin/env python3
"""Parser refusals and actual SDK cross-codegen controls, never native evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import struct
import subprocess
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'builders'))
import compose_nvidia_first_transaction as composer
import link_nvidia_first_transaction as old
link=composer.load('s540_image_control_linker',HERE/'link_native.py')

def run(args):
    args.cc=args.cc.absolute()
    args.cxx=args.cxx.absolute()
    out=args.output.absolute()
    if out.exists():raise ValueError('Fresh experimental image control output required')
    out.mkdir(parents=True)
    checks=[]
    def refuse(label,callback):
        try:callback()
        except ValueError:checks.append(label)
        else:raise AssertionError('Missing refusal: '+label)
    if sys.platform!='darwin' or platform.machine()!='x86_64':
        unused=out/'native-must-not-exist'
        empty=SimpleNamespace(output=unused,native_compilation=unused)
        refuse('native-compiler-refuses-before-write-on-non-Intel-Apple-host',
            lambda:link.native.compile_verified_plan(empty,{},lambda: (_ for _ in ()).throw(AssertionError('callback must not execute'))))
        refuse('native-linker-refuses-before-write-on-non-Intel-Apple-host',
            lambda:link.link_verified_plan(empty,{},lambda: (_ for _ in ()).throw(AssertionError('callback must not execute'))))
        assert not unused.exists()
    row=lambda **kw:{'strong':[],'weak':[],'imports':[],**kw}
    input_optional=old.audit_symbols({'dormant':row(imports=['s540Global_dormant'])},set(),
        require_private_closure=False,require_reviewed_public=False)
    assert input_optional['unresolved_original_private']==['s540Global_dormant']
    checks.append('input-phase-retains-dormant-private-import-as-diagnostic')
    refuse('final-private-import-never-whitelisted',lambda:old.audit_symbols(
        {'live':row(imports=['s540Global_dormant'])},{'s540Global_dormant'}))
    refuse('duplicate-strong-owner',lambda:old.audit_symbols(
        {'first':row(strong=['s540Real']),'second':row(strong=['s540Real'])},set()))
    refuse('final-unreviewed-public-import',lambda:old.audit_symbols(
        {'live':row(imports=['UnreviewedOperation'])},set()))
    flags,cpp=old.kernel_flags(args.kernel_sdk.resolve(strict=True))
    cpp=[*cpp,'-fcheck-new']
    cross=['-target','x86_64-apple-macos15',*flags[3:]]
    include=composer.include_flags(args.composition.resolve(strict=True))
    def execute(command,label):
        command=[str(v) for v in command]
        result=subprocess.run(command,text=True,capture_output=True,timeout=180)
        (out/(label+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise ValueError(label+' actual cross compiler failed: '+result.stderr[-4000:])
        return result
    source=HERE.parent/'prospective-experimental-target-control/tests/sdk_experimental_metaclass_reference.cpp'
    reference=out/'actual-sdk-experimental-registration.o'
    execute([args.cxx,*cross,*cpp,*include,'-c',source,'-o',reference],'sdk-registration')
    registration=link.classes.loader_graph(reference,reference)
    checks.append('actual-two-experimental-SDK-registration-reference')
    decoder=args.cc.parent/'llvm-objdump'
    decoded=execute([decoder,'--macho','--disassemble','--no-show-raw-insn',reference],'sdk-registration-decode').stdout
    def null_branch(text,spelling):
        function=text.split(spelling,1)[1].split('\n__',1)[0]
        allocation=function.index('__ZN8OSObjectnwEm')
        constructor=function.index('callq',allocation+len('__ZN8OSObjectnwEm'))
        between=function[allocation:constructor]
        return 'testq' in between and ('\tje\t' in between or '\tjz\t' in between)
    for name in link.classes.CLASSES:
        assert null_branch(decoded,'__ZNK'+str(len(name))+name+'9MetaClass5allocEv:')
    power_reference=out/'actual-sdk-power-registration.o'
    execute([args.cxx,*cross,*cpp,*include,'-c',link.power.REFERENCE,'-o',power_reference],'sdk-power-registration')
    link.power._review_reference(link.power.Object(power_reference).loader_graph())
    power_decoded=execute([decoder,'--macho','--disassemble','--no-show-raw-insn',power_reference],'sdk-power-registration-decode').stdout
    assert null_branch(power_decoded,'__ZNK18S540GspPowerKernel25S540NvidiaGspPowerService9MetaClass5allocEv:')
    checks.append('actual-SDK-metaclass-allocation-null-branches-retained')
    unchecked=out/'missing-null-check-flag.o'
    execute([args.cxx,*cross,*[v for v in cpp if v!='-fcheck-new'],*include,'-c',source,'-o',unchecked],
        'sdk-registration-without-null-check-policy')
    unchecked_decoded=execute([decoder,'--macho','--disassemble','--no-show-raw-insn',unchecked],
        'sdk-registration-unchecked-decode').stdout
    assert all(not null_branch(unchecked_decoded,'__ZNK'+str(len(name))+name+'9MetaClass5allocEv:') for name in link.classes.CLASSES)
    checks.append('actual-compiler-negative-control-detects-removed-new-null-check-policy')
    protocol_source=HERE.parent/'prospective-experimental-target-control/tests/sdk_experimental_protocol_reference.c'
    protocol_object=out/'actual-sdk-protocol.o'
    execute([args.cc,*cross,'-std=c11',*include,'-I',HERE.parent/'prospective-runtime-coordinator',
        '-c',protocol_source,'-o',protocol_object],'sdk-protocol-layout')
    protocol_image=old.Image(protocol_object,1)
    symbol=protocol_image.named('_s540ExperimentalProtocolOffsets')
    section=protocol_image.sections[symbol['section']-1]
    offset=section['offset']+symbol['value']-section['address']
    protocol_offsets=list(struct.unpack_from('<13I',protocol_image.data,offset))
    assert protocol_offsets[:2]==[144,80] and protocol_offsets[3:]==[104,8,16,32,64,96,128,72,8,56]
    assert protocol_offsets[2]>=256 and protocol_offsets[2]%8==0
    checks.append('actual-SDK-request-identity-native-profile-C-offsets')
    image=old.Image(reference,1)
    initializer=next(s for s in image.symbols if s['name'].startswith('__GLOBAL__sub_I_'))
    text=image.sections[initializer['section']-1]
    data=bytearray(reference.read_bytes());data[text['offset']+initializer['value']-text['address']]^=1
    mutation=out/'changed-instruction.o';mutation.write_bytes(data)
    refuse('changed-registration-instruction',lambda:link.classes.loader_graph(mutation,reference))
    data=bytearray(reference.read_bytes())
    needle=b'S540ExperimentalTargetControl\0'
    strings=next(s for s in image.sections if s['name']=='__cstring')
    location=data.index(needle,strings['offset'],strings['offset']+strings['size'])
    data[location]=ord('X')
    altered=bytes(data)
    mutation=out/'unreviewed-class-name.o';mutation.write_bytes(altered)
    refuse('self-reference-cannot-admit-unreviewed-class-name',lambda:link.classes.loader_graph(mutation,mutation))
    layout,layout_ref=link.sdk_kmod_layout(out,args.cc,cross,execute)
    assert layout['info_version']==1 and layout['name_bytes']==layout['version_bytes']==64
    assert layout['size']>layout['stop_offset']>=layout['start_offset']+8
    checks.append('actual-pinned-SDK-kmod-offsets')
    codec=composer.load('s540_image_control_profile',HERE.parent/'prospective-runtime-coordinator/profile.py')
    profile=codec.encode_profile('12'*32,16384,16384)
    (out/'native-profile.bin').write_bytes(profile)
    assembly=out/'profile-control.S'
    assembly.write_text('.section __TEXT,__s540_trial,regular\n.p2align 3\n'
        '.globl _s540ExperimentalNativeProfileBegin\n.globl _s540ExperimentalNativeProfileEnd\n'
        '_s540ExperimentalNativeProfileBegin:\n.incbin "native-profile.bin"\n'
        '_s540ExperimentalNativeProfileEnd:\n.subsections_via_symbols\n')
    obj=out/'actual-profile.o'
    result=subprocess.run([str(args.cc),'-target','x86_64-apple-macos15','-c',str(assembly),'-o',str(obj)],
        cwd=out,text=True,capture_output=True,timeout=180)
    (out/'profile-control.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stderr
    link.verify_endpoint(old.Image(obj,1),'s540ExperimentalNativeProfileBegin',
        's540ExperimentalNativeProfileEnd','__s540_trial',profile)
    checks.append('actual-immutable104B-profile-typed-endpoints')
    # Explicit parser-only final-container fixtures preserve the actual
    # assembled payload. Their modified headers are never native link proof.
    readonly=bytearray(obj.read_bytes());struct.pack_into('<I',readonly,12,11)
    segment=32
    assert struct.unpack_from('<I',readonly,segment)[0]==0x19
    readonly[segment+8:segment+24]=b'__TEXT'+b'\0'*10
    struct.pack_into('<II',readonly,segment+56,5,5)
    container=out/'synthetic-final-profile-readonly.macho';container.write_bytes(readonly)
    link.verify_endpoint(old.Image(container,11),'s540ExperimentalNativeProfileBegin',
        's540ExperimentalNativeProfileEnd','__s540_trial',profile)
    writable=bytearray(readonly);struct.pack_into('<II',writable,segment+56,7,7)
    mutation=out/'synthetic-final-profile-writable.macho';mutation.write_bytes(writable)
    refuse('synthetic-final-container-rejects-writable-payload-segment',lambda:link.verify_endpoint(
        old.Image(mutation,11),'s540ExperimentalNativeProfileBegin','s540ExperimentalNativeProfileEnd','__s540_trial',profile))
    disguised=bytearray(readonly)
    count,length=struct.unpack_from('<II',disguised,16)
    position=32
    for _ in range(count):
        command,size=struct.unpack_from('<II',disguised,position)
        if command==0x19:
            disguised[position+8:position+24]=b'__DATA'+b'\0'*10
            struct.pack_into('<II',disguised,position+56,3,3)
            fileoff=struct.unpack_from('<Q',disguised,position+40)[0]
            struct.pack_into('<Q',disguised,position+40,fileoff+72)
            for index in range(struct.unpack_from('<I',disguised,position+64)[0]):
                section=position+72+80*index
                for offset in (48,56):
                    value=struct.unpack_from('<I',disguised,section+offset)[0]
                    if value:struct.pack_into('<I',disguised,section+offset,value+72)
        elif command==2:
            for offset in (8,16):
                value=struct.unpack_from('<I',disguised,position+offset)[0]
                struct.pack_into('<I',disguised,position+offset,value+72)
        position+=size
    struct.pack_into('<II',disguised,16,count+1,length+72)
    empty_text=struct.pack('<II16sQQQQIIII',0x19,72,b'__TEXT',0x1000,0,0,0,5,5,0,0)
    disguised[32+length:32+length]=empty_text
    mutation=out/'synthetic-final-profile-wrong-owning-segment.macho';mutation.write_bytes(disguised)
    refuse('synthetic-final-container-rejects-false-readonly-section-membership',lambda:link.verify_endpoint(
        old.Image(mutation,11),'s540ExperimentalNativeProfileBegin','s540ExperimentalNativeProfileEnd','__s540_trial',profile))
    bad=bytearray(profile);bad[8]^=1
    refuse('native-profile-byte-drift',lambda:link.verify_endpoint(old.Image(obj,1),
        's540ExperimentalNativeProfileBegin','s540ExperimentalNativeProfileEnd','__s540_trial',bytes(bad)))
    refuse('native-profile-wrong-end-symbol',lambda:link.verify_endpoint(old.Image(obj,1),
        's540ExperimentalNativeProfileBegin','s540ExperimentalNativeProfileBegin','__s540_trial',profile))
    report=dict(format=1,status='passed-current-experimental-image-host-controls',checks=checks,
        check_count=len(checks),actual_sdk_registration=registration,actual_sdk_kmod_layout=layout,
        sdk_layout_reference=layout_ref,compiler_version=execute([args.cc,'--version'],'compiler-version').stdout.splitlines()[0],
        native_darwin_compilation=False,host_control=True,final_image_linked=False,module_loaded=False,
        gpu_access=False,original_entry_admission=False,production_candidate_allowed=False,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__),HERE/'link_native.py',HERE/'metaclasses.py',
                      HERE.parent/'prospective-native-target-preparation/compile_native.py',source)})
    (out/'results.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','composition','kernel-sdk','cc','cxx'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args),sort_keys=True))

if __name__=='__main__':main()
