#!/usr/bin/env python3
"""Verify exact V3 input and materialize this isolated eight-file source overlay."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from common import HERE, REPO, V3, original, contract, output_path, sha, write_json

def prepare(upstream: Path, v3_root: Path | None, output: Path) -> dict:
    upstream = upstream.resolve(strict=True)
    output = output_path(output, upstream)
    frozen = contract()
    checked, _ = original._checked_profile(upstream)
    v3_contract = json.loads((V3 / 'PROSPECTIVE-SOURCE-PROFILE.json').read_text())
    expected_files = dict(checked['files'])
    for name, digest in v3_contract['final_sources_sha256'].items():
        expected_files[name] = {**expected_files[name], 'sha256': digest}
    if v3_root is None:
        v3_root = output / 'materialized-v3'
        source = v3_root / 'source'
        if not source.exists():
            patch = (V3 / 'all-prospective-overlays-from-raw.patch').read_bytes()
            if sha(patch) != v3_contract['patch_sha256']['raw_to_v3']:
                raise ValueError('Frozen raw-to-V3 patch changed.')
            raw = {name: (upstream / name).read_bytes() for name in expected_files}
            raw.update(original._strict_patch(raw, patch))
            source.mkdir(parents=True)
            for name, row in expected_files.items():
                data = raw[name]
                if sha(data) != row['sha256']:
                    raise ValueError('Raw replay does not produce exact V3: ' + name)
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o755 if row['mode'] == '100755' else 0o644)
            write_json(v3_root / 'materialized-source.json', {
                'format': 1, 'profile': v3_contract['profile'], 'source_only': True,
                'compiled': False, 'original_entry_admission': False})
    else:
        v3_root = v3_root.resolve(strict=True)
        if output.is_relative_to(v3_root) or v3_root.is_relative_to(output):
            raise ValueError('Output must be separate from an explicitly supplied V3 input tree.')
        source = v3_root / 'source'
    original._verify_workspace(source, {'files': expected_files})
    before = {}
    for row in frozen['sources']:
        name = row['path']
        raw = (upstream / name).read_bytes()
        if sha(raw) != row['upstream_sha256']:
            raise ValueError('Pinned upstream source changed: ' + name)
        before[name] = (source / name).read_bytes()
        if sha(before[name]) != row['exact_v3_sha256']:
            raise ValueError('Exact V3 original input changed: ' + name)
    changed = original._strict_patch(before, (HERE / frozen['patch']).read_bytes())
    if set(changed) != set(before):
        raise ValueError('Candidate patch changes an unexpected original source set.')
    for row in frozen['sources']:
        name = row['path']
        if sha(changed[name]) != row['candidate_sha256']:
            raise ValueError('Candidate source hash changed: ' + name)
        target = output / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(changed[name])
    manifest = {'format': 1, 'profile': frozen['profile'], 'source_contract': frozen,
        'source_contract_sha256': sha((HERE / 'SOURCE-CONTRACT.json').read_bytes()),
        'base_source': str(source), 'v3_full_inventory_verified': True,
        'base_source_count': len(expected_files), 'output': str(output),
        'base_sha256': {p: sha(v) for p, v in before.items()},
        'candidate_sha256': {p: sha(v) for p, v in changed.items()},
        'production_candidate_allowed': False, 'original_entry_admission': False}
    write_json(output / 'source-manifest.json', manifest)
    return {'original': {p: v.decode() for p, v in before.items()},
            'proposed': {p: v.decode() for p, v in changed.items()},
            'base_source': source, 'source': output / 'source', 'manifest': manifest}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--v3-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.upstream, args.v3_root, args.output)
    print(json.dumps({'prepared_sources': len(result['proposed']),
        'v3_full_inventory_verified': True, 'original_entry_admission': False}))

if __name__ == '__main__':
    main()
