#!/usr/bin/env python3
"""Generate exact typed failure bindings; never synthesize scalar/void success.

Input is the original symbol names actually implemented by the selected full-RM
facades. The manifest records remaining scalar/void/data dependencies as entry
blockers. A build must not enter RM while any such reachable blocker remains.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def parameter(kind: str, name: str) -> str:
    if '(*)' in kind:
        return kind.replace('(*)', '(*' + name + ')', 1)
    if '[' in kind:
        offset = kind.index('[')
        return kind[:offset] + name + kind[offset:]
    return kind + ' ' + name


def generate(implemented: set[str]) -> tuple[str, dict]:
    record = json.loads((ROOT / 'EXTERNAL-CONTRACTS.json').read_text())
    contracts = record['contracts']
    known = {entry['symbol'] for entry in contracts}
    if not implemented <= known:
        raise ValueError('Implementation list contains unknown original symbols: ' +
                         ', '.join(sorted(implemented - known)))
    source = ['// SPDX-License-Identifier: MIT',
              '// Generated exact-ABI failure bindings; no successful service stubs.',
              '// Compile with the global namespace header and original source flags.',
              '#include "nv.h"', '#include "os-interface.h"',
              '#include "nvlink_os.h"', '#include "S540NvidiaGlobalRm.h"', '']
    refused = []
    blocked = []
    data = []
    for index, entry in enumerate(contracts):
        name = entry['symbol']
        if name in implemented:
            continue
        if entry['kind'] != 'FunctionDecl':
            data.append(name)
            continue
        result = entry['return_type']
        if result != 'NV_STATUS' and '*' not in result:
            blocked.append(name)
            continue
        if entry.get('variadic'):
            raise ValueError('A variadic refusal requires an explicit reviewed binding: ' + name)
        parameters = entry['parameters']
        args = ', '.join(parameter(item['type'], item['name']) for item in parameters) or 'void'
        source += ['// ' + entry['source'] + ':' + str(entry['line']),
                   result + ' ' + name + '(' + args + ')', '{']
        source += ['    (void)' + item['name'] + ';' for item in parameters]
        source += ['    s540GlobalRmRecordServiceName(__func__);',
                   '    s540GlobalRmRecordUnavailable(' + str(index) + ');',
                   '    return ' + ('NV_ERR_NOT_SUPPORTED' if result == 'NV_STATUS' else 'NULL') + ';',
                   '}', '']
        refused.append(name)
    output = '\n'.join(source)
    manifest = {'format': 1, 'commit': record['commit'],
                'implemented': sorted(implemented), 'failure_bindings': refused,
                'blocked_scalar_or_void': blocked, 'blocked_data': data,
                'entry_allowed': not blocked and not data,
                'scope': 'Original external ABI closure only; not runtime initialization evidence.',
                'generated_source_sha256': hashlib.sha256(output.encode()).hexdigest()}
    return output, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--implemented', type=Path, required=True)
    parser.add_argument('--source-output', type=Path, required=True)
    parser.add_argument('--manifest-output', type=Path, required=True)
    args = parser.parse_args()
    provided = json.loads(args.implemented.read_text())
    if not isinstance(provided, list) or any(not isinstance(value, str) for value in provided):
        raise ValueError('Expected an array of original symbol names.')
    if len(provided) != len(set(provided)):
        raise ValueError('Duplicate implementation symbols are invalid.')
    source, manifest = generate(set(provided))
    args.source_output.write_text(source)
    args.manifest_output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': 'ready' if manifest['entry_allowed'] else 'entry-blocked',
                      'failure_bindings': len(manifest['failure_bindings']),
                      'scalar_void_blockers': len(manifest['blocked_scalar_or_void']),
                      'data_blockers': len(manifest['blocked_data'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
