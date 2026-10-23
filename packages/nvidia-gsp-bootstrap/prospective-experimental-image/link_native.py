#!/usr/bin/env python3
"""Link an independently replayed experimental source plan on Intel macOS.

The complete ld-r input is audited without dead stripping. Dormant unresolved
imports may remain there; the actual final kext must have exact private closure
and only public SDK-declared, KPI-exported imports. No kernel is loaded here.
"""
from __future__ import annotations

from copy import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'builders'))
import compose_nvidia_first_transaction as composer
import link_nvidia_first_transaction as old
import embed_nvidia_firmware as firmware
import nvidia_metaclass_initializers as power
import nvidia_public_kpi_exports as public
native=composer.load('s540_experimental_native_compile',HERE.parent/'prospective-native-target-preparation/compile_native.py')
classes=composer.load('s540_experimental_metaclasses',HERE/'metaclasses.py')
FRONT='packages/nvidia-gsp-bootstrap/prospective-experimental-target-control/'
RUNTIME=HERE.parent/'prospective-runtime-coordinator'
DENIED=dict(native.DENIED,installable_bundle_created=False,target_kernel_admission_proven=False,
            acceleration_test=False,system_security_changed=False)
BUNDLE_ID='org.osx86.S540ExperimentalInit'
VERSION='0.0.1'


def require(value,message):
    if not value: raise ValueError(message)


def write(path,value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')


def helper_hashes():
    paths=[Path(__file__),HERE/'metaclasses.py',RUNTIME/'profile.py',
        *[ROOT/'builders'/name for name in ('link_nvidia_first_transaction.py',
        'embed_nvidia_firmware.py','nvidia_metaclass_initializers.py',
        'nvidia_combined_metaclasses.py','nvidia_public_kpi_exports.py')],
        HERE.parent/'prospective-native-target-preparation/compile_native.py',
        HERE.parent/'prospective-aggregate-stack-closure/check.py',
        HERE.parent/'prospective-aggregate-stack-closure/native_budget.py']
    return {str(path):composer.sha(path) for path in paths}


def contained(root,name):
    path=Path(name)
    path=path if path.is_absolute() else root/composer.checked_relative(name)
    require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)) and
            path.resolve().is_relative_to(root.resolve()),'An image artifact escaped its exact ordinary build directory')
    return path.resolve()


def section_bytes(image,name,segment='__TEXT'):
    found=[s for s in image.sections if s['name']==name and s['segment']==segment]
    require(len(found)==1,'One exact immutable image section is required: '+name)
    section=found[0]
    require(section['flags']&0xff==0,'An immutable image section has an unexpected loader type')
    if image.kind==11:
        position=32;segments=[];ordinal_base=0;owners=[]
        wanted_ordinal=image.sections.index(section)+1
        for _ in range(struct.unpack_from('<I',image.data,16)[0]):
            command,size=struct.unpack_from('<II',image.data,position)
            if command==0x19:
                actual_name=image.data[position+8:position+24].split(b'\0',1)[0].decode('ascii')
                maximum,initial=struct.unpack_from('<II',image.data,position+56)
                count=struct.unpack_from('<I',image.data,position+64)[0]
                if actual_name==segment:segments.append((maximum,initial))
                if ordinal_base<wanted_ordinal<=ordinal_base+count:
                    vmaddr,vmsize,fileoff,filesize=struct.unpack_from('<4Q',image.data,position+24)
                    owners.append(actual_name)
                    require(actual_name==segment and vmaddr<=section['address'] and
                        section['address']+section['size']<=vmaddr+vmsize and fileoff<=section['offset'] and
                        section['offset']+section['size']<=fileoff+filesize,
                        'Actual immutable section is outside its owning read-only segment ranges')
                ordinal_base+=count
            position+=size
        require(owners==[segment] and len(segments)==1 and not segments[0][0]&2 and not segments[0][1]&2 and segments[0][1]&1,
                'Actual final immutable payload is inside a writable or ambiguous segment')
    return section,image.data[section['offset']:section['offset']+section['size']]


