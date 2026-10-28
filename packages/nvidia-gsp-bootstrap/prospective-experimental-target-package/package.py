#!/usr/bin/env python3
"""Sign/package one exact fresh native retained experiment; never load it."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'builders'))
import compose_nvidia_first_transaction as composer
image=composer.load('s540_package_experimental_image',HERE.parent/'prospective-experimental-image/link_native.py')
signing=composer.load('s540_package_signature_invariants',HERE.parent/'prospective-complete-image-package/macho_signing.py')
codec=composer.load('s540_package_native_profile_codec',HERE.parent/'prospective-runtime-coordinator/profile.py')
budget=composer.load('s540_package_native_stack_budget',HERE.parent/'prospective-aggregate-stack-closure/native_budget.py')
native=image.native
FRONT='packages/nvidia-gsp-bootstrap/prospective-experimental-target-control'
BUNDLE='S540ExperimentalInit.kext'
EXECUTABLE='S540ExperimentalInit'
ARCHIVE='S540ExperimentalInitRetained-B10.zip'

def require(value,message):
    if not value: raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path,value):
    Path(path).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')

def ordinary(path):
    path=Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),
            'An authenticated input is not an ordinary file: '+str(path))
    return path.resolve(strict=True)

def checked_file(home,name):
    # The linker records relocatable basenames. Absolute paths are accepted
    # only when still confined to that exact ordinary image build directory.
    return image.contained(home,name)

def bound_file(path,digest):
    path=ordinary(path)
    require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and sha(path)==digest,
            'Authenticated file bytes changed: '+str(path))
    return path

def contract(report):
    expected=dict(format=1,status='linked-native-experimental-retained-image',phase='done',
        host_system='Darwin',host_control=False,native_darwin_compilation=True,
        native_compilation_reports_verified=True,actual_link_performed=True,
        relocatable_link_performed=True,final_link_attempted=True,**image.DENIED)
    for name,wanted in expected.items():
        require(type(report.get(name)) is type(wanted) and report[name]==wanted,
                'Independent experimental package report contract refused: '+name)
    require(report.get('final_exported_symbols')==['kmod_info'],
            'Only real kmod metadata may be exported')
    policy=report.get('final_link_policy',{})
    require(policy.get('dead_strip') is True and policy.get('exported_symbols')==['_kmod_info'] and
        policy.get('unresolved_private_imports_permitted') is False and
        policy.get('undefined_closure_enforcement')=='independent exact final Mach-O private/public symbol audit',
        'Final experimental private/export policy changed')
    plan=report.get('source_plan',{})
    require(plan.get('complete_original_translation_units')==1100 and
        type(plan.get('canonical_project_translation_units')) is int and
        plan['canonical_project_translation_units']>0 and
        plan.get('complete_metaclass_classes')==['S540NvidiaGspPowerService',
            'S540ExperimentalTargetControl','S540ExperimentalTargetClient'] and
        plan.get('profile_objects')==1 and plan.get('firmware_objects')==1,
        'The complete current native matrix/metaclass scope changed')
    final=report.get('final_image',{})
    require(final.get('filetype')=='MH_KEXT_BUNDLE' and final.get('installable_bundle') is False and
        isinstance(final.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',final['sha256']),
        'The exact final native image identity is missing')
    for name in ('complete-relocatable-link','raw-experimental-kext-link'):
        commands=[r for r in report.get('commands',[]) if r.get('name')==name]
        require(len(commands)==1 and type(commands[0].get('status')) is int and commands[0]['status']==0,
                'A real successful native link command is missing: '+name)

def source_archive(destination,composed,value,sdk):
    """Actual corresponding sources, recipe, selected transforms and SDK notices.

    This function is deliberately usable for a Linux source-only preflight.
    It does not create native evidence, load code or sign a bundle.
    """
    require(not destination.exists(),'Source archive output must be fresh')
    records={}
    def add(path,name,expected=None,mode=None):
        path=ordinary(path)
        composer.checked_relative(name)
        require(name not in records,'Duplicate source archive member')
        digest=sha(path)
        require(expected is None or digest==expected,'Corresponding source bytes differ: '+name)
        mode=(0o100755 if path.stat().st_mode&0o111 else 0o100644) if mode is None else mode
        require(mode in (0o100644,0o100755),'Unsupported corresponding source file mode')
        records[name]=(path,digest,mode)
    for scope,key in (('source','original_files'),('project','project_files')):
        for relative,row in value[key].items():
            add(composed/scope/composer.checked_relative(relative),'composition/'+scope+'/'+relative,row['sha256'],int(row['mode'],8))
    add(composed/'composition.json','composition/composition.json')
    add(composed/value['namespace'],'composition/'+value['namespace'],value['namespace_sha256'])
    # Ship the actual recipe inputs as well as already materialized sources.
    # EFI/device reports and unrelated repository history are not included.
    for directory in ('builders','packages'):
        for path in sorted((ROOT/directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                add(path,'recipe/'+path.relative_to(ROOT).as_posix())
    for path in (ROOT/'AGENTS.md',ROOT/'LICENSE',ROOT/'LICENSE.txt'):
        if path.is_file(): add(path,'recipe/'+path.name)
    for relative,expected in value['retained_trial']['helper_source_sha256'].items():
        path=bound_file(ROOT/composer.checked_relative(relative),expected)
        require('recipe/'+relative in records,'A selected recipe helper is missing from corresponding source archive')
    require((composed/'source/COPYING').is_file(),'Original NVIDIA COPYING notice is missing')
    require((sdk/'LICENSE.txt').is_file(),'Pinned SDK license is missing')
    # SDK headers and the exact module-runtime archive are build dependencies.
    # Use its tracked tree, avoiding transient .git metadata and unsafe links.
    tracked=subprocess.check_output(['git','-C',str(sdk),'ls-tree','-rz','HEAD']).split(b'\0')
    for entry in tracked:
        if not entry: continue
        metadata,name=entry.split(b'\t',1);mode,kind,blob=metadata.split()
        require(kind==b'blob' and mode in (b'100644',b'100755'),'Unsupported pinned SDK archive entry')
        relative=name.decode();add(sdk/composer.checked_relative(relative),'MacKernelSDK/'+relative,mode=int(mode,8))
    require(any(name.endswith('/COPYING.txt') and 'softfloat' in name for name in records),
            'Original software floating point notice is missing')
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,(path,digest,mode) in sorted(records.items()):
            require(sha(path)==digest,'Source archive input changed during copying: '+name)
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3;info.external_attr=mode<<16;archive.writestr(info,path.read_bytes())
    require(all(sha(path)==digest for path,digest,mode in records.values()),'Corresponding source input changed during archiving')
    return dict(path=destination.name,sha256=sha(destination),files=len(records),
        original_source_files=len(value['original_files']),project_source_files=len(value['project_files']),
        sdk_source_commit=subprocess.check_output(['git','-C',str(sdk),'rev-parse','HEAD'],text=True).strip())

def verify_measurement(home,row,objects,*,final=None):
    path=bound_file(checked_file(home,row['path']),row['sha256'])
    value=json.loads(path.read_text())
    require(value.get('status')=='complete-current-native-stack-graph-measured' and
        value.get('complete_native_object_inventory') is True and value.get('original_translation_units')==1100,
        'A fresh complete actual native graph measurement is required')
    inputs=value.get('input_sha256',{})
    require(isinstance(inputs,dict) and inputs,'Complete native graph byte bindings are missing')
    for name,digest in inputs.items():bound_file(name,digest)
    require(all(inputs.get(name)==digest for name,digest in objects.items()),
            'Native graph does not bind every actual current compiled source object')
    if final is not None:
        require(inputs.get(str(final))==sha(final),'Final native graph is not bound to this actual image')
    return value

def verify_build(args,value,verify_callback,*,companion_include_directories=(),reviewed_initializer_sources=(),profile_contract=None):
    common,cc,cxx,sdk,sdk_record,identity=native.native_environment(args)
    native.checked_plan(value,verify_callback)
    report_path=bound_file(args.image_report,args.image_report_sha256)
    report=json.loads(report_path.read_text());contract(report)
    require(report['builder_source_sha256']==image.helper_hashes(),'Executing native image verifier helpers changed')
    composed=Path(args.composition).resolve(strict=True)
    home=report_path.parent
    native_home=Path(args.native_compilation).resolve(strict=True)
    require(report['composition_directory']==str(composed) and
        report['composition_sha256']==sha(composed/'composition.json') and
        report['native_compilation_directory']==str(native_home) and report['sdk']==sdk_record,
        'The current source/native/SDK directory identity changed')
    verified=native.verify_native_reports(args,value,verify_callback)
    require(verified['summary']['companion_include_directories']==list(companion_include_directories) and
        verified['summary']['reviewed_initializer_sources']==sorted(reviewed_initializer_sources),
        'Native include and initializer-owner plans changed')
    bound_file(native_home/'native-compilation.json',report['native_compilation_report_sha256'])
    source_objects={}
    for label,filename in (('original','full-original-compilation.json'),('project','project-compilation.json')):
        bound_file(native_home/filename,report['compilation_reports'][label+'_sha256'])
        rows=verified[label]['results']
        require(report['compilation_reports'][label+'_objects']==len(rows),'Native object count changed')
        for row in rows:
            path=native_home/(label+'-objects')/composer.checked_relative(row['object'])
            source_objects[str(path)]=row['object_sha256']
    require(len(source_objects)==1100+len(value['project_translation_units']),
            'Current complete native source object inventory changed')
    expected=set(source_objects)|{str(home/name) for name in ('firmware-bytes.o','native-profile.o','c_start.o','c_stop.o')}
    require(set(report['input_object_sha256'])==expected and report['source_plan']['total_expected_link_objects']==len(expected),
        'Final image inputs do not equal complete current sources plus four exact runtime/asset objects')
    for name,digest in report['input_object_sha256'].items():bound_file(name,digest)
    require(all(report['input_object_sha256'][n]==h for n,h in source_objects.items()),'Native source object bytes changed')
    for row in report['commands']:
        require(type(row['status']) is int and row['status']==0,'A native image command failed')
        bound_file(checked_file(home,row['log']),row['log_sha256'])
    for row in report['independent_sdk_references'].values():
        source=Path(row['source']);source=source if source.is_absolute() else home/source
        bound_file(source,row['source_sha256']);bound_file(checked_file(home,row['object']),row['object_sha256'])
        require(row.get('dependency_sha256'),'Independent actual SDK reference dependencies are missing')
        for name,digest in row['dependency_sha256'].items():bound_file(name,digest)
    layout_ref=report['independent_sdk_kmod_layout']['reference']
    bound_file(checked_file(home,layout_ref['source']),layout_ref['source_sha256'])
    bound_file(checked_file(home,layout_ref['object']),layout_ref['object_sha256'])
    for name,digest in layout_ref['dependency_sha256'].items():bound_file(name,digest)
    archive=sdk/'Library/x86_64/libkmod.a'
    bound_file(archive,report['pinned_module_runtime']['archive_sha256'])
    require(report['pinned_module_runtime']['legacy_libkmod_cpp_used'] is False,'Obsolete C++ module runtime refused')
    for member in ('c_start.o','c_stop.o'):
        raw=subprocess.run(['/usr/bin/ar','p',str(archive),member],check=True,capture_output=True).stdout
        require(raw==checked_file(home,member).read_bytes(),'Actual native C module wrapper changed')
    assets=Path(args.assets_dir).resolve(strict=True)
    require(image.firmware.ACQUIRE.verify_assets(assets)==report['firmware_asset_inventory'],'Pinned firmware assets changed')
    profile_path=bound_file(checked_file(home,report['native_profile']['path']),report['native_profile']['sha256'])
    profile_bytes=profile_path.read_bytes();profile=codec.decode_profile(profile_bytes)
    require(report['native_profile']['bytes']==len(profile_bytes)==104,'Native immutable profile size changed')
    code=report['native_code_contract'];basis=code['basis']
    require(code['sha256']==hashlib.sha256(json.dumps(basis,sort_keys=True,separators=(',',':')).encode()).hexdigest() and
        profile['code_contract_sha256']==code['sha256'] and basis['input_object_sha256']==source_objects and
        basis['late_bound_profile_bytes_excluded'] is True and basis['composition_sha256']==report['composition_sha256'] and
        basis['native_report_sha256']==report['native_compilation_report_sha256'] and
        basis['compilation_reports']==report['compilation_reports'],
        'The immutable native code contract no longer describes the actual compiled source matrix')
    presign=bound_file(checked_file(home,report['final_image']['path']),report['final_image']['sha256'])
    require(presign.stat().st_size==report['final_image']['bytes'],'Actual native image byte count changed')
    preliminary=verify_measurement(home,report['preliminary_measurement_json'],source_objects)
    measured=verify_measurement(home,report['final_measurement_json'],source_objects,final=presign)
    if profile_contract is not None:
        require(preliminary.get('profile_contract')==profile_contract and measured.get('profile_contract')==profile_contract,
            'Native graph context/profile contract differs from the independently supplied current source contract')
    require(basis['preliminary_measurement_sha256']==hashlib.sha256(json.dumps(preliminary,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'The compiled code contract no longer binds its actual preliminary graph')
    encoded,pre_budget=budget.build_profile(preliminary,code['sha256'])
    require(encoded==profile_bytes and pre_budget==report['preliminary_native_stack_budget'] and
        budget.verify_profile(measured,profile_bytes,code['sha256'])==report['final_native_stack_budget'],
        'Current actual native graph no longer fits the exact immutable experimental profile')
    reloc=bound_file(checked_file(home,report['relocatable_image']['path']),report['relocatable_image']['sha256'])
    image.old.verify_scatterable_objects([reloc])
    refs=report['independent_sdk_references']
    metaclasses=image.classes.verify(reloc,checked_file(home,refs['power-metaclass']['object']),
        checked_file(home,refs['experimental-metaclasses']['object']))
    require(metaclasses==report['combined_metaclasses'],'Actual current complete metaclass graph changed')
    approved=report['approved_public_imports']
    entries=image.old.loader_pointer_names(reloc)
    require(json.loads(json.dumps(entries))==report['loader_entries'],
        'Actual current relocatable loader pointer inventory changed')
    proof=image.verify_final_image(presign,approved,entries,profile_bytes,assets,report['independent_sdk_kmod_layout']['layout'])
    require(json.loads(json.dumps(proof))==report['final_verification'],'Strict actual presign image invariants changed')
    character=image.old.verify_closed_character_frontend(image.old.Image(presign,11),value)
    require(character==report['final_character_frontend'],'A forbidden private character dispatcher survived the image')
    identity_record=value['retained_trial']['build_identity']
    return dict(report=report,report_path=report_path,home=home,composed=composed,presign=presign,
        profile_bytes=profile_bytes,profile=profile,code_contract=code['sha256'],approved=approved,entries=entries,
        proof=proof,sdk=sdk,sdk_record=sdk_record,assets=assets,identity=identity,build_identity=identity_record,
        common=common,cc=cc,cxx=cxx,metaclasses=metaclasses)

def bundle_info():
    return dict(CFBundleIdentifier=image.BUNDLE_ID,CFBundleVersion='0.0.1',CFBundleExecutable=EXECUTABLE,
        CFBundleName='S540 retained first initialization',CFBundlePackageType='KEXT',OSBundleCompatibleVersion='0.0.1',
        OSBundleLibraries=image.LIBRARIES,S540ManualRetainedExperiment=True,
        S540NormalUnloadAfterRequest=False,S540ProductionCandidate=False,S540AccelerationTest=False,
        IOKitPersonalities={'ManualRetainedControl':dict(CFBundleIdentifier=image.BUNDLE_ID,
            IOClass='S540ExperimentalTargetControl',IOProviderClass='IOResources',IOResourceMatch='IOKit',
            IOMatchCategory='S540ExperimentalTargetControl')})

def package_verified_plan(args,value,verify_callback,*,companion_include_directories=(),
    profile_contract=None,context_review_callback=None,reviewed_initializer_sources=()):
    # No output or native evidence is created before actual Intel Apple identity.
    native.native_environment(args)
    container=Path(args.output).absolute()
    destination=container/'S540ExperimentalInitRetained'
    require(not container.exists() and not any(p.is_symlink() for p in (container,*container.parents)),
        'Native package output must be a fresh ordinary directory')
    for source in (Path(args.composition).resolve(),Path(args.native_compilation).resolve(),
        Path(args.image_report).resolve().parent,Path(args.kernel_sdk).resolve(),ROOT/'packages',ROOT/'builders'):
        require(not container.is_relative_to(source) and not source.is_relative_to(container),
            'Package output overlaps an authenticated native/source input')
    container.parent.mkdir(parents=True,exist_ok=True)
    helpers={str(path):sha(path) for path in sorted(HERE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
    verified=verify_build(args,value,verify_callback,companion_include_directories=companion_include_directories,
        reviewed_initializer_sources=reviewed_initializer_sources,profile_contract=profile_contract)
    commands=[]
    with tempfile.TemporaryDirectory(prefix='s540-retained-package-',dir=container.parent) as temporary:
        work=Path(temporary);staged=work/'package';staged.mkdir()
        def execute(command,name):
            command=[str(x) for x in command]
            result=subprocess.run(command,capture_output=True,text=True,timeout=180)
            (work/(name+'.log')).write_text(result.stdout+result.stderr)
            commands.append(dict(name=name,command=command,status=result.returncode))
            require(result.returncode==0,'Actual native package command failed: '+name+'; '+result.stderr[-3000:])
            return result
        bundle=staged/BUNDLE;macos=bundle/'Contents/MacOS';macos.mkdir(parents=True)
        resources=bundle/'Contents/Resources';resources.mkdir()
        signed=macos/EXECUTABLE;shutil.copyfile(verified['presign'],signed);signed.chmod(0o755)
        (bundle/'Contents/Info.plist').write_bytes(plistlib.dumps(bundle_info()))
        acquisition=image.firmware.ACQUIRE.MANIFEST
        notice_name=acquisition['redistribution']['notice_path']
        require(len(composer.checked_relative(notice_name).parts)==1,'Firmware notice mapping escapes assets')
        notice=bound_file(verified['assets']/notice_name,acquisition['redistribution']['notice_sha256'])
        shutil.copyfile(notice,resources/notice_name)
        identity=verified['build_identity']
        source_sha=identity['source_sha256'];policy_sha=identity['policy_sha256']
        def array(text):
            require(re.fullmatch('[0-9a-f]{64}',text) is not None,'Generated client digest must be exact SHA256')
            return '{'+','.join('0x'+text[i:i+2] for i in range(0,64,2))+'}'
        generated=work/'client-image-identity.h'
        generated.write_text('#define S540_EXPERIMENTAL_EXPECTED_SOURCE '+array(source_sha)+'\n'
            '#define S540_EXPERIMENTAL_EXPECTED_POLICY '+array(policy_sha)+'\n'
            '#define S540_EXPERIMENTAL_EXPECTED_NATIVE '+array(verified['code_contract'])+'\n'
            '#define S540_EXPERIMENTAL_REQUIRED_STACK '+str(identity['required_kernel_stack_bytes'])+'ULL\n')
        client_source=verified['composed']/'project'/FRONT/'experimental_ctl.c'
        sdk=execute(['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path'],'client-sdk').stdout.strip()
        require(Path(sdk).is_dir(),'Actual macOS user-space SDK is absent')
        client=staged/'experimental_ctl'
        execute([verified['cc'],'-arch','x86_64','-mmacosx-version-min=15.0','-isysroot',sdk,
            '-O2','-std=c11','-Wall','-Wextra','-Werror','-include',generated,client_source,
            '-framework','IOKit','-framework','CoreFoundation','-o',client],'compile-actual-client')
        shutil.copyfile(HERE/'test-retained-first-initialization.sh',staged/'test-retained-first-initialization.sh')
        shutil.copyfile(HERE/'TARGET-GUIDE.md',staged/'READ-ME-FIRST.md')
        evidence=staged/'evidence';evidence.mkdir()
        for path,name in ((verified['report_path'],'native-image.json'),
            (verified['composed']/'composition.json','composition.json'),
            (verified['presign'],'presign-image.macho'),(generated,'client-image-identity.h')):
            shutil.copyfile(path,evidence/name)
        source_receipt=source_archive(staged/'corresponding-source.zip',verified['composed'],value,verified['sdk'])
        for target,label in ((bundle,'bundle'),(client,'client')):
            execute(['/usr/bin/codesign','--force','--sign','-','--timestamp=none',target],'sign-'+label)
            execute(['/usr/bin/codesign','--verify','--strict',target],'verify-'+label)
        invariant=signing.compare(verified['presign'],signed)
        post=image.verify_final_image(signed,verified['approved'],verified['entries'],verified['profile_bytes'],
            verified['assets'],verified['report']['independent_sdk_kmod_layout']['layout'])
        def normalized(value):
            if isinstance(value,dict):
                result={}
                for key,item in value.items():
                    if key=='image_sha256':continue
                    if key=='strong_definition_owners':result[key]={name:'<single-image>' for name in item}
                    elif key=='weak_definition_owners':result[key]={name:['<single-image>']*len(owners) for name,owners in item.items()}
                    else:result[key]=normalized(item)
                return result
            if isinstance(value,(list,tuple)):return [normalized(v) for v in value]
            return value
        require(normalized(post)==normalized(verified['proof']),'Signing changed actual instructions/data/imports/roots/profile/kmod semantics')
        require(image.old.verify_closed_character_frontend(image.old.Image(signed,11),value)==
            verified['report']['final_character_frontend'],'Signing changed private character/event frontend exclusion')
        # This repeats only authenticated reads, not source compilation or graph
        # decoding. It catches source/tool/SDK/object drift during packaging.
        verify_build(args,value,verify_callback,companion_include_directories=companion_include_directories,
            reviewed_initializer_sources=reviewed_initializer_sources,profile_contract=profile_contract)
        require(all(sha(Path(name))==digest for name,digest in helpers.items()),'Packager source changed during execution')
        for path in staged.rglob('*'):
            require(not path.is_symlink(),'Package symlinks are refused')
            path.chmod(0o755 if path.is_dir() or path in (signed,client) or path.suffix=='.sh' else 0o644)
        staged.chmod(0o755)
        for target,label in ((bundle,'bundle'),(client,'client')):
            execute(['/usr/bin/codesign','--verify','--strict',target],'final-verify-'+label)
        logs=evidence/'native-package-logs';logs.mkdir()
        for path in sorted(work.glob('*.log')):
            shutil.copyfile(path,logs/path.name);(logs/path.name).chmod(0o644)
        inventory={path.relative_to(staged).as_posix():sha(path) for path in sorted(staged.rglob('*')) if path.is_file()}
        (staged/'SHA256SUMS').write_text(''.join(digest+'  '+name+'\n' for name,digest in inventory.items()))
        attestation=dict(format=1,status='packaged-native-retained-first-initialization',
            bundle_identifier=image.BUNDLE_ID,bundle_path=BUNDLE,executable=EXECUTABLE,
            target=dict(architecture='x86_64',build='25G241',darwin_release='25.6.0'),
            strict_native_report_sha256=args.image_report_sha256,source_sha256=source_sha,policy_sha256=policy_sha,
            native_code_contract_sha256=verified['code_contract'],native_profile=verified['profile'],
            signed_image=dict(sha256=sha(signed),bytes=signed.stat().st_size,uuid=invariant['uuid']),
            signature_invariance=invariant,postsign_verification=post,corresponding_source=source_receipt,
            native_packager=verified['identity'],sdk=verified['sdk_record'],commands=commands,
            package_manifest_sha256=sha(staged/'SHA256SUMS'),inventory=inventory,packager_source_sha256=helpers,
            normal_unload_after_request=False,
            retention_policy='facade/module/PCI until reboot; original-visible or uncertain buffers/IOVAs retained; checked pre-original cleanup permitted',
            checked_pre_original_cleanup_permitted=True,
            experiment_entry_enabled=True,actual_lenovo_test_performed=False,module_loaded=False,
            installable_bundle_created=True,system_security_changed=False,production_candidate_allowed=False,
            whole_dma_stop_proven=False,aggregate_stack_proven=False,pm_acknowledgement_authorized=False,
            acceleration_test=False)
        write(staged/'packaging-attestation.json',attestation)
        container.mkdir()
        staged.rename(destination)
    artifacts=container
    archive=artifacts/ARCHIVE
    require(not archive.exists(),'Final retained archive must be fresh')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zipped:
        for path in sorted(destination.rglob('*')):
            require(not path.is_symlink(),'Final archive symlinks are refused')
            if path.is_file():zipped.write(path,'S540ExperimentalInitRetained/'+path.relative_to(destination).as_posix())
    result=dict(format=1,status='packaged-native-retained-first-initialization',output=str(destination),
        archive=str(archive),archive_sha256=sha(archive),attestation_sha256=sha(destination/'packaging-attestation.json'),
        actual_lenovo_test_performed=False,module_loaded=False,system_security_changed=False,acceleration_test=False)
    write(artifacts/'package-digests.json',result)
    shutil.copyfile(destination/'packaging-attestation.json',artifacts/'packaging-attestation.json')
    return result
