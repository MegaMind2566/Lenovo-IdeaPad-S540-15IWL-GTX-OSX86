#!/usr/bin/env python3
"""Replay the immutable V3 companion files without inventing a compile audit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'builders'))
import compile_nvidia_global_rm as original

EXPECTED_COUNT=28
EXPECTED_TREE='ec8108f56f4b59b8c9937953206efffba6820d1b6998c55303ceee9d64bc8eb5'
def sha(data):return hashlib.sha256(data).hexdigest()
def replay(output):
    output=output.resolve()
    if output.exists():raise ValueError('A fresh project-overlay output is required')
    if (output.parent/'materialized-project-source.json').exists():
        raise ValueError('A fresh source-only report is required')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT/'build'):
        raise ValueError('Repository output is allowed only below build/')
    # This is the exact companion-copy loop of the frozen V2 checker: its
    # `contract` is the v1 contract, not the much broader V2 audit-input list.
    predecessor=ROOT/'packages/nvidia-gsp-bootstrap/prospective/PROSPECTIVE-SOURCE-PROFILE.json'
    inputs=json.loads(predecessor.read_text())['project_input_sha256']
    values={name:(ROOT/name).read_bytes() for name in inputs}
    for name,data in values.items():
        if sha(data)!=inputs[name]:raise ValueError('Pinned v1 companion changed: '+name)
    logpatch=ROOT/'packages/nvidia-gsp-bootstrap/prospective-v2/inputs/cancellation-log-prospective/optional-log-port-prospective.patch'
    if sha(logpatch.read_bytes())!='1f373cacd791ce5d8d3eca6b937744e686c66397998b428bd8c9d0680a0d9c62':
        raise ValueError('Pinned V2 project patch changed')
    values.update(original._strict_patch(values,logpatch.read_bytes()))
    timers=ROOT/'packages/nvidia-gsp-bootstrap/prospective-timer-checked'
    contract=json.loads((timers/'SOURCE-CONTRACT.json').read_text())
    raw={name:(ROOT/name).read_bytes() for name in contract['original_project_sha256']}
    for name,data in raw.items():
        if sha(data)!=contract['original_project_sha256'][name]:raise ValueError('Raw timer companion changed: '+name)
    row=contract['patches'][3];patch=(timers/row['path']).read_bytes()
    if sha(patch)!=row['sha256']:raise ValueError('Pinned checked-timer project patch changed')
    raw.update(original._strict_patch(raw,patch))
    if {name:sha(data) for name,data in raw.items()}!=contract['final_project_sha256']:
        raise ValueError('Checked timer companion replay changed')
    values.update(raw)
    name='packages/nvidia-global-rm/src/S540NvidiaGlobalRm.h'
    values[name]=(ROOT/name).read_bytes()
    # V2/V3 copyfile/write_bytes emit non-executable files. Include every
    # copied helper/contract as the real checker does, not only C headers.
    rows={name:{'sha256':sha(data),'mode':'100644'} for name,data in values.items()}
    tree=sha(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())
    if len(rows)!=EXPECTED_COUNT or tree!=EXPECTED_TREE:
        raise ValueError('Exact immutable V3 companion inventory changed')
    output.mkdir(parents=True)
    for name,data in values.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o644)
    return {'format':1,'source_only':True,'compiled':False,'original_entry_admission':False,
        'files':rows,'files_verified':len(rows),'tree_sha256':tree,
        'replay_helper_sha256':sha(Path(__file__).read_bytes())}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=replay(args.output)
    reportpath=args.output.parent/'materialized-project-source.json'
    reportpath.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:report[key] for key in ('source_only','compiled','files_verified','tree_sha256','original_entry_admission')},sort_keys=True))
