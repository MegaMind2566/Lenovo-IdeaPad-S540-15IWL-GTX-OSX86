#!/usr/bin/env python3
"""Actual-body CPU controls and complete original-TU compilation; no GPU/PIO."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

import prepare
HERE, ROOT = prepare.HERE, prepare.ROOT
sys.path.insert(0, str(ROOT / 'builders'))
import compile_nvidia_global_rm as original
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original'))
import common

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def controls_source(raw, proposed, osinit):
    prefix = raw[raw.index('#define IO_LOG'):raw.index('static NvU8\nx_inb')]
    start, end = prepare.function_span(raw, 'RmInitX86EmuState')
    baseline = raw[start:end].replace('RmInitX86EmuState', 'baselineInit', 1)
    start, end = prepare.function_span(proposed, 'RmInitX86EmuState')
    candidate = proposed[start:end].replace('RmInitX86EmuState', 'candidateInit', 1)
    start, end = prepare.function_span(osinit, 'RmInitX86Emu')
    caller = osinit[start:end].replace('RmInitX86Emu(', 'actualCaller(', 1).replace('RmInitX86EmuState(', 'candidateInit(')
    return '''#include "nv.h"
#include "osapi.h"
#include "os/os.h"
#include "core/core.h"
#include "gpu/gpu.h"
#include "x86emu/x86emu.h"
#undef memcpy
#undef memcmp
#include <stdio.h>
#include <string.h>
''' + prefix + '''
extern NvU8 x_inb(NvU16); extern NvU16 x_inw(NvU16); extern u32 x_inl(X86EMU_pioAddr);
extern void x_outb(NvU16,NvU8); extern void x_outw(NvU16,NvU16); extern void x_outl(X86EMU_pioAddr,u32);
extern NvU8 Mem_rb(u32); extern NvU16 Mem_rw(u32); extern u32 Mem_rl(u32);
extern void Mem_wb(u32,NvU8); extern void Mem_ww(u32,NvU16); extern void Mem_wl(u32,u32);
extern void x86emu_do_int(int);
X86EMU_sysEnv M;
static unsigned allocations, assertions, checks, failures;
static void *allocationFailure(NvLength bytes) { (void)bytes; ++allocations; return NULL; }
#undef portMemAllocNonPaged
#define portMemAllocNonPaged(bytes) allocationFailure(bytes)
#undef NV_ASSERT
#define NV_ASSERT(condition) do { if (!(condition)) ++assertions; } while (0)
NV_STATUS
''' + baseline + '\nNV_STATUS\n' + candidate + '\nstatic NV_STATUS\n' + caller + '''
#define CHECK(test) do { ++checks; if (!(test)) ++failures; } while (0)
static OBJGPU gpu, savedGpu;
static nv_state_t nv, savedNv;
static unsigned char savedMap[sizeof(x86emu_mem_map)];
int main(void) {
    NV_SET_NV_STATE(&gpu,&nv);
    savedGpu=gpu; savedNv=nv;
    x86emuReady=NV_TRUE; x86emuStack=(void *)0x1234;
    memcpy(savedMap,x86emu_mem_map,sizeof(savedMap));
    CHECK(baselineInit(&gpu)==NV_OK);
    CHECK(allocations==0); CHECK(assertions==0);
    CHECK(x86emuReady==NV_TRUE); CHECK(x86emuStack==(void *)0x1234);
    CHECK(memcmp(&gpu,&savedGpu,sizeof(gpu))==0); CHECK(memcmp(&nv,&savedNv,sizeof(nv))==0);
    CHECK(memcmp(savedMap,x86emu_mem_map,sizeof(savedMap))==0);
    CHECK(candidateInit(&gpu)==NV_OK); CHECK(allocations==0); CHECK(assertions==0);
    CHECK(actualCaller(&gpu)==NV_OK);
    nv.primary_vga=NV_TRUE; savedNv=nv;
    CHECK(candidateInit(&gpu)==NV_ERR_NOT_SUPPORTED); CHECK(allocations==0);
    CHECK(x86emuReady==NV_TRUE); CHECK(x86emuStack==(void *)0x1234);
    CHECK(memcmp(&gpu,&savedGpu,sizeof(gpu))==0); CHECK(memcmp(&nv,&savedNv,sizeof(nv))==0);
    CHECK(memcmp(savedMap,x86emu_mem_map,sizeof(savedMap))==0); CHECK(assertions==0);
    CHECK(actualCaller(&gpu)==NV_ERR_NOT_SUPPORTED);
    x86emuReady=NV_FALSE;
    CHECK(baselineInit(&gpu)==NV_ERR_NO_MEMORY); CHECK(allocations==1);
    CHECK(x86emuReady==NV_FALSE); CHECK(x86emuStack==NULL); CHECK(assertions==0);
    printf("{\\"status\\":\\"%s\\",\\"checks\\":%u,\\"failures\\":%u,\\"kernel_execution\\":\\"not_tested\\",\\"gpu_access\\":false,\\"port_io_executed\\":false}\\n",failures?"failed":"passed",checks,failures);
    return failures?1:0;
}
'''

def check(args):
    upstream = original._pinned_upstream(args.upstream)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(upstream) or output.is_relative_to(HERE):
        raise ValueError('Fresh output outside source inputs required')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / 'build'):
        raise ValueError('Repository output must be below build/')
    cc = common.compiler(str(args.cc));cxx=common.compiler(str(args.cxx))
    identity = common.execution_identity(cc,cxx,args.host_control)
    identity['native_darwin_compilation']=identity.pop('authoritative_darwin_execution')
    namespace=args.namespace.resolve(strict=True)
    ns=json.loads((ROOT/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    if sha(namespace)!=ns['namespace_sha256']:raise ValueError('Baseline namespace changed')
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    for group,root in [('source_sha256',HERE),('original_source_sha256',upstream),('project_source_sha256',ROOT)]:
        for name,digest in contract[group].items():
            if sha(root/name)!=digest:raise ValueError('Source contract changed: '+name)
    raw=(upstream/prepare.SOURCE).read_text();proposed=prepare.overlay(raw)
    output.mkdir(parents=True)
    source=output/'vbioscall.c';source.write_text(proposed)
    controls=output/'actual-body-controls.c'
    controls.write_text(controls_source(raw,proposed,(upstream/'src/nvidia/arch/nvalloc/unix/src/osinit.c').read_text()))
    flags=original.original_bridge_flags(upstream,output/'profile',cc,namespace)
    forbidden={'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}
    cpu=[flag for flag in flags if flag not in forbidden]+['-fPIC','-O1','-g','-DS540_NVIDIA_NONPRIMARY_X86_EMULATION=1']
    if args.host_control:cpu+=['-U__linux__','-U__linux']
    results={}
    for label,extra in [('plain',[]),('sanitized',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
        obj=output/(label+'.o');binary=output/label
        command=[str(cc),*cpu,*extra,'-c',str(controls),'-o',str(obj)]
        original.execute(command,diagnostic_log=output/(label+'-compile.log'))
        original.execute([str(cxx),*extra,str(obj),'-o',str(binary)],diagnostic_log=output/(label+'-link.log'))
        env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0'
        result=subprocess.run([str(binary)],text=True,capture_output=True,env=env)
        (output/(label+'-run.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise ValueError('Actual-body control failed: '+result.stdout+result.stderr)
        results[label]=json.loads(result.stdout)
    declared=original.original_commands(upstream,output/'declared',cc)
    matches=[row for row in declared if row[row.index('-c')+1]=='arch/nvalloc/unix/src/vbioscall.c']
    if len(matches)!=1:raise ValueError('No unique complete original source command')
    base=matches[0][:matches[0].index('-c')]
    obj=output/'vbioscall-profile.o'
    target=['-target','x86_64-macos-none','-fPIC'] if args.host_control else ['-arch','x86_64','-mmacosx-version-min=15.0','-mkernel']
    command=[*base,'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__','-DNV_VERSION_STRING="615.78.08"','-include',str(namespace),*target,'-DS540_NVIDIA_NONPRIMARY_X86_EMULATION=1','-c',str(source),'-o',str(obj)]
    original.execute(command,cwd=upstream/'src/nvidia',diagnostic_log=output/'full-tu.log')
    defined,imports,_=original.macho_symbols(obj)
    forbidden_imports={original.PREFIX+name for name in contract['removed_callbacks']}
    if imports&forbidden_imports:raise ValueError('Nonprimary profile still references primary emulator callbacks')
    negatives=[]
    for label,option in [('missing',[]),('zero',['-DS540_NVIDIA_NONPRIMARY_X86_EMULATION=0'])]:
        negative=[flag for flag in command if flag!='-DS540_NVIDIA_NONPRIMARY_X86_EMULATION=1']
        negative[negative.index('-o')+1]=str(output/('refused-'+label+'.o'))
        negative+=option
        result=subprocess.run(negative,cwd=upstream/'src/nvidia',text=True,capture_output=True)
        (output/('refused-'+label+'.log')).write_text(result.stdout+result.stderr)
        if not result.returncode or 'Explicit nonprimary-only x86 emulation source profile required' not in result.stderr:
            raise ValueError('Unselected source profile was not refused')
        negatives.append({'case':label,'refused':True})
    report={'format':1,'status':'passed-nonprimary-original-source-profile',**identity,'controls':results,
        'full_translation_unit':{'source_sha256':sha(source),'object_sha256':sha(obj),'definitions':sorted(defined),'imports':sorted(imports),'command':command},
        'negative_compile_controls':negatives,'removed_primary_emulator_callbacks':sorted(forbidden_imports),
        'primary_status':'NV_ERR_NOT_SUPPORTED before any emulator allocation/map/publication',
        'nonprimary_status':'unchanged original NV_OK early return','fixture_scope':'actual complete NVIDIA types and bodies; explicit allocation-failure and assert-observer CPU controls',
        'leak_inspection':'disabled due executor ptrace limitation; these controls allocate no emulator backing',
        'kernel_execution':'not_tested','gpu_access':False,'original_entry_admission':False,'production_candidate_allowed':False}
    (output/'nonprimary-profile-checks.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['upstream','namespace','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--cc',type=Path,default=Path('/usr/bin/clang'));parser.add_argument('--cxx',type=Path,default=Path('/usr/bin/clang++'));parser.add_argument('--host-control',action='store_true')
    v=check(parser.parse_args());print(json.dumps({'status':v['status'],'checks':{k:r['checks'] for k,r in v['controls'].items()},'gpu_access':False}))