def verify_endpoint(image,begin,end,section_name,expected_bytes):
    section,data=section_bytes(image,section_name)
    b,e=image.named('_'+begin),image.named('_'+end)
    ordinal=image.sections.index(section)+1
    require(b['section']==e['section']==ordinal and b['value']==section['address'] and
        e['value']==section['address']+section['size'] and data==expected_bytes,
        'Typed immutable array boundaries differ from exact bytes: '+section_name)
    return dict(section='__TEXT,'+section_name,begin=begin,end=end,bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def firmware_endpoints(image,assets):
    return {filename:verify_endpoint(image,prefix+'_begin',prefix+'_end',section,
        (assets/filename).read_bytes()) for section,(filename,prefix) in firmware.SECTIONS.items()}


def pointer_at(image,name):
    symbol=image.named(name)
    section=image.sections[symbol['section']-1]
    offset=section['offset']+symbol['value']-section['address']
    require(section['address']<=symbol['value']<=section['address']+section['size']-8,
            'An exact pointer symbol escaped its section')
    return struct.unpack_from('<Q',image.data,offset)[0]


def verify_kmod(image,layout):
    required=('size','info_version_offset','name_offset','name_bytes','version_offset','version_bytes','start_offset','stop_offset','info_version')
    require(set(layout)==set(required) and all(type(v) is int and v>=0 for v in layout.values()),'Independent actual SDK kmod layout is incomplete')
    symbol=image.named('_kmod_info')
    section=image.sections[symbol['section']-1]
    start=section['offset']+symbol['value']-section['address']
    require(section['address']<=symbol['value'] and symbol['value']+layout['size']<=section['address']+section['size'],
            'Actual kmod_info extends beyond its data section')
    data=image.data[start:start+layout['size']]
    def field(name):return data[layout[name+'_offset']:layout[name+'_offset']+layout[name+'_bytes']]
    require(field('name')==BUNDLE_ID.encode()+b'\0'*(layout['name_bytes']-len(BUNDLE_ID)) and
        field('version')==VERSION.encode()+b'\0'*(layout['version_bytes']-len(VERSION)),
        'Actual SDK module name/version bytes differ from the experimental bundle')
    require(struct.unpack_from('<I',data,layout['info_version_offset'])[0]==layout['info_version'],
            'Actual kmod_info version differs from its independent SDK declaration')
    require(struct.unpack_from('<Q',data,layout['start_offset'])[0]==image.code('__start')['value'] and
        struct.unpack_from('<Q',data,layout['stop_offset'])[0]==image.code('__stop')['value'],
        'Actual SDK module entry pointers differ from real C libkmod wrappers')
    require(pointer_at(image,'__realmain')==image.code('_s540_prospective_start')['value'] and
        pointer_at(image,'__antimain')==image.code('_s540_prospective_stop')['value'],
        'Actual C libkmod main/antimain pointers do not select the reviewed experimental backends')
    return dict(status='matched-independent-sdk-kmod-layout',bundle_id=BUNDLE_ID,version=VERSION,
                sdk_layout=layout,real_c_wrappers=True,legacy_libkmod_cpp_used=False)


def sdk_kmod_layout(output,cc,flags,execute):
    source=output/'sdk-kmod-layout.c'
    source.write_text('#include <mach/kmod.h>\n'
        'const unsigned long long s540ExperimentalSdkKmodLayout[] = {'
        'sizeof(kmod_info_t), __builtin_offsetof(kmod_info_t,info_version),'
        '__builtin_offsetof(kmod_info_t,name), sizeof(((kmod_info_t*)0)->name),'
        '__builtin_offsetof(kmod_info_t,version), sizeof(((kmod_info_t*)0)->version),'
        '__builtin_offsetof(kmod_info_t,start), __builtin_offsetof(kmod_info_t,stop), KMOD_INFO_VERSION};\n')
    obj=output/'sdk-kmod-layout.o'
    execute([cc,*flags,'-std=c11','-MD','-MF',obj.with_suffix('.d'),'-c',source,'-o',obj],'sdk-kmod-layout')
    power.verify_no_initializers(obj)
    parsed=old.Image(obj,1)
    symbol=parsed.named('_s540ExperimentalSdkKmodLayout')
    section=parsed.sections[symbol['section']-1]
    offset=section['offset']+symbol['value']-section['address']
    values=struct.unpack_from('<9Q',parsed.data,offset)
    names=('size','info_version_offset','name_offset','name_bytes','version_offset','version_bytes','start_offset','stop_offset','info_version')
    return dict(zip(names,values)),dict(source=source.name,source_sha256=composer.sha(source),
        object=obj.name,object_sha256=composer.sha(obj),
        dependency_sha256=native.dependencies(obj.with_suffix('.d'),source,output,output,output,cc))


def power_reference_source(output,composed):
    """Instantiate only the reviewed SDK macro against current class layout.

    The shared Service declaration itself is unchanged. Its embedded Protocol
    type lives in the composed Power.hpp and gained the genuine cancellation
    coupling fields. A reference under ROOT would quote-include the historical
    Protocol instead and attest a stale sizeof(Service). Keep the exact macro
    and class declaration, relocate only that include, and bind both actual
    composed headers in the compiler dependency inventory.
    """
    declaration_relative=power.CLASS_HEADER.relative_to(ROOT).as_posix()
    protocol_relative='packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.hpp'
    manifest=composer.verify_composition(composed)
    declaration=composed/'project'/declaration_relative
    protocol=composed/'project'/protocol_relative
    for relative,path in ((declaration_relative,declaration),(protocol_relative,protocol)):
        require(path.is_file() and not path.is_symlink() and
            composer.sha(path)==manifest['project_files'][relative]['sha256'],
            'Current Power SDK declaration differs from the exact composed source inventory')
    require(declaration.read_bytes()==power.CLASS_HEADER.read_bytes(),
            'The shared Power service declaration needs a separate explicit review')
    authored=power.REFERENCE.read_text()
    source=re.sub(r'/\*.*?\*/|//[^\n]*','',authored,flags=re.S)
    require(re.findall(r'^\s*#include\s+"([^"\n]+)"\s*$',source,flags=re.M)==
        ['../platform/S540NvidiaGspPowerService.hpp'],
        'The independent Power reference must include only its reviewed shared declaration')
    body=re.sub(r'^\s*#include[^\n]*$','',source,flags=re.M)
    expected='namespace S540GspPowerKernel { OSDefineMetaClassAndStructors(S540NvidiaGspPowerService, IOService); }'
    require(re.sub(r'\s+','',body)==re.sub(r'\s+','',expected),
        'The independent Power reference must instantiate only the reviewed SDK macro')
    path=output/'sdk-current-power-metaclass-reference.cpp'
    require(not path.exists(),'Current Power SDK reference source must be fresh')
    path.write_text(authored.replace('#include "../platform/S540NvidiaGspPowerService.hpp"',
        '#include "'+str(declaration)+'"'))
    return path,dict(authored_reference_source=str(power.REFERENCE),
        authored_reference_source_sha256=composer.sha(power.REFERENCE),
        class_declaration=str(declaration),class_declaration_sha256=composer.sha(declaration),
        embedded_protocol_declaration=str(protocol),embedded_protocol_declaration_sha256=composer.sha(protocol))


def sdk_references(output,composed,native_home,cc,cxx,sdk,project_rows,include,execute):
    flags,cpp=old.kernel_flags(sdk)
    cpp=[*cpp,'-fcheck-new']
    authored=[
        'packages/nvidia-darwin-services/tests/sdk_import_reference.cpp',
        'packages/nvidia-global-rm/tests/sdk_import_reference.cpp',
        'packages/nvidia-device-transport/tests/sdk_import_reference.cpp',
        'packages/nvidia-gsp-bootstrap/platform/tests/sdk_import_reference.cpp',
        'packages/nvidia-gsp-bootstrap/platform/tests/sdk_power_reference.cpp',
        'packages/nvidia-gsp-bootstrap/tests/sdk_dispatcher_reference.cpp',
        'packages/nvidia-gsp-bootstrap/prospective-public-callback-closure/tests/sdk_import_reference.cpp',
        FRONT+'tests/sdk_experimental_operations_reference.cpp']
    approved={name[1:] for name in old.transport.ADAPTER_IMPORTS}
    records={}
    for label,text in (('hardware-transport',old.transport.HARDWARE_IMPORT_REFERENCE),
                       ('rm-services',old.transport.SERVICES_IMPORT_REFERENCE)):
        source=output/('sdk-authored-'+label+'.cpp')
        source.write_text(text)
        authored.append(str(source))
    for index,name in enumerate(authored):
        path=Path(name)
        if not path.is_absolute():
            composed_source=composed/'project'/path
            path=composed_source if composed_source.is_file() else ROOT/path
        obj=output/('sdk-operation-%02d.o'%index)
        execute([cxx,*flags,*cpp,*include,'-MD','-MF',obj.with_suffix('.d'),'-c',path,'-o',obj],'sdk-operation-%02d'%index)
        power.verify_no_initializers(obj)
        defined,imports,_=composer.original.macho_symbols(obj)
        approved.update(imports)
        records[name]=dict(source=str(path),source_sha256=composer.sha(path),object=obj.name,
            object_sha256=composer.sha(obj),definitions=sorted(defined),imports=sorted(imports),
            dependency_sha256=native.dependencies(obj.with_suffix('.d'),path,composed/'project',composed,sdk,cxx,
                authored_reference=True))
    power_ref=output/'sdk-power-metaclass-reference.o'
    power_source,power_source_bindings=power_reference_source(output,composed)
    execute([cxx,*flags,*cpp,*include,'-MD','-MF',power_ref.with_suffix('.d'),
        '-c',power_source,'-o',power_ref],'sdk-power-metaclasses')
    power._review_reference(power.Object(power_ref).loader_graph())
    front_source=composed/'project'/FRONT/'tests/sdk_experimental_metaclass_reference.cpp'
    require(front_source.is_file(),'Current composed experimental metaclass SDK reference is missing')
    front_ref=output/'sdk-experimental-metaclasses.o'
    execute([cxx,*flags,*cpp,*include,'-MD','-MF',front_ref.with_suffix('.d'),'-c',front_source,'-o',front_ref],'sdk-experimental-metaclasses')
    lookup={r['source']:native_home/'project-objects'/r['object'] for r in project_rows}
    actual_power=lookup[native.POWER]
    inherited,private=power.framework_imports(actual_power,power_ref)
    approved.update(n[1:] for n in inherited)
    kernel=FRONT+'S540ExperimentalTargetKernel.cpp'
    require(kernel in lookup,'Only the current exact experimental kernel may supply metaclasses')
    classes.loader_graph(lookup[kernel],front_ref)
    defined,_,_=composer.original.macho_symbols(lookup[kernel],reviewed_project_initializers=True)
    _,imports,_=composer.original.macho_symbols(front_ref,reviewed_project_initializers=True)
    private_prefixes=tuple(prefix+str(len(name))+name for prefix in ('_ZN','_ZNK') for name in classes.CLASSES)
    project_private={n for n in imports if n.startswith(private_prefixes)}
    require(project_private<=defined,'Experimental SDK registration reference requires an unimplemented project override')
    ancestors=('OSMetaClass','OSMetaClassBase','OSObject','IORegistryEntry','IOService','IOUserClient')
    framework_prefixes=tuple(prefix+str(len(name))+name for prefix in ('_ZN','_ZNK') for name in ancestors)
    framework=imports-project_private
    require(all(n.startswith(framework_prefixes) for n in framework),'Experimental SDK metaclass imports escaped exact IOKit ancestry')
    approved.update(framework)
    power_dependencies=native.dependencies(power_ref.with_suffix('.d'),power_source,composed/'project',composed,sdk,cxx)
    require(all(path in power_dependencies for path in (power_source_bindings['class_declaration'],
        power_source_bindings['embedded_protocol_declaration'])),
        'Current Power SDK compiler dependencies omitted a composed class/layout header')
    records['power-metaclass']=dict(source=str(power_source),source_sha256=composer.sha(power_source),
        object=power_ref.name,object_sha256=composer.sha(power_ref),imports=sorted(n[1:] for n in inherited),
        private_project_dependencies=sorted(private),**power_source_bindings,dependency_sha256=power_dependencies)
    records['experimental-metaclasses']=dict(source=str(front_source),source_sha256=composer.sha(front_source),
        object=front_ref.name,object_sha256=composer.sha(front_ref),imports=sorted(framework),
        private_project_dependencies=sorted(project_private),
        dependency_sha256=native.dependencies(front_ref.with_suffix('.d'),front_source,composed/'project',composed,sdk,cxx))
    protocol_source=composed/'project'/FRONT/'tests/sdk_experimental_protocol_reference.c'
    protocol_object=output/'sdk-experimental-protocol.o'
    execute([cc,*flags,'-std=c11',*include,'-MD','-MF',protocol_object.with_suffix('.d'),
        '-c',protocol_source,'-o',protocol_object],'sdk-experimental-protocol')
    power.verify_no_initializers(protocol_object)
    protocol_image=old.Image(protocol_object,1)
    protocol_symbol=protocol_image.named('_s540ExperimentalProtocolOffsets')
    protocol_section=protocol_image.sections[protocol_symbol['section']-1]
    protocol_offset=protocol_section['offset']+protocol_symbol['value']-protocol_section['address']
    offsets=list(struct.unpack_from('<13I',protocol_image.data,protocol_offset))
    require(offsets[:2]==[144,80] and offsets[3:]==[104,8,16,32,64,96,128,72,8,56] and
        offsets[2]>=256 and offsets[2]%8==0,
        'Independent actual SDK wire/build-identity/native-profile offsets differ from the typed ABI')
    records['experimental-protocol-layout']=dict(source=str(protocol_source),source_sha256=composer.sha(protocol_source),
        object=protocol_object.name,object_sha256=composer.sha(protocol_object),offsets=offsets,
        dependency_sha256=native.dependencies(protocol_object.with_suffix('.d'),protocol_source,
            composed/'project',composed,sdk,cc))
    return approved,records,power_ref,front_ref


def verify_final_image(path,approved,loader_entries,profile_bytes,assets,layout):
    image=old.Image(path,11)
    audit=old.audit_symbols({path.name:image.externals()},set(approved))
    exports=public.audit_imports(audit['public_imports'],public.IDLE_LIBRARIES)
    require(old.verify_final_exports(image)==['kmod_info'],'Only module metadata may be exported')
    return dict(imports=audit['public_imports'],symbol_audit=audit,public_kpi=exports,
        roots=old.verify_roots(path,expected_type=11),
        loader_pointers=old.verify_final_loader_pointers(path,loader_entries),
        firmware=firmware.verify_embedded_firmware(path),firmware_endpoints=firmware_endpoints(image,assets),
        native_profile=verify_endpoint(image,'s540ExperimentalNativeProfileBegin',
            's540ExperimentalNativeProfileEnd','__s540_trial',profile_bytes),kmod=verify_kmod(image,layout))


def link_verified_plan(args,value,verify_callback,*,companion_include_directories=(),
                       profile_contract=None,context_review_callback=None,reviewed_initializer_sources=()):
    common,cc,cxx,sdk,sdk_record,identity=native.native_environment(args)
    checked=native.verify_native_reports(args,value,verify_callback)
    composed=Path(args.composition).resolve(strict=True)
    native_home=Path(args.native_compilation).resolve(strict=True)
    output=Path(args.output).absolute()
    require(not output.exists() and not any(p.is_symlink() for p in (output,*output.parents)),
            'Current image linking requires a fresh ordinary isolated output directory')
    require(all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in (composed,native_home,sdk)),
            'Current image output overlaps an authenticated input')
    require(not ROOT.is_relative_to(output) and
        (not output.is_relative_to(ROOT) or output.is_relative_to(ROOT/'build')) and
        not output.is_relative_to(Path(args.upstream).resolve(strict=True)),
        'Current image output overlaps repository source or the pinned original input')
    require(sorted(reviewed_initializer_sources)==checked['summary']['reviewed_initializer_sources'] and
        list(companion_include_directories)==checked['summary']['companion_include_directories'],
        'Image source includes/initializer owners differ from actual native compilation')
    assets=Path(args.assets_dir).resolve(strict=True)
    firmware_inventory=firmware.ACQUIRE.verify_assets(assets)
    helpers=helper_hashes()
    output.mkdir(parents=True)
    commands=[]
    report=dict(format=1,status='running',phase='verify-current-native-inputs',**identity,**DENIED,
        composition_directory=str(composed),composition_sha256=composer.sha(composed/'composition.json'),
        native_compilation_directory=str(native_home),native_compilation_report_sha256=composer.sha(native_home/'native-compilation.json'),
        native_compilation_reports_verified=True,builder_source_sha256=helpers,sdk=sdk_record,
        firmware_asset_inventory=firmware_inventory,commands=commands,actual_link_performed=False,
        relocatable_link_performed=False,final_link_attempted=False)
    destination=output/'experimental-image.json'
    def execute(command,name,timeout=300,cwd=None):
        command=[str(v) for v in command]
        result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=timeout)
        log=output/(name+'.log');log.write_text(result.stdout+result.stderr)
        commands.append(dict(name=name,command=command,cwd=str(cwd) if cwd else None,status=result.returncode,
                             log=log.name,log_sha256=composer.sha(log)))
        write(destination,report)
        require(result.returncode==0,'Actual native image step failed: '+name+'; '+result.stderr[-4000:])
        return result
    write(destination,report)
    try:
        original_rows,project_rows=checked['original']['results'],checked['project']['results']
        objects=[native_home/(label+'-objects')/r['object'] for label,rows in
                 (('original',original_rows),('project',project_rows)) for r in rows]
        require(len(objects)==1100+len(value['project_translation_units']) and len(set(objects))==len(objects),
                'Current complete source matrix contains missing or duplicate objects')
        report['compilation_reports']=dict(original_sha256=composer.sha(native_home/'full-original-compilation.json'),
            project_sha256=composer.sha(native_home/'project-compilation.json'),original_objects=len(original_rows),
            project_objects=len(project_rows))
        include=[*composer.include_flags(composed),*[v for name in companion_include_directories
            for v in ('-I',str(composed/'project'/composer.checked_relative(name)))]]
        flags,cpp=old.kernel_flags(sdk)
        approved,references,power_ref,front_ref=sdk_references(output,composed,native_home,cc,cxx,sdk,project_rows,include,execute)
        report['independent_sdk_references']=references
        report['approved_public_imports']=sorted(approved)
        layout,layout_ref=sdk_kmod_layout(output,cc,flags,execute)
        report['independent_sdk_kmod_layout']=dict(layout=layout,reference=layout_ref)
        # Fresh whole-source native machine-code graph before profile bytes
        # exist. Its contract cannot hash itself through the late-bound data.
        graph=composer.load('s540_current_experimental_stack',HERE.parent/'prospective-aggregate-stack-closure/check.py')
        budget=composer.load('s540_current_experimental_budget',HERE.parent/'prospective-aggregate-stack-closure/native_budget.py')
        measurement_args=copy(args);measurement_args.stack_output=output/'preliminary-stack'
        measurement_args.final_image=None
        preliminary=graph.measure_verified_plan(measurement_args,value,verify_callback,
            native_home/'full-original-compilation.json',native_home/'project-compilation.json',
            profile_contract=profile_contract,context_review_callback=context_review_callback)
        report['preliminary_measurement_json']=dict(path='preliminary-stack/results.json',
            sha256=composer.sha(output/'preliminary-stack/results.json'))
        original_hashes={str(p):composer.sha(p) for p in objects}
        contract=dict(format=1,scope='actual-current-native-compiled-code-and-complete-measurements',
            composition_sha256=report['composition_sha256'],native_report_sha256=report['native_compilation_report_sha256'],
            compilation_reports=report['compilation_reports'],input_object_sha256=original_hashes,
            preliminary_measurement_sha256=hashlib.sha256(json.dumps(preliminary,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            sdk=sdk_record,compiler_file_sha256=checked['summary']['compiler_file_sha256'],
            late_bound_profile_bytes_excluded=True)
        code_contract=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        profile_bytes,budget_report=budget.build_profile(preliminary,code_contract)
        require(isinstance(profile_bytes,bytes) and len(profile_bytes)==104,'Actual native experimental profile must be104 bytes')
        profile_path=output/'native-profile.bin';profile_path.write_bytes(profile_bytes)
        report['native_code_contract']=dict(sha256=code_contract,basis=contract)
        report['preliminary_native_stack_budget']=budget_report
        report['native_profile']=dict(path=profile_path.name,sha256=composer.sha(profile_path),bytes=104)
        assembly,embedding=firmware.emit_assembly(assets,output)
        assembly.write_text(assembly.read_text()+'.subsections_via_symbols\n')
        firmware_object=output/'firmware-bytes.o'
        execute([cc,'-arch','x86_64','-mmacosx-version-min=15.0','-c',assembly,'-o',firmware_object],
                'firmware-assemble',cwd=assets)
        firmware.verify_embedded_firmware(firmware_object)
        firmware_endpoints(old.Image(firmware_object,1),assets)
        report['firmware_embedding']=embedding
        profile_assembly=output/'native-profile.S'
        profile_assembly.write_text('.section __TEXT,__s540_trial,regular\n.p2align 3\n'
            '.globl _s540ExperimentalNativeProfileBegin\n.globl _s540ExperimentalNativeProfileEnd\n'
            '_s540ExperimentalNativeProfileBegin:\n.incbin "native-profile.bin"\n'
            '_s540ExperimentalNativeProfileEnd:\n.subsections_via_symbols\n')
        profile_object=output/'native-profile.o'
        execute([cc,'-arch','x86_64','-mmacosx-version-min=15.0','-c',profile_assembly,'-o',profile_object],
                'native-profile-assemble',cwd=output)
        verify_endpoint(old.Image(profile_object,1),'s540ExperimentalNativeProfileBegin',
            's540ExperimentalNativeProfileEnd','__s540_trial',profile_bytes)
        archive=sdk/'Library/x86_64/libkmod.a'
        wrappers=[];wrapper_report=[]
        for member,imports in (('c_start.o',{'_realmain','kmod_info'}),('c_stop.o',{'_antimain'})):
            raw=subprocess.run(['/usr/bin/ar','p',str(archive),member],capture_output=True,check=True).stdout
            obj=output/member;obj.write_bytes(raw)
            defined,observed,_=composer.original.macho_symbols(obj)
            power.verify_no_initializers(obj)
            require(observed==imports,'Pinned SDK C module wrapper imports changed')
            wrappers.append(obj);wrapper_report.append(dict(member=member,sha256=composer.sha(obj),definitions=sorted(defined),imports=sorted(observed)))
        report['pinned_module_runtime']=dict(archive_sha256=composer.sha(archive),members=wrapper_report,legacy_libkmod_cpp_used=False)
        objects += [firmware_object,profile_object,*wrappers]
        old.verify_scatterable_objects(objects)
        input_symbols={str(p):old.Image(p,1).externals() for p in objects}
        input_audit=old.audit_symbols(input_symbols,approved,require_private_closure=False,require_reviewed_public=False)
        report['input_symbol_audit']=input_audit
        report['input_object_sha256']={str(p):composer.sha(p) for p in objects}
        report['source_plan']=dict(complete_original_translation_units=1100,canonical_project_translation_units=len(project_rows),
            total_expected_link_objects=len(objects),retained_original_roots=list(old.ROOTS),
            complete_metaclass_classes=[power.CLASS_NAME,*classes.CLASSES],firmware_objects=1,profile_objects=1,
            pinned_libkmod_c_wrappers=['c_start.o','c_stop.o'],dead_strip='final-kext-only')
        report['scatterable_input_objects']=len(objects)
        ld=Path(execute(['/usr/bin/xcrun','--find','ld'],'find-apple-linker').stdout.strip()).resolve(strict=True)
        report['apple_linker']=dict(path=str(ld),sha256=composer.sha(ld))
        linked=output/'S540ExperimentalInit.o'
        report['phase']='complete-relocatable-link'
        execute([ld,'-r','-keep_private_externs','-arch','x86_64',*objects,'-o',linked],
                'complete-relocatable-link',timeout=900)
        old.verify_scatterable_objects([linked])
        linked_symbols=old.Image(linked,1).externals()
        linked_audit=old.audit_symbols({linked.name:linked_symbols},approved,
            require_private_closure=False,require_reviewed_public=False)
        definitions=set(input_audit['strong_definition_owners'])|set(input_audit['weak_definition_owners'])
        require(set(linked_symbols['strong'])|set(linked_symbols['weak'])==definitions and
            linked_audit['unresolved_symbols']==input_audit['unresolved_symbols'],
            'The actual complete ld-r image lost/gained a definition or import')
        require(set(linked_symbols['strong'])==set(input_audit['strong_definition_owners']) and
            set(linked_symbols['weak'])==set(input_audit['weak_definition_owners'])-set(input_audit['strong_definition_owners']),
            'The actual complete ld-r image changed strong/weak definition ownership')
        report['relocatable_image']=dict(path=linked.name,sha256=composer.sha(linked),bytes=linked.stat().st_size,
            subsections_via_symbols=True,unresolved_original_private=linked_audit['unresolved_original_private'])
        report['combined_metaclasses']=classes.verify(linked,power_ref,front_ref)
        old.verify_roots(linked,expected_type=1)
        firmware.verify_embedded_firmware(linked)
        firmware_endpoints(old.Image(linked,1),assets)
        verify_endpoint(old.Image(linked,1),'s540ExperimentalNativeProfileBegin',
            's540ExperimentalNativeProfileEnd','__s540_trial',profile_bytes)
        entries=old.loader_pointer_names(linked)
        report.update(actual_link_performed=True,relocatable_link_performed=True,loader_entries=entries)
        exports=output/'exported-symbols.txt';exports.write_text('_kmod_info\n')
        final=output/'S540ExperimentalInit.macho'
        retained=['__start','__stop','_kmod_info','_s540ProspectiveRetainedRootsPresent',
            '_s540_gsp_begin','_s540_gsp_end','_s540_ucodes_begin','_s540_ucodes_end',
            '_s540ExperimentalNativeProfileBegin','_s540ExperimentalNativeProfileEnd']
        report['final_link_policy']=dict(dead_strip=True,undefined_policy='Apple x86_64 kext dynamic_lookup',
            undefined_closure_enforcement='independent exact final Mach-O private/public symbol audit',
            exported_symbols=['_kmod_info'],unresolved_private_imports_permitted=False,retained_symbols=retained)
        report.update(phase='raw-experimental-kext-link',final_link_attempted=True)
        execute([cxx,'-fuse-ld='+str(ld),'-arch','x86_64','-mmacosx-version-min=15.0','-mkernel','-nostdlib',
            '-Wl,-kext','-Wl,-no_source_version','-Wl,-dead_strip','-Wl,-exported_symbols_list,'+str(exports),
            *[f for name in retained for f in ('-Xlinker','-u','-Xlinker',name)],linked,'-o',final],
            'raw-experimental-kext-link',timeout=900)
        facts=verify_final_image(final,approved,entries,profile_bytes,assets,layout)
        require(set(facts['imports'])<=set(linked_audit['public_imports']),
                'Actual final kernel image gained an import absent from complete ld-r inputs')
        report['final_verification']=facts
        report['final_public_kpi_export_audit']=facts['public_kpi']
        report['final_exported_symbols']=['kmod_info']
        report['final_character_frontend']=old.verify_closed_character_frontend(old.Image(final,11),value)
        final_args=copy(args);final_args.stack_output=output/'final-stack';final_args.final_image=final
        final_measurement=graph.measure_verified_plan(final_args,value,verify_callback,
            native_home/'full-original-compilation.json',native_home/'project-compilation.json',
            profile_contract=profile_contract,context_review_callback=context_review_callback)
        report['final_measurement_json']=dict(path='final-stack/results.json',
            sha256=composer.sha(output/'final-stack/results.json'))
        report['final_native_stack_budget']=budget.verify_profile(final_measurement,profile_bytes,code_contract)
        native.verify_native_reports(args,value,verify_callback)
        require(helper_hashes()==helpers and common.validate_sdk(sdk,None,False)==sdk_record and
            firmware.ACQUIRE.verify_assets(assets)==firmware_inventory and
            all(composer.sha(Path(p))==h for p,h in report['input_object_sha256'].items()) and
            composer.sha(ld)==report['apple_linker']['sha256'],'A source/tool/SDK/asset/object changed during actual linking')
        report.update(status='linked-native-experimental-retained-image',phase='done',
            final_image=dict(path=final.name,sha256=composer.sha(final),bytes=final.stat().st_size,
                filetype='MH_KEXT_BUNDLE',imports=facts['imports'],installable_bundle=False))
        return report
    except Exception as error:
        report.update(status='failed',error=str(error),failure_type=type(error).__name__)
        raise
    finally:
        write(destination,report)
