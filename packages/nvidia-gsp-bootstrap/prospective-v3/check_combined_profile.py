#!/usr/bin/env python3
"""Isolated V3 composition: frozen V2 plus sequential checked timers.

Compiles changed original units and real project bridges; no admission or link.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import struct
import sys
import tarfile

V2_HELPER = 'cbeb2618560673d0cb8a2b051431b1ead3d31c948e6029a3cec1815dc97d7429'
V2_CONTRACT = 'ce3fe72438c0548098d94fc0147b7ad036307378578e0b9c418a74aae96b938e'
TIMER_FREEZE = 'cf1d0398f8c9bde49c64cfe56efa4daeace0e4a68bd259d32c2f78e983bf75aa'
SDK_COMMIT = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
SDK_ARCHIVE = '8931e622b6d16a7052cb2c2dabe16be06963a34b747f19e6cda2bbe8bc7e2557'
TIMER = 'src/nvidia/src/kernel/gpu/timer/timer.c'
OSTIMER = 'src/nvidia/src/kernel/gpu/timer/timer_ostimer.c'
OS = 'src/nvidia/arch/nvalloc/unix/src/os.c'
TIMER_BRIDGES = {'s540GspTimersCancelNano', 's540GspTimersDestroyNano'}
PUBLIC_TIMER_CALLBACKS = {'nv_start_rc_timer', 'nv_stop_rc_timer', 'nv_create_nano_timer',
                          'nv_start_nano_timer', 'nv_cancel_nano_timer', 'nv_destroy_nano_timer'}

def sha(data): return hashlib.sha256(data).hexdigest()
def digest(path): return sha(path.read_bytes())
def write_json(path, value): path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

def strong_exports(path, names):
    """Require exact externally defined symbols without N_WEAK_DEF."""
    data=path.read_bytes();offset=32;table=None
    for unused in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,offset)
        if command==2:table=struct.unpack_from('<4I',data,offset+8)
        offset+=size
    if table is None:raise ValueError('Missing Mach-O symbol table')
    symbols,count,strings,size=table;found={}
    for index in range(count):
        string,kind,section,description,value=struct.unpack_from('<IBBHQ',data,symbols+index*16)
        if not kind&1 or kind&0x0e!=0x0e:continue
        end=data.index(b'\0',strings+string,strings+size)
        name=data[strings+string:end].decode().removeprefix('_')
        if name in names:
            if description&0x80:raise ValueError('Weak project bridge definition: '+name)
            found[name]={'n_type':kind,'n_sect':section,'n_desc':description}
    if set(found)!=set(names):raise ValueError('Missing strong project bridge export')
    return found

def main():
    parser = argparse.ArgumentParser()
    for key in ('repo', 'upstream', 'checked-source', 'v2-output', 'namespace', 'cc', 'cxx',
                'kernel-sdk', 'timer-control-report', 'output'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--sdk-archive',type=Path)
    parser.add_argument('--cross-probe',action='store_true')
    args = parser.parse_args()
    native=sys.platform=='darwin' and platform.machine()=='x86_64'
    if not native and not args.cross_probe:raise ValueError('Intel macOS required; use --cross-probe explicitly elsewhere')
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve(strict=key!='output'))
    if args.output.exists(): raise ValueError('Fresh isolated output required')
    args.output.mkdir(parents=True)
    self_sha = digest(Path(__file__).resolve())
    own_contract_path=Path(__file__).with_name('PROSPECTIVE-SOURCE-PROFILE.json')
    own_contract_sha=digest(own_contract_path);own_contract=json.loads(own_contract_path.read_text())
    if own_contract['helper_sha256']!=self_sha:raise ValueError('V3 helper changed')
    sys.path.insert(0, str(args.repo/'builders'))
    import compile_nvidia_global_rm as original
    base = original.validate_checked_source(args.upstream, args.checked_source)
    v2dir = args.repo/'packages/nvidia-gsp-bootstrap/prospective-v2'
    if digest(v2dir/'check_combined_profile.py') != V2_HELPER: raise ValueError('V2 helper changed')
    if digest(v2dir/'PROSPECTIVE-SOURCE-PROFILE.json') != V2_CONTRACT: raise ValueError('V2 contract changed')
    v2 = module(v2dir/'check_combined_profile.py')
    contract = json.loads((v2dir/'PROSPECTIVE-SOURCE-PROFILE.json').read_text())
    monitored = {own_contract_path:own_contract_sha,v2dir/'check_combined_profile.py': V2_HELPER,
                 v2dir/'PROSPECTIVE-SOURCE-PROFILE.json': V2_CONTRACT}
    for name,expected in own_contract['project_input_sha256'].items():monitored[args.repo/name]=expected
    for name, expected in contract['project_input_sha256'].items(): monitored[args.repo/name] = expected
    for path, expected in monitored.items():
        if digest(path) != expected: raise ValueError('Frozen V2 input changed: '+str(path))
    old = json.loads((args.v2_output/'combined-profile-audit.json').read_text())
    if (old['status'] != 'changed-original-units-compiled' or old['compile_failures'] or
        old['composition_script_sha256'] != V2_HELPER or
        old['combined_tree_sha256'] != contract['combined_tree_sha256'] or
        old['final_sources_sha256'] != contract['final_sources_sha256'] or
        old['verified_ten_tree_sha256'] != base['tree_sha256']):
        raise ValueError('V2 output is not the frozen verified composition')
    if len(old['translation_units']) != 25 or len(old['project_bridge_translation_units']) != 2:
        raise ValueError('V2 compiled-input count differs')
    if digest(args.namespace) != old['baseline_namespace_sha256']:
        raise ValueError('The baseline private namespace changed')
    expected_files = dict(base['files'])
    for name, expected in contract['final_sources_sha256'].items():
        expected_files[name] = {**expected_files[name], 'sha256': expected}
    original._verify_workspace(args.v2_output/'source', {'files': expected_files})
    for row in old['translation_units']+old['project_bridge_translation_units']:
        if digest(args.v2_output/'objects'/row['object']) != row['object_sha256']:
            raise ValueError('V2 compiled object changed')
        for name, expected in row['dependency_sha256'].items():
            if digest(Path(name)) != expected: raise ValueError('V2 compile dependency changed: '+name)
    timers = args.repo/'packages/nvidia-gsp-bootstrap/prospective-timer-checked'
    freeze_path = timers/'FROZEN-SHA256.json'
    if digest(freeze_path) != TIMER_FREEZE: raise ValueError('Timer freeze changed')
    monitored[freeze_path] = TIMER_FREEZE
    frozen = json.loads(freeze_path.read_text())
    for name, expected in frozen['files'].items():
        path = timers/name
        if digest(path) != expected: raise ValueError('Frozen timer input changed: '+name)
        monitored[path] = expected
    tc = json.loads((timers/'SOURCE-CONTRACT.json').read_text())
    timer_controls=json.loads(args.timer_control_report.read_text())
    if timer_controls['source_contract']!=tc or timer_controls['status']!='passed-isolated-timer-cpu-controls':
        raise ValueError('Timer CPU controls do not match the frozen source contract')
    if timer_controls['namespace_sha256']!=digest(args.namespace):raise ValueError('Timer control namespace differs')
    for label,checks,failures in [('bridge',16,4),('order',384,165),('status',49,10)]:
        for version,nfail in [('candidate',0),('baseline',failures)]:
            for record in timer_controls['controls'][label][version].values():
                if (record['checks'],record['failures'],record['status'])!=(checks,nfail,'failed' if nfail else 'passed'):
                    raise ValueError('Checked timer CPU control failed')
    for record in timer_controls['controls']['legacy_void_abi'].values():
        if (record['checks'],record['failures'],record['status'])!=(34,0,'passed'):
            raise ValueError('Legacy timer ABI control failed')
    monitored[args.timer_control_report]=digest(args.timer_control_report)
    raw_timers = {name: (args.upstream/name).read_bytes() for name in tc['original_source_sha256']}
    for name, expected in tc['original_source_sha256'].items():
        if sha(raw_timers[name]) != expected: raise ValueError('Raw timer source changed')
    timer_sources = dict(raw_timers)
    timer_project = {name: (args.repo/name).read_bytes() for name in tc['original_project_sha256']}
    for name, expected in tc['original_project_sha256'].items():
        if sha(timer_project[name]) != expected: raise ValueError('Raw timer bridge changed')
        monitored[args.repo/name] = expected
    predecessor = timers/tc['patches'][0]['path']
    old_predecessor = v2dir/'inputs/cancellation-timer-status-prospective/timer-cancel-status-prospective.patch'
    if predecessor.read_bytes() != old_predecessor.read_bytes(): raise ValueError('Status predecessor differs')
    predecessor_sources = original._strict_patch(raw_timers, predecessor.read_bytes())
    for name in (TIMER, OSTIMER):
        if sha(predecessor_sources[name]) != contract['final_sources_sha256'][name]:
            raise ValueError('V2 has other timer edits; cannot replace predecessor')
    for index, row in enumerate(tc['patches']):
        patch = (timers/row['path']).read_bytes()
        if sha(patch) != row['sha256']: raise ValueError('Timer patch digest changed')
        target = timer_project if index == 3 else timer_sources
        target.update(original._strict_patch(target, patch))
    if {name: sha(data) for name, data in timer_sources.items()} != tc['final_source_sha256']:
        raise ValueError('Sequential timer final bytes differ')
    if {name: sha(data) for name, data in timer_project.items()} != tc['final_project_sha256']:
        raise ValueError('Sequential timer project bytes differ')
    raw = {name: (args.upstream/name).read_bytes() for name in contract['final_sources_sha256']}
    final = {name: (args.v2_output/'source'/name).read_bytes() for name in raw}
    final[TIMER], final[OSTIMER] = timer_sources[TIMER], timer_sources[OSTIMER]
    final[OS], os_offsets = v2.merge(raw[OS], v2.edits(raw[OS], final[OS], 'frozen-v2')+
                                   v2.edits(raw[OS], timer_sources[OS], 'checked-timer-os'))
    for name, data in final.items():
        if name not in (TIMER, OSTIMER, OS) and sha(data) != contract['final_sources_sha256'][name]:
            raise ValueError('Unexpected V2 source changed')
    timer_runner=module(timers/'check_timer_checked.py')
    for function in ('osCancelNanoTimer','osDestroyNanoTimer'):
        if timer_runner.body(final[OS],function,'NV_STATUS')!=timer_runner.body(timer_sources[OS],function,'NV_STATUS'):
            raise ValueError('Merged original OS callback differs from the tested complete body')
    raw_patch = v2.diff_patch(raw, final)
    ten_inputs = {name: (args.checked_source/name).read_bytes() for name in final}
    ten_patch = v2.diff_patch(ten_inputs, final)
    v2_inputs = {name: (args.v2_output/'source'/name).read_bytes() for name in final}
    v2_patch = v2.diff_patch(v2_inputs, final)
    for before, patch in [(raw, raw_patch), (ten_inputs, ten_patch), (v2_inputs, v2_patch)]:
        if {**before, **original._strict_patch(before, patch)} != final:
            raise ValueError('Combined patch replay differs')
    for filename, data in [('all-prospective-overlays-from-raw.patch',raw_patch),
                           ('prospective-additions-to-verified-ten.patch',ten_patch),
                           ('checked-timer-additions-to-v2.patch',v2_patch)]:
        (args.output/filename).write_bytes(data)
    if ({name:sha(data) for name,data in final.items()}!=own_contract['final_sources_sha256'] or
        {'raw_to_v3':sha(raw_patch),'ten_to_v3':sha(ten_patch),'v2_to_v3':sha(v2_patch)}!=own_contract['patch_sha256']):
        raise ValueError('The frozen V3 source composition changed')
    source = args.output/'source'; shutil.copytree(args.v2_output/'source', source)
    for name, data in final.items():
        (source/name).write_bytes(data)
        expected_files[name] = {**expected_files[name], 'sha256':sha(data)}
    original._verify_workspace(source, {'files':expected_files})
    project = args.output/'project-overlay';shutil.copytree(args.v2_output/'project-overlay',project)
    for name, data in timer_project.items():
        path = project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    # Copy real project headers with relative includes preserved, never replace
    # the TimerOriginal relative global-host import with a test facade.
    for relative in ['packages/nvidia-global-rm/src/S540NvidiaGlobalRm.h']:
        path = args.repo/relative;monitored[path] = digest(path)
        target = project/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    ns = args.output/'prospective-private-namespace.h'
    ns.write_text('/* V3 original private aliases; project bridges remain strong. */\n#include "'+
                  str(args.namespace)+'"\n'+''.join('#define '+k+' '+v+'\n' for k,v in old['new_original_private_names'].items()))
    cancel = project/'packages/nvidia-gsp-bootstrap/cancellation'
    timer_include = project/'packages/nvidia-gsp-bootstrap/timers'
    source_root = source/'src/nvidia';objects=args.output/'objects';objects.mkdir()
    commands=original.original_commands(args.upstream,args.output,args.cc)
    by_source={row[row.index('-c')+1]:row for row in commands}
    project_bridges = set(v2.PROJECT_BRIDGES)|TIMER_BRIDGES
    report={'format':1,'profile':'isolated-prospective-combined-v3-not-approved','status':'composed',
            'native_apple_compiler':native and not args.cross_probe,'cross_compile_probe':args.cross_probe,'production_candidate_allowed':False,
            'approved_profile':False,'kernel_execution':'not_tested','gpu_access':False,
            'helper_sha256':self_sha,'source_contract_sha256':own_contract_sha,'v2_helper_sha256':V2_HELPER,'v2_source_contract_sha256':V2_CONTRACT,
            'timer_freeze_sha256':TIMER_FREEZE,'timer_source_contract':tc,
            'status_predecessor_replaced_exactly_once':True,'os_raw_to_composed_offsets':os_offsets,
            'final_sources_sha256':{n:sha(v) for n,v in final.items()},
            'combined_tree_files':len(expected_files),
            'combined_tree_sha256':sha(json.dumps(expected_files,sort_keys=True,separators=(',',':')).encode()),
            'patch_sha256':{'raw_to_v3':sha(raw_patch),'ten_to_v3':sha(ten_patch),'v2_to_v3':sha(v2_patch)},
            'unique_project_bridges':sorted(project_bridges),'new_original_private_names':old['new_original_private_names'],
            'timer_body_controls':{'report_sha256':digest(args.timer_control_report),'checks_each_variant':483,
                                   'scope':'Separate CPU controls with explicit dependencies; no combined adapter execution',
                                   'source_contract_sha256':digest(timers/'SOURCE-CONTRACT.json')},
            'translation_units':[],'project_bridge_translation_units':[],'sdk_backend_translation_units':[],
            'limits':['Changed 25 original translation units only; no all-1100 header-fanout claim.',
                      'Individual 4096-byte frame check is not a complete call-chain stack bound.',
                      'No link/KXLD, hardware/PM/DMA, accepted-work borrower or outer-destructor admission.']}
    write_json(args.output/'combined-profile-audit.json',report)
    target_flags=(['-target','x86_64-macos-none'] if args.cross_probe else
                  ['-mkernel','-arch','x86_64','-mmacosx-version-min=15.0'])
    def compile_c(name, project_kind=False):
        if project_kind:
            row=commands[0];path=project/name;stem=path.name;flags=['-mkernel','-DKERNEL','-D__KERNEL__']
        else:
            rel=__import__('os').path.relpath(name,'src/nvidia');row=by_source[rel];path=source/name
            stem=rel.replace('/','__');flags=['-fPIC'] if args.cross_probe else []
        obj=objects/(stem+'.o');dep=obj.with_suffix('.d')
        command=[str(args.cc),*row[1:row.index('-c')],'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__',
                 '-DNV_VERSION_STRING="'+original.RELEASE+'"','-include',str(ns),'-I',str(cancel),
                 '-I',str(timer_include),*target_flags,*flags,
                 '-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than',
                 '-MMD','-MF',str(dep),'-c',str(path),'-o',str(obj)]
        result=subprocess.run(command,cwd=source_root,text=True,capture_output=True,timeout=300)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:raise ValueError(name+' failed:\n'+result.stderr[-6500:])
        defined,undefined,sections=original.macho_symbols(obj)
        if not project_kind and any(not n.startswith(original.PREFIX) for n in defined):
            raise ValueError('Original unnamespaced export')
        imports={n for n in undefined if n.startswith('s540') and not n.startswith(original.PREFIX)}
        if not project_kind and imports-project_bridges:raise ValueError('Unexpected project bridge imports '+repr(imports-project_bridges))
        if project_kind and not name.endswith('TimersOriginal.c') and any(not n.startswith('s540GspCancellation') for n in defined):
            raise ValueError('Unexpected cancellation project definition')
        export_metadata={}
        if project_kind and name.endswith('TimersOriginal.c'):
            expected={original.PREFIX+n for n in PUBLIC_TIMER_CALLBACKS}
            if {n for n in defined if n.startswith(original.PREFIX)}!=expected:
                raise ValueError('Original timer callback namespace attribution differs')
            if any(not n.startswith(('s540GspTimers',original.PREFIX)) for n in defined):
                raise ValueError('Unexpected checked timer project definition')
            expected |= {'s540GspTimersBind','s540GspTimersStop','s540GspTimersUnbind',
                         's540GspTimersGetSnapshot',*TIMER_BRIDGES}
            if defined != expected: raise ValueError('Checked timer exact strong exports differ')
            export_metadata=strong_exports(obj,defined)
        dependencies={}
        for name_dep in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            p=Path(name_dep);p=(p if p.is_absolute() else source_root/p).resolve(strict=True)
            if p.is_relative_to(args.upstream):raise ValueError('Raw upstream header escaped composed tree')
            dependencies[str(p)]=digest(p)
        return {'source':name,'source_sha256':digest(path),'object':obj.name,'object_sha256':digest(obj),
                'definitions':sorted(defined),'imports':sorted(undefined),'sections':sections,
                'strong_export_metadata':export_metadata,
                'unique_project_bridge_imports':sorted(imports),'dependency_sha256':dependencies,'command':command}
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(compile_c,name):name for name in sorted(final) if name.endswith('.c')}
        for job in concurrent.futures.as_completed(jobs):
            try:report['translation_units'].append(job.result());print('PASS '+jobs[job],flush=True)
            except Exception as exc:failures.append({'source':jobs[job],'error':str(exc)});print('FAIL '+jobs[job],flush=True)
            write_json(args.output/'combined-profile-audit.json',report)
    for name in ['packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c',
                 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellationOriginal.c',
                 'packages/nvidia-gsp-bootstrap/timers/S540NvidiaGspTimersOriginal.c']:
        try:report['project_bridge_translation_units'].append(compile_c(name,True));print('PASS '+name,flush=True)
        except Exception as exc:failures.append({'source':name,'error':str(exc)});print('FAIL '+name,flush=True)
    # Compare every SDK file to the exact local archive; do not present an
    # archive filename as independent Git provenance or native Apple execution.
    sdk_files={};prefix='MacKernelSDK-'+SDK_COMMIT+'/'
    if args.sdk_archive:
        if digest(args.sdk_archive)!=SDK_ARCHIVE:raise ValueError('SDK archive changed')
        with tarfile.open(args.sdk_archive,'r:gz') as archive:
            for member in archive.getmembers():
                if not member.isfile():continue
                if not member.name.startswith(prefix):raise ValueError('Unexpected archive root')
                relative=member.name[len(prefix):];data=archive.extractfile(member).read()
                if (args.kernel_sdk/relative).read_bytes()!=data:raise ValueError('SDK differs from archive: '+relative)
                sdk_files[relative]=sha(data)
        observed_sdk={p.relative_to(args.kernel_sdk).as_posix() for p in args.kernel_sdk.rglob('*') if p.is_file()}
        if observed_sdk!=set(sdk_files):raise ValueError('SDK archive/tree file inventory differs')
        sdk_identity={'archive_sha256':SDK_ARCHIVE,'source':'local exact archive; not a Git checkout'}
    else:
        def git(*command):
            return subprocess.run(['/usr/bin/git','-C',str(args.kernel_sdk),*command],capture_output=True,check=True).stdout
        if git('rev-parse','HEAD').decode().strip()!=SDK_COMMIT:raise ValueError('SDK Git revision differs')
        if git('ls-files','--others'):raise ValueError('SDK contains untracked files')
        for entry in git('ls-tree','-rz','HEAD').split(b'\0'):
            if not entry:continue
            metadata,name=entry.split(b'\t',1);mode,kind,expected=metadata.split()
            if kind!=b'blob' or mode not in (b'100644',b'100755'):raise ValueError('Unexpected SDK tree entry')
            path=args.kernel_sdk/name.decode();data=path.read_bytes()
            observed=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest().encode()
            if observed!=expected:raise ValueError('SDK tracked file differs: '+name.decode())
            sdk_files[name.decode()]=sha(data)
        sdk_identity={'source':'verified Git commit and every tracked blob'}
    report['sdk']={'reference_commit':SDK_COMMIT,**sdk_identity,'file_count':len(sdk_files),
                  'tree_sha256':sha(json.dumps(sdk_files,sort_keys=True,separators=(',',':')).encode())}
    backend=args.repo/'packages/nvidia-darwin-services/src/S540NvidiaDarwinTimer.cpp'
    monitored[backend]=digest(backend);obj=objects/'S540NvidiaDarwinTimer.cpp.o';dep=obj.with_suffix('.d')
    cpp_target=(['-target','x86_64-apple-macos15'] if args.cross_probe else
                ['-arch','x86_64','-mmacosx-version-min=15.0'])
    command=[str(args.cxx),*cpp_target,'-mkernel','-fno-builtin','-ffreestanding',
             '-fno-common','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables',
             '-mno-red-zone','-DKERNEL','-D__KERNEL__','-O2','-Wall','-Wextra','-Werror',
             '-Wno-deprecated-declarations','-nostdinc','-isystem',str(args.kernel_sdk/'Headers'),
             '-I',str(args.repo/'packages/nvidia-os-adapter/upstream/include'),'-fapple-kext',
             '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-fno-use-cxa-atexit','-mllvm',
             '-disable-atexit-based-global-dtor-lowering','-nostdinc++','-std=c++17',
             '-Wframe-larger-than=4096','-Werror=frame-larger-than','-MD','-MF',str(dep),
             '-c',str(backend),'-o',str(obj)]
    result=subprocess.run(command,cwd=args.repo,text=True,capture_output=True,timeout=300)
    obj.with_suffix('.log').write_text(result.stdout+result.stderr)
    if result.returncode:failures.append({'source':str(backend),'error':result.stderr[-6500:]})
    else:
        defined,undefined,sections=original.macho_symbols(obj)
        dependencies={}
        for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=Path(name);path=(path if path.is_absolute() else args.repo/path).resolve(strict=True)
            dependencies[str(path)]=digest(path)
        report['sdk_backend_translation_units'].append({'source':str(backend),'source_sha256':digest(backend),
             'object':obj.name,'object_sha256':digest(obj),'definitions':sorted(defined),'imports':sorted(undefined),
             'sections':sections,'dependency_sha256':dependencies,'command':command})
        print('PASS actual SDK DarwinTimer backend',flush=True)
    project_defined=set().union(*(set(r['definitions']) for r in report['project_bridge_translation_units']))
    if not project_bridges<=project_defined:failures.append({'missing_strong_bridges':sorted(project_bridges-project_defined)})
    for row in report['translation_units']+report['project_bridge_translation_units']+report['sdk_backend_translation_units']:
        for path,expected in row['dependency_sha256'].items():
            if digest(Path(path))!=expected:raise ValueError('Actual compiler dependency changed')
    for path,expected in monitored.items():
        if digest(path)!=expected:raise ValueError('Frozen project input changed during V3')
    original._verify_workspace(source,{'files':expected_files})
    if digest(Path(__file__).resolve())!=self_sha:raise ValueError('V3 helper changed during run')
    report['compiler']={key:{'sha256':digest(path),'version':subprocess.run([str(path),'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]}
                        for key,path in [('c',args.cc),('cxx',args.cxx)]}
    report['monitored_project_inputs']={str(p):s for p,s in monitored.items()}
    report['compile_failures']=failures;report['status']='failed' if failures else 'changed-original-units-compiled'
    report['translation_units'].sort(key=lambda r:r['source'])
    write_json(args.output/'combined-profile-audit.json',report)
    print(json.dumps({'status':report['status'],'original_units':len(report['translation_units']),
                     'strong_project_c_units':len(report['project_bridge_translation_units']),
                     'sdk_cpp_backends':len(report['sdk_backend_translation_units']),'failures':failures},indent=2))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
