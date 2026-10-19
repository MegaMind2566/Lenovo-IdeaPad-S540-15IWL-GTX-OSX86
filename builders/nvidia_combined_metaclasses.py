#!/usr/bin/env python3
"""Verify the exact loader code of the combined three-class development image.

This compares every actual loader-table pointer and its reachable bytes to
independent SDK references. It grants no original RM, kernel or GPU admission.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

import nvidia_metaclass_initializers as metaclass

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / 'packages/nvidia-gsp-bootstrap/prospective-loader'


def entry_graphs(image: metaclass.Object) -> list[dict]:
    """Keep distinct TU roots while checking all original table relocations.

    The frozen single-class parser canonicalizes TU wrapper names; its one
    graph cannot contain multiple such wrappers. This standalone successor
    uses the same exact byte/relocation rules per actual loader pointer.
    """
    roots = []
    for section in image.sections:
        kind = section.flags & 0xff
        if section.name in metaclass.OTHER_LOADER_NAMES or kind == 0x16:
            raise ValueError('Unreviewed alternate loader table.')
        if section.name not in metaclass.LOADER_TYPES and kind not in metaclass.LOADER_TYPES.values():
            continue
        if metaclass.LOADER_TYPES.get(section.name) != kind or section.size % 8:
            raise ValueError('Unexpected loader table name/type/alignment.')
        relocations = image.relocations(section)
        if [r.offset for r in relocations] != list(range(0, section.size, 8)):
            raise ValueError('Every loader pointer requires one exact relocation.')
        for relocation in relocations:
            if relocation.pc_relative or relocation.kind != 0 or relocation.width != 8:
                raise ValueError('Unexpected loader-pointer relocation encoding.')
            target, function = image.target(section, relocation)
            if function is None:
                raise ValueError('Loader table does not target local named code.')
            roots.append((section.name, target, function))
    result = []
    for section_name, target, root in roots:
        pending, functions = [root], {}
        while pending:
            function = pending.pop()
            name = metaclass._function_name(function.name)
            if name in functions:
                if functions[name]['symbol'] != function:
                    raise ValueError('Multiple functions collapse within one loader entry.')
                continue
            section = image.sections[function.section-1]
            if (section.name != '__text' or section.segment != '__TEXT' or
                    section.flags & 0x80000400 != 0x80000400):
                raise ValueError('Loader code is outside executable text.')
            end = min([s.value for s in image._defined(function.section) if s.value > function.value],
                      default=section.address+section.size)
            start = function.value-section.address
            code = bytearray(image.data[section.offset+start:section.offset+end-section.address])
            relocations = []
            functions[name] = {'symbol': function}
            for relocation in image.relocations(section):
                if not start <= relocation.offset < end-section.address:
                    continue
                if relocation.offset+relocation.width > end-section.address:
                    raise ValueError('Relocation crosses loader atom boundary.')
                resolved, called = image.target(section, relocation)
                relative = relocation.offset-start
                code[relative:relative+relocation.width] = b'\0'*relocation.width
                relocations.append({'offset': relative, 'kind': relocation.kind,
                                    'pc_relative': relocation.pc_relative,
                                    'width': relocation.width, 'target': resolved})
                if called is not None:
                    pending.append(called)
            last = max((r['offset']+r['width'] for r in relocations), default=0)
            functions[name].update(code=metaclass._without_alignment_nops(code, last).hex(),
                                   relocations=relocations)
        result.append({'entries': [{'section': section_name, 'offset': 0, 'target': target}],
                       'functions': {name: {k: v for k, v in value.items() if k != 'symbol'}
                                     for name, value in sorted(functions.items())}})
    return result


def canonical(graph: dict) -> str:
    return json.dumps(graph, sort_keys=True, separators=(',', ':'))


def entry_inventory(path: Path) -> Counter:
    return Counter(canonical(graph) for graph in entry_graphs(metaclass.Object(path)))


def verify(actual: Path, power_reference: Path, loader_reference: Path) -> dict:
    # Each reference is reviewed independently by the original narrow verifier.
    # Passing a larger observed image as its own reference is not sufficient:
    # these verifiers reject any extra class, external, loader or data target.
    power = metaclass.Object(power_reference).loader_graph()
    metaclass._review_reference(power)
    spec = importlib.util.spec_from_file_location('s540_combined_loader_reference',
                                                LOADER / 'check_loader.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.loader_graph(loader_reference, loader_reference)
    expected = entry_inventory(power_reference) + entry_inventory(loader_reference)
    observed = entry_inventory(actual)
    if observed != expected:
        raise ValueError('Combined image loader code differs from independent SDK references: '
                         + canonical({'missing': list((expected-observed).elements()),
                                      'extra': list((observed-expected).elements())}))
    if sum(expected.values()) != 4:
        raise ValueError('Expected two genuine initializer/finalizer pairs.')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {'format': 1, 'status': 'matched-combined-metaclass-codegen',
            'classes': [metaclass.CLASS_NAME, 'S540ProspectiveLoaderControl',
                        'S540ProspectiveLoaderClient'],
            'loader_entries': sum(observed.values()),
            'every_loader_pointer_compared': True,
            'image_sha256': digest(actual),
            'power_reference_sha256': digest(power_reference),
            'loader_reference_sha256': digest(loader_reference),
            'entry_inventory_sha256': hashlib.sha256(canonical(sorted(expected.elements())).encode()).hexdigest(),
            'kernel_execution': 'not_tested', 'production_candidate_allowed': False,
            'aggregate_stack_proven': False, 'gpu_access': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'power-reference', 'loader-reference', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.image.resolve(strict=True), args.power_reference.resolve(strict=True),
              args.loader_reference.resolve(strict=True)]
    output = args.output.resolve()
    if output in inputs or output.exists():
        raise ValueError('Fresh output distinct from all input objects required.')
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    result = verify(*inputs)
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in before.items()):
        raise ValueError('A metaclass input changed during verification.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'status': result['status'], 'loader_entries': result['loader_entries'],
                      'production_candidate_allowed': False}))


if __name__ == '__main__':
    main()
