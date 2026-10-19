#!/usr/bin/env python3
"""Bind the empty admitted-user-mapping set to the exact reviewed loader."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]

def validate_profile(project_root=None):
    root=Path(project_root or REPO).resolve(strict=True)
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    verified={}
    for relative,expected in contract['source_sha256'].items():
        path=HERE/relative
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('The reviewed mapping implementation/control changed: '+relative)
    # A composer may copy just the runtime source, but if that source is in
    # its project tree it must be exactly the implementation reviewed here.
    mapped=root/'packages/nvidia-gsp-bootstrap/prospective-mapping-closure/S540NvidiaMappingClosure.c'
    if mapped.exists() and (mapped.is_symlink() or hashlib.sha256(mapped.read_bytes()).hexdigest()!=contract['source_sha256']['S540NvidiaMappingClosure.c']):
        raise ValueError('The composed mapping backend differs from its reviewed implementation')
    for relative,expected in contract['loader_source_sha256'].items():
        path=root/relative
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('The reviewed no-user-mapping loader changed: '+relative)
        source=path.read_text()
        if any(name in source for name in ('clientMemoryForType','mapClientMemory','getExternalMethodForIndex','getExternalAsyncMethodForIndex')):
            raise ValueError('A new mapping or alternate external-method ingress requires independent review')
        verified[relative]=expected
    header=(root/'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.hpp').read_text()
    if header.count('class S540ProspectiveLoaderClient final : public IOUserClient')!=1:
        raise ValueError('The exact inherited IOUserClient mapping refusal is no longer established')
    return {'format':1,'status':'verified-fixed-no-user-mapping-loader',
        'loader_source_sha256':verified,'apple_reference':contract['apple_reference'],
        'source_sha256':contract['source_sha256'],'callbacks':contract['callbacks'],
        'expected_imports':contract['expected_imports'],
        'user_client_present':True,'user_mapping_ingress':False,'dma_stop_receipt':False}

if __name__=='__main__':
    print(json.dumps(validate_profile(),indent=2,sort_keys=True))
