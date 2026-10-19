#!/usr/bin/env python3
"""Execute actual Host pinning against the frozen strong-record implementation.

GPU-binding record composition is separately kernel-compiled; these controls
isolate the new Host policy with actual queues, timers and tracked allocations.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys

import prepare

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent/'prospective-first-transaction'
REPO=HERE.parents[2]


def check(args):
    composition=args.composition.resolve(strict=True)
    observed=json.loads(composition.read_text())
    project=(composition.parent/observed['project']).resolve(strict=True)
    output=args.output.resolve()
    if output.exists() or output.is_relative_to(project) or project.is_relative_to(output):
        raise ValueError('Fresh output separate from composed input required.')
    # Revalidate the frozen parent and all source materialization inputs.
    sys.path.insert(0,str(HERE.parent/'prospective-work-gpu-binding'))
    spec=importlib.util.spec_from_file_location('s540_pin_parent_guard',HERE.parent/'prospective-work-gpu-binding/prepare.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);guard.parent_guard()
    sys.path.insert(0,str(PARENT/'original'))
    import common
    identity=common.execution_identity(common.compiler(str(args.cc)),common.compiler(str(args.cxx)),args.host_control)
    inputs={}
    for name,metadata in observed['project_files'].items():
        path=project/name
        if path.is_symlink() or prepare.sha(path)!=metadata['sha256']:
            raise ValueError('Composed control input changed: '+name)
        inputs[str(path)]=metadata['sha256']
    values={name:(project/name).read_text() for name in
            (prepare.HOST,prepare.RETENTION,prepare.RETENTION_ORIGIN)}
    # The tested pin fragment is the same exact transformation used by the
    # composed successor. Additional work/GPU metadata is not claimed tested here.
    values[prepare.RECORD]=(PARENT/'record/S540NvidiaGspFirstTransaction.c').read_text()
    values[prepare.HEADER]=(PARENT/'record/S540NvidiaGspFirstTransaction.h').read_text()
    transformed=prepare.transforms(values)
    inputs.update({str(PARENT/'record/S540NvidiaGspFirstTransaction.c'):prepare.sha(PARENT/'record/S540NvidiaGspFirstTransaction.c'),
            str(PARENT/'record/S540NvidiaGspFirstTransaction.h'):prepare.sha(PARENT/'record/S540NvidiaGspFirstTransaction.h')})
    output.mkdir(parents=True)
    fixture=output/'fixture';record=fixture/'record';services=fixture/'services';host=output/'host'
    shutil.copytree(project,host)
    shutil.copytree(PARENT/'record',record,ignore=shutil.ignore_patterns('__pycache__'))
    services.mkdir()
    for path in (PARENT/'services').glob('*.h'):
        shutil.copy2(path,services/path.name)
    for name in ('S540NvidiaFirstTxnServices.cpp',):
        shutil.copy2(PARENT/'services'/name,services/name)
    fixture_source=(PARENT/'services/check_strong_joint.c').read_text()
    fixture_source=prepare.once(fixture_source,'static unsigned checks, failures;',
        'static void *diagnosticDirectPointer;\nstatic unsigned checks, failures;')
    fixture_source=prepare.once(fixture_source,
        '    require(s540GspCancellationCurrentScopeActive());',
        '    require(s540GspCancellationCurrentScopeActive());\n'
        '    if (mode == 6) s540GlobalRmHostFreeOriginal(diagnosticDirectPointer);')
    (services/'parent-controls.inc').write_text(fixture_source)
    shutil.copy2(HERE/'check_host.c',services/'check_strong_joint.c')
    for name,text in transformed.items():
        if name==prepare.RECORD:target=record/'S540NvidiaGspFirstTransaction.c'
        elif name==prepare.HEADER:target=record/'S540NvidiaGspFirstTransaction.h'
        else:target=host/name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    sys.path.insert(0,str(PARENT/'services'))
    spec=importlib.util.spec_from_file_location('s540_pinning_joint',PARENT/'services/check_joint.py')
    joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint)
    joint.HERE=services
    result=joint.check({'upstream':args.upstream,'namespace':args.namespace,
        'output':output/'checks','cc':args.cc,'cxx':args.cxx,
        'host_overlay':host,'services_overlay':composition.parent/'inputs/work-gpu/services-overlay',
        'host_control':args.host_control})
    if any(prepare.sha(Path(path))!=digest for path,digest in inputs.items()):
        raise ValueError('Frozen record changed during pinning controls.')
    result.update(component='retained-diagnostic-host',
        record_scope='frozen strong record plus exact pinning transform; work/GPU successor separately compiled',
        composition_sha256=prepare.sha(composition),kernel_execution='not_tested',
        execution_identity=identity,native_apple_execution=identity['authoritative_darwin_execution'],
        callback_fixture_source_sha256=prepare.sha(services/'parent-controls.inc'),
        installable_candidate_generated=False,
        gpu_access=False,production_candidate_allowed=False)
    (output/'diagnostic-host-controls.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('composition','upstream','namespace','output','cc','cxx'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--host-control',action='store_true')
    check(parser.parse_args())
