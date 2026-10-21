#!/usr/bin/env python3
"""Opt-in retained failed sysConstruct; preserves genuine original failures.

Compose after retained-diagnostic/backends and permanent-global-epoch. Emit
exact original/project successors separately; never mutate the input image.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RECORD='packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
HEADER=RECORD[:-1]+'h'
SYSTEM='src/nvidia/src/kernel/core/system.c'
GENERATED='src/nvidia/generated/g_system_nvoc.c'
INPUTS=(RECORD,HEADER)
ORIGINAL_INPUTS=(SYSTEM,GENERATED)
EXPORTS=('s540FirstTxnGlobalRetainConstruction','s540FirstTxnGlobalConstructionRetained')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(text,old,new):
    if text.count(old)!=1:
        raise ValueError('Exact retained construction anchor missing or ambiguous: '+old[:110])
    return text.replace(old,new)

def transforms(values):
    if set(values)!=set(INPUTS):raise ValueError('Exact retained construction project source set required')
    out=dict(values)
    out[RECORD]=once(out[RECORD],
        '    const void *owner; NvU64 generation,thread; } globalEpoch;',
        '    const void *owner; NvU64 generation,thread;\n'
        '    const void *retainedSystem; NvU32 constructionStatus,constructionRetained; } globalEpoch;')
    out[RECORD]=once(out[RECORD],
        '    view.validated=LD(&globalEpoch.validated)!=0;',
        '    view.validated=LD(&globalEpoch.validated)!=0;\n'
        '    view.constructionRetained=LD(&globalEpoch.constructionRetained)!=0;\n'
        '    view.retainedSystem=LD(&globalEpoch.retainedSystem);\n'
        '    view.constructionStatus=LD(&globalEpoch.constructionStatus);')
    out[RECORD]=once(out[RECORD],'NV_STATUS s540FirstTxnGlobalAbort(',
        (HERE/'construction-api.c.inc').read_text()+'\nNV_STATUS s540FirstTxnGlobalAbort(')
    out[HEADER]=once(out[HEADER],
        '    NvBool originalReturned, validated;\n} S540FirstTxnGlobalSnapshot;',
        '    NvBool originalReturned, validated;\n'
        '    const void *retainedSystem; NvU32 constructionStatus; NvBool constructionRetained;\n'
        '} S540FirstTxnGlobalSnapshot;')
    out[HEADER]=once(out[HEADER],'NV_STATUS s540FirstTxnGlobalEnter(void);',
        (HERE/'construction-api.h.inc').read_text()+'\nNV_STATUS s540FirstTxnGlobalEnter(void);')
    return out

def original_transforms(values):
    if set(values)!=set(ORIGINAL_INPUTS):raise ValueError('Exact retained construction original source set required')
    out=dict(values)
    out[SYSTEM]=once(out[SYSTEM],'#include "core/system.h"',
        '#include "core/system.h"\n#include "S540NvidiaGspFirstTransaction.h"')
    out[SYSTEM]=once(out[SYSTEM],'failed:\n\n    _sysDestroyMemExportCache(pSys);',
        'failed:\n\n'
        '    /* Keep the genuine failing system, children, TLS and resource\n'
        '     * roots alive. Sticky OOM forbids the fresh TLS allocation needed\n'
        '     * by destructive rmapiShutdown; preserve the real failure. */\n'
        '    if (s540FirstTxnGlobalRetainConstruction(pSys, status))\n'
        '        return status;\n\n'
        '    _sysDestroyMemExportCache(pSys);')
    out[GENERATED]=once(out[GENERATED],'#include "g_system_nvoc.h"',
        '#include "g_system_nvoc.h"\n#include "S540NvidiaGspFirstTransaction.h"')
    out[GENERATED]=once(out[GENERATED],'__nvoc_ctor_OBJSYS_fail__init:\n',
        '__nvoc_ctor_OBJSYS_fail__init:\n'
        '    /* sysConstruct retained this exact failed system and ancestors. */\n'
        '    if (s540FirstTxnGlobalConstructionRetained(arg_this))\n'
        '        goto __nvoc_ctor_OBJSYS_exit;\n')
    out[GENERATED]=once(out[GENERATED],'__nvoc_objCreate_OBJSYS_cleanup:\n',
        '__nvoc_objCreate_OBJSYS_cleanup:\n'
        '    /* Preserve backing and parent/root identity; failure output stays\n'
        '     * untouched and the actual constructor status remains failure. */\n'
        '    if (s540FirstTxnGlobalConstructionRetained(__nvoc_pThis))\n'
        '        return __nvoc_status;\n')
    return out

def prepare(composition,output):
    sys.path.insert(0,str(ROOT/'builders'))
    import compose_nvidia_first_transaction as composer
    composition=composition.resolve(strict=True)
    if composition.is_dir():composition=composition/'composition.json'
    manifest=composer.verify_composition(composition.parent)
    required=('retained_diagnostic','retained_backends','global_epoch')
    if any(manifest.get('fixed_source_profiles',{}).get(name) is not True for name in required):
        raise ValueError('Exact retained diagnostic/backends/global epoch composition required')
    output=composer.new_output(output,[composition.parent,HERE])
    output.mkdir(parents=True)
    reports={}
    for scope,names,transform in [('project',INPUTS,transforms),('source',ORIGINAL_INPUTS,original_transforms)]:
        root=composition.parent/scope
        values={name:(root/name).read_text() for name in names}
        changed=transform(values)
        rows={}
        for name,text in changed.items():
            path=output/scope/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            rows[name]={'input_sha256':sha(root/name),'output_sha256':sha(path),
                        'source':path.relative_to(output).as_posix()}
        reports[scope]={'format':1,'sources':rows,'composition_sha256':sha(composition),
            'component':'retained-failed-original-global-construction',
            'transform_source_sha256':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
            'original_entry_admission':False,'hardware_admission':False,
            'physical_reclamation_authorized':False,'first_error_cleared':False,
            'actual_failure_preserved':True,'production_candidate_allowed':False}
        destination='project-successor.json' if scope=='project' else 'source-successor.json'
        (output/destination).write_text(json.dumps(reports[scope],indent=2,sort_keys=True)+'\n')
    composer.verify_composition(composition.parent)
    return reports

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();prepare(a.composition,a.output)
