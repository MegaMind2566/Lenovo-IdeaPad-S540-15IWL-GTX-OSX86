"""Generate controls from exact approved osRmInitRm overlay statements.

Only the initial-status and derived-NVLink stages are extracted. The full
original lifecycle is a separate control; these generated functions are never
production source substitutions or a stand-in for that lifecycle.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def prepare(upstream: Path, output: Path) -> Path:
    package = Path(__file__).resolve().parents[1]
    root = package.parents[1]
    spec = importlib.util.spec_from_file_location(
        'registry_overlay_checked_builder', root / 'builders/compile_nvidia_global_rm.py')
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    adaptations = json.loads((package / 'upstream/ADAPTATIONS.json').read_bytes())
    item = next(entry for entry in adaptations['adaptations']
                if entry['patch'].endswith('registry-profile-init-propagation.patch'))
    baseline = (upstream / item['source']).read_bytes()
    patch = (package / item['patch']).read_bytes()
    sha = lambda value: hashlib.sha256(value).hexdigest()
    if sha(baseline) != item['upstream_sha256'] or sha(patch) != item['patch_sha256']:
        raise ValueError('The approved registry overlay input changed.')
    adapted = builder._strict_patch({item['source']: baseline}, patch)[item['source']]
    if sha(adapted) != item['adapted_sha256']:
        raise ValueError('The approved registry overlay output changed.')
    text = adapted.decode()
    initial = ('    status = RmInitRegistry();\n'
               '    if (status != NV_OK)\n'
               '        return status;\n')
    if text.count(initial) != 1:
        raise ValueError('The exact registry initialization stage changed.')
    anchor = ('    if ((osReadRegistryDword(NULL,\n'
              '                NV_REG_NVLINK_DISABLE, &data) == NV_OK) &&\n'
              '            (data == 1))\n')
    if text.count(anchor) != 1:
        raise ValueError('The original derived-NVLink stage changed.')
    start = text.index(anchor)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    block = text[start:end] + '\n'
    header = ('/* Generated from exact approved original-source stages. */\n'
              'static NV_STATUS s540TestRegistryInitStage(void)\n{\n'
              '    NV_STATUS status;\n' + initial + '    return NV_OK;\n}\n'
              'static NV_STATUS s540TestNvLinkStage(void)\n{\n'
              '    NV_STATUS status;\n    NvU32 data = 0;\n' + block +
              '    return NV_OK;\n}\n')
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'S540RegistryOverlayStages.h'
    path.write_text(header)
    (output / 'registry-overlay-stages.json').write_text(json.dumps({
        'format': 1, 'source': item['source'], 'baseline_sha256': sha(baseline),
        'adapted_sha256': sha(adapted), 'patch_sha256': sha(patch),
        'generated_header_sha256': sha(header.encode()),
        'scope': 'Two source-extracted stages; not the full osRmInitRm lifecycle.',
        'production_candidate_allowed': False, 'gpu_access': False}, indent=2) + '\n')
    return path
