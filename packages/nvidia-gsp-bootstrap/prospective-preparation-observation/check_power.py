#!/usr/bin/env python3
"""Compare exact B3/new PM bodies, raw observations and endpoint call traces."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('s540_pm_observation_transform', HERE / 'power.py')
power = importlib.util.module_from_spec(spec); spec.loader.exec_module(power)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text, start, following):
    if text.count(start) != 1 or text.count(following) != 1:
        raise ValueError('Exact PM fixture function boundary changed')
    return text[text.index(start):text.index(following)].strip() + '\n'


def run(args):
    base = args.project.resolve(strict=True); output = args.output.resolve()
    if output.exists() or output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('Fresh isolated PM observation control output required')
    values = {name: (base / name).read_text() for name in power.INPUTS}
    changed = power.transforms(values)
    output.mkdir(parents=True); project = output / 'project'; shutil.copytree(base, project)
    for name, text in changed.items(): (project / name).write_text(text)
    header = project / 'packages/nvidia-gsp-bootstrap/prospective-preparation-observation/S540PreparationObservation.h'
    header.parent.mkdir(parents=True); header.write_bytes((HERE / header.name).read_bytes())
    includes = [project / 'packages', project / 'packages/nvidia-gsp-bootstrap/platform',
        project / 'packages/nvidia-os-adapter/upstream/include',
        project / 'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure',
        project / 'packages/nvidia-gsp-bootstrap/prospective-pm-event-closure']
    common = ['-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-ffunction-sections', '-fdata-sections', *[p for path in includes for p in ('-I', str(path))]]
    report = dict(format=1, status='running', input_sha256=power.BASE_SHA256,
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__), HERE/'power.py',
            HERE/'S540PreparationObservation.h', HERE/'tests/check_power.cpp')},
        output_source_sha256={n:hashlib.sha256(t.encode()).hexdigest() for n,t in changed.items()},
        commands=[], dependency_sha256={}, variants={}, negative_controls={},
        original_pm_control_flow_changed=False, extra_pm_requests=0, extra_hardware_queries=0,
        native_darwin_compilation=False, hardware_executed=False)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')

    def record(): (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    def execute(command, log, expected=0):
        result = subprocess.run([str(x) for x in command],capture_output=True,text=True,timeout=180,env=environment)
        log.write_text(result.stdout+result.stderr);report['commands'].append([str(x) for x in command])
        if expected is not None and result.returncode != expected:
            raise ValueError('PM observation control failed: '+str(log)+'\n'+result.stderr[-5000:])
        return result
    def compile_one(source, obj, flags):
        dep=obj.with_suffix('.d');execute([args.cxx,*flags,'-MD','-MF',dep,'-c',source,'-o',obj],obj.with_suffix('.compile.log'))
        for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=Path(name).resolve(strict=True);digest=sha(path)
            if report['dependency_sha256'].setdefault(str(path),digest)!=digest:raise ValueError('PM control dependency changed')
    def variant(label,instrumentation,expected=0):
        work=output/label;work.mkdir();new=(project/power.POWER).read_text();old=values[power.POWER]
        kernel=power.KERNEL
        if kernel not in new:raise ValueError('Actual guarded metadata helper bodies changed')
        for text,original in ((new,False),(old,True)):
            join=function(text,'bool S540NvidiaGspPowerService::join(', 'bool S540NvidiaGspPowerService::exactDomain()')
            wait=function(text,'NV_STATUS S540NvidiaGspPowerService::waitOn()', 'Snapshot S540NvidiaGspPowerService::snapshot()')
            if original:join=join.replace('::join(','::originalJoin(',1);wait=wait.replace('::waitOn()','::originalWaitOn()',1)
            kernel+='\n'+join+wait
        kernel+='\n'+function(new,'Snapshot S540NvidiaGspPowerService::snapshot()','NV_STATUS S540NvidiaGspPowerService::acknowledge()')
        (work/'actual-power-kernel.inc').write_text(kernel)
        lease=function(new,'NV_STATUS Lease::status() const','NV_STATUS Lease::acknowledgeRevocation()')
        lease+=function(old,'NV_STATUS Lease::status() const','NV_STATUS Lease::acknowledgeRevocation()').replace('Lease::status()','Lease::originalStatus()',1)
        lease+=function(new,'NV_STATUS Lease::stop()','S540PreparationPowerObservation Lease::preparationObservation()')
        lease+=function(new,'S540PreparationPowerObservation Lease::preparationObservation()','NvU64 Lease::revocationEventNs()')
        (work/'actual-power-lease.inc').write_text(lease.replace('Lease::','TestLease::'))
        objects=[]
        for name,source in [('power',project/power.POWER),('control',HERE/'tests/check_power.cpp')]:
            obj=work/(name+'.o');compile_one(source,obj,[*common,'-I',str(work),*instrumentation]);objects.append(obj)
        binary=work/'control';execute([args.cxx,*instrumentation,'-pthread',*objects,'-Wl,--gc-sections','-o',binary],binary.with_suffix('.link.log'))
        return binary,execute([binary],binary.with_suffix('.run.log'),expected)
    record()
    try:
        for label,flags in [('plain',[]),('sanitized',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
            binary,result=variant(label,flags);observed=json.loads(result.stdout)
            if observed['status']!='passed':raise ValueError('PM observation fixture did not pass')
            report['variants'][label]=dict(observed,binary_sha256=sha(binary))
        for label,before,after in [
            ('getter_repeats_domain_query','const auto result = service->protocol.preparationObservation();',
                '(void)service->exactDomain();\n    const auto result = service->protocol.preparationObservation();'),
            ('raw_ior_return_erased','NvU32(registered), NV_TRUE','0, NV_TRUE'),
            ('observation_lost_when_impl_freed','    preparationFinal_ = preparationObservation();','    /* deliberate lost-copy mutant */')]:
            path=project/power.POWER;text=path.read_text()
            if text.count(before)!=1:raise ValueError('Exact PM observation mutation point changed: '+label)
            path.write_text(text.replace(before,after));success=report['dependency_sha256'];report['dependency_sha256']={}
            try:
                binary,result=variant('negative-'+label,[],None)
                if result.returncode==0:raise ValueError('PM observation mutation escaped: '+label)
                report['negative_controls'][label]=dict(rejected=True,status=result.returncode,binary_sha256=sha(binary))
            finally:path.write_text(text);report['dependency_sha256']=success
        for path,digest in report['dependency_sha256'].items():
            if sha(path)!=digest:raise ValueError('PM observation dependency changed during controls')
        report['status']='passed-actual-old-new-PM-body-observation-controls';return report
    except Exception as error:report.update(status='failed',error=str(error));raise
    finally:record()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--cxx',type=Path,required=True)
    a=p.parse_args();r=run(a);print(json.dumps(dict(status=r['status'],variants=r['variants'],negative_controls=list(r['negative_controls']))))
