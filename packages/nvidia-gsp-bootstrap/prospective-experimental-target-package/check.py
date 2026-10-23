#!/usr/bin/env python3
"""Actual source-archive/executable-mode and nonnative refusal controls."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('s540_actual_package_controls',HERE/'package.py')
package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('composition','kernel-sdk','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    args.composition=args.composition.resolve(strict=True);args.kernel_sdk=args.kernel_sdk.resolve(strict=True)
    if args.output.exists():raise ValueError('Fresh archive control output required')
    args.output.mkdir(parents=True)
    value=package.composer.verify_composition(args.composition)
    archive=args.output/'actual-corresponding-source.zip'
    receipt=package.source_archive(archive,args.composition,value,args.kernel_sdk)
    counts={'original':0,'project':0,'executable':0,'sdk':0}
    with zipfile.ZipFile(archive) as zipped:
        rows={row.filename:row for row in zipped.infolist()}
        if len(rows)!=len(zipped.infolist()):raise ValueError('Source archive duplicated a member')
        for scope,key,label in (('source','original_files','original'),('project','project_files','project')):
            for relative,expected in value[key].items():
                row=rows['composition/'+scope+'/'+relative]
                if row.create_system!=3 or row.external_attr>>16!=int(expected['mode'],8):
                    raise ValueError('Actual source archive lost inventoried source mode:'+relative)
                if package.hashlib.sha256(zipped.read(row)).hexdigest()!=expected['sha256']:
                    raise ValueError('Actual source archive changed inventoried bytes:'+relative)
                counts[label]+=1
                if expected['mode']=='100755':counts['executable']+=1
        if not counts['executable']:raise ValueError('Control did not cover any real executable source mode')
        for row in zipped.infolist():
            if row.filename.startswith('MacKernelSDK/'):
                if not stat.S_ISREG(row.external_attr>>16):raise ValueError('SDK member is not a regular file')
                counts['sdk']+=1
    restored=args.output/'restored'
    subprocess.run(['unzip','-q',str(archive.resolve()),'-d',str(restored.resolve())],check=True)
    for scope,key in (('source','original_files'),('project','project_files')):
        for relative,expected in value[key].items():
            path=restored/'composition'/scope/relative
            if stat.S_IMODE(path.stat().st_mode)!=int(expected['mode'],8)&0o777 or package.sha(path)!=expected['sha256']:
                raise ValueError('Actual unzip did not restore exact executable/source mode:'+relative)
    negative=args.output/'missing-notice-composition'
    negative.mkdir()
    for scope in ('source','project'):
        shutil.copytree(args.composition/scope,negative/scope,copy_function=os.link)
    for relative in ('composition.json',value['namespace']):shutil.copyfile(args.composition/relative,negative/relative)
    (negative/'source/COPYING').unlink()
    refused=False
    try:package.source_archive(args.output/'must-not-exist.zip',negative,value,args.kernel_sdk)
    except ValueError:refused=True
    if not refused or (args.output/'must-not-exist.zip').exists():raise ValueError('Missing original legal/source notice was admitted')
    refusal_output=args.output/'must-not-be-native-package'
    native_refusal='not-executed-on-native-host'
    if sys.platform!='darwin':
        try:package.package_verified_plan(SimpleNamespace(output=refusal_output),{},lambda:{})
        except ValueError as error:
            if 'Intel macOS' not in str(error):raise
            native_refusal='refused-before-native-output'
        else:raise ValueError('Nonnative source control created native packaging evidence')
        if refusal_output.exists():raise ValueError('Nonnative packaging wrote an output')
    report=dict(format=1,status='actual-source-archive-controls-passed',archive=receipt,checks=counts,
        actual_unzip_restored_inventory_modes=True,missing_original_notice_refused=True,
        nonnative_package=native_refusal,host_control=True,native_darwin_packaging=False,
        source_sha256={str(path.relative_to(ROOT)):package.sha(path) for path in (HERE/'package.py',HERE/'check.py',
            HERE/'test-retained-first-initialization.sh',HERE/'TARGET-GUIDE.md')},
        composition_sha256=package.sha(args.composition/'composition.json'),kernel_execution='not_tested',gpu_access=False)
    (args.output/'results.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
