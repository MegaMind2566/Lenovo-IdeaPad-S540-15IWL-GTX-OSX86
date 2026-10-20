#!/usr/bin/env python3
"""Exercise the exact V3 wrapper contract at independent absolute build paths."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import prepare as candidate


def run(args):
    baseline=args.baseline.resolve(strict=True)
    output=args.output.resolve()
    if output.exists():raise ValueError('Namespace control output must be fresh')
    output.mkdir(parents=True)
    source_repo=candidate.REPO
    aliases=json.loads((source_repo/'packages/nvidia-gsp-bootstrap/prospective-v2/PROSPECTIVE-SOURCE-PROFILE.json').read_text())['new_original_private_names']
    prefix='/* V3 original private aliases; project bridges remain strong. */\n#include "'
    def wrapper(path):
        return (prefix+str(path)+'"\n'+''.join('#define '+k+' '+v+'\n' for k,v in sorted(aliases.items()))).encode()
    checks=[]
    hashes=[]
    compile_rows=[]
    for name in ('native-build-a', 'different checkout with spaces/native-build-b'):
        home=output/name;home.mkdir(parents=True)
        base=home/'S540GlobalRmNamespace.h';base.write_bytes(baseline.read_bytes())
        header=home/'prospective-private-namespace.h';header.write_bytes(wrapper(base))
        if candidate.namespace_guard(header)!=header:raise ValueError('Guard returned a different wrapper')
        checks.append('accept-exact-independent-absolute-path-'+name)
        hashes.append(candidate.sha(header))
        command=[str(args.cc),'-E','-dM','-include',str(header),'-x','c',os.devnull]
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode:raise ValueError(result.stderr)
        macros={line.split()[1]:' '.join(line.split()[2:]) for line in result.stdout.splitlines() if line.startswith('#define ')}
        if any(macros.get(k)!=v for k,v in aliases.items()):raise ValueError('Actual compiler lost a V3 alias')
        checks.append('actual-compiler-five-aliases-'+name)
        compile_rows.append({'command':command,'status':result.returncode,'wrapper_sha256':candidate.sha(header),
                             'baseline_sha256':candidate.sha(base),'aliases':aliases})
    if len(set(hashes))!=2:raise ValueError('Independent absolute wrappers unexpectedly match byte hashes')
    checks.append('different-raw-wrapper-hashes-same-pinned-contract')
    home=output/'negatives';home.mkdir()
    base=home/'S540GlobalRmNamespace.h';base.write_bytes(baseline.read_bytes())
    header=home/'prospective-private-namespace.h'
    def refused(path,label):
        try:candidate.namespace_guard(path)
        except (ValueError,OSError,UnicodeError):checks.append('refuse-'+label);return
        raise ValueError('Namespace guard accepted '+label)
    refused(base,'baseline-used-as-v3-wrapper')
    correct=wrapper(base)
    first=next(iter(sorted(aliases)))
    mutations={
        'wrong-alias':correct.replace(aliases[first].encode(),b's540WrongAlias',1),
        'missing-alias':correct.replace(('#define '+first+' '+aliases[first]+'\n').encode(),b'',1),
        'duplicate-alias':correct+('#define '+first+' '+aliases[first]+'\n').encode(),
        'extra-macro':correct+b'#define S540_UNREVIEWED 1\n',
        'extra-include':correct+b'#include "unreviewed.h"\n',
        'changed-comment':correct.replace(b'project bridges remain strong',b'project bridges are changed',1),
        'relative-baseline':wrapper(Path('S540GlobalRmNamespace.h')),
        'noncanonical-baseline':wrapper(home/'..'/'negatives'/'S540GlobalRmNamespace.h'),
        'crlf-directives':correct.replace(b'\n',b'\r\n'),
        'trailing-bytes':correct+b'\0',
        'reordered-aliases':(prefix+str(base)+'"\n'+''.join('#define '+k+' '+v+'\n' for k,v in reversed(sorted(aliases.items())))).encode()}
    for label,raw in mutations.items():header.write_bytes(raw);refused(header,label)
    header.write_bytes(correct)
    bad=home/'wrong-baseline.h';bad.write_bytes(baseline.read_bytes()+b'\n#define EXTRA 1\n')
    header.write_bytes(wrapper(bad));refused(header,'changed-baseline-bytes')
    link=home/'baseline-symlink.h';link.symlink_to(base)
    header.write_bytes(wrapper(link));refused(header,'baseline-symlink')
    header.write_bytes(correct)
    link=home/'wrapper-symlink.h';link.symlink_to(header);refused(link,'wrapper-symlink')
    directory=output/'directory-symlink';directory.symlink_to(home,target_is_directory=True)
    refused(directory/header.name,'wrapper-parent-symlink')
    fifo=home/'fifo.h';os.mkfifo(fifo);refused(fifo,'non-regular-wrapper')
    # Change independent contract bytes only in a separate local repository,
    # preserving the real frozen source files throughout the control.
    fake=output/'contract-fixture'
    relatives=['packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json',
               'packages/nvidia-gsp-bootstrap/prospective-v2/PROSPECTIVE-SOURCE-PROFILE.json']
    for relative in relatives:
        target=fake/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((source_repo/relative).read_bytes())
    try:
        candidate.REPO=fake
        for relative in relatives:
            target=fake/relative;original=target.read_bytes();target.write_bytes(original+b'\n')
            refused(header,'changed-independent-contract-'+target.parent.name)
            target.write_bytes(original)
    finally:candidate.REPO=source_repo
    result={'format':1,'status':'passed','checks':checks,'check_count':len(checks),
        'actual_preprocessor_controls':compile_rows,'pinned_baseline_sha256':candidate.sha(baseline),
        'helper_sha256':candidate.sha(Path(candidate.__file__)),
        'control_source_sha256':candidate.sha(Path(__file__)),
        'runtime_source_transforms_changed':False,'module_loaded':False,'gpu_access':False,
        'hardware_admission':False,'original_entry_admission':False,'production_candidate_allowed':False}
    (output/'namespace-guard-controls.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','cc','output'):p.add_argument('--'+name,type=Path,required=True)
    result=run(p.parse_args())
    print(json.dumps({'status':result['status'],'checks':result['check_count'],'runtime_source_transforms_changed':False}))
