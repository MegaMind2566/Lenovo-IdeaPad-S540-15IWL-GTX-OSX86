"""Exact new two-class SDK registration and combined three-class audit."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'builders'))
import nvidia_metaclass_initializers as old
import nvidia_combined_metaclasses as combined

CLASSES=('S540ExperimentalTargetControl','S540ExperimentalTargetClient')

def require(value,message):
    if not value: raise ValueError(message)

def loader_graph(actual,reference):
    observed=old.Object(actual).loader_graph()
    reviewed=old.Object(reference).loader_graph()
    require(observed==reviewed,'Current experimental registration differs from independent SDK code generation')
    require([r['section'] for r in reviewed['entries']]==['__mod_init_func','__mod_term_func'],
            'Only the exact experimental initializer/finalizer pair is admitted')
    prefixes={'__ZN'+str(len(name))+name for name in CLASSES}
    data={p+'10gMetaClassE':0 for p in prefixes}
    data.update({'__ZTVN'+str(len(name))+name+'9MetaClassE':16 for name in CLASSES})
    externals={'__ZN11OSMetaClassC2EPKcPKS_j','__ZN11OSMetaClassD2Ev',
               '__ZN9IOService10gMetaClassE','__ZN12IOUserClient10gMetaClassE'}
    seen_external,seen_data,seen_names=set(),set(),set()
    for name,function in reviewed['functions'].items():
        require(name=='<translation-unit-initializer>' or name.startswith('__GLOBAL__D_') or
            any(name.startswith(p+'9MetaClass') for p in prefixes),'Unreviewed experimental loader function: '+name)
        for relocation in function['relocations']:
            target=relocation['target']
            if 'external' in target:
                require(target['external'] in externals and target['addend']==0,'Unreviewed experimental loader external/addend')
                seen_external.add(target['external'])
            elif 'data' in target:
                require(target['data'] in data and target['addend']==data[target['data']], 'Unreviewed experimental loader data/addend')
                seen_data.add(target['data'])
            elif 'cstring' in target:
                require(target['cstring'] in CLASSES,'Unreviewed experimental registration class name')
                seen_names.add(target['cstring'])
    require(seen_external==externals and seen_data==set(data) and seen_names==set(CLASSES),
            'Incomplete experimental SDK registration inventory')
    digest=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return dict(status='exact-two-experimental-metaclass-reference-match', classes=list(CLASSES),
        actual_object_sha256=digest(actual), reference_object_sha256=digest(reference),
        graph_sha256=hashlib.sha256(combined.canonical(reviewed).encode()).hexdigest(),loader_entries=2)

def verify(actual,power_reference,experimental_reference):
    old._review_reference(old.Object(power_reference).loader_graph())
    loader_graph(experimental_reference,experimental_reference)
    expected=combined.entry_inventory(power_reference)+combined.entry_inventory(experimental_reference)
    observed=combined.entry_inventory(actual)
    require(sum(expected.values())==4 and observed==expected,
            'Complete image loader code differs from the three exact SDK metaclasses')
    return dict(status='matched-current-combined-metaclass-codegen',
        classes=[old.CLASS_NAME,*CLASSES],loader_entries=4,every_loader_pointer_compared=True,
        image_sha256=hashlib.sha256(Path(actual).read_bytes()).hexdigest(),
        power_reference_sha256=hashlib.sha256(Path(power_reference).read_bytes()).hexdigest(),
        experimental_reference_sha256=hashlib.sha256(Path(experimental_reference).read_bytes()).hexdigest(),
        entry_inventory_sha256=hashlib.sha256(combined.canonical(sorted(expected.elements())).encode()).hexdigest(),
        production_candidate_allowed=False,kernel_execution='not_tested')
