#!/usr/bin/env python3
"""Compile eight complete guarded original TUs and the actual typed probe."""
from __future__ import annotations
import json
from common import HERE, REPO, original, parser, resolve_arguments, validate_sdk, sha, write_json
from prepare import prepare

def run(args) -> dict:
    args, identity = resolve_arguments(args)
    sdk = validate_sdk(args.sdk, args.sdk_archive, args.host_control)
    prepared = prepare(args.upstream, args.v3_root, args.output)
    commands = original.original_commands(args.upstream, args.output / 'full-objects', args.cc)
    source_root = prepared['base_source'] / 'src/nvidia'
    objects = args.output / 'objects'
    objects.mkdir(parents=True, exist_ok=True)
    rows = []
    for relative in (*prepared['proposed'], 'S540NvidiaGspFirstTransactionOriginal.c'):
        if relative in prepared['proposed']:
            matches = [c for c in commands if
                (args.upstream / 'src/nvidia' / c[c.index('-c') + 1]).resolve() == args.upstream / relative]
            if len(matches) != 1:
                raise ValueError('No unique original TU command: ' + relative)
            command = matches[0][:matches[0].index('-c')]
            source = prepared['source'] / relative
        else:
            command = commands[0][:commands[0].index('-c')]
            source = HERE / relative
        target = objects / ('full-' + source.stem + '.o')
        command += ['-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__', '-DNV_VERSION_STRING="615.78.08"',
            '-include', str(args.namespace), '-I', str(HERE),
            '-I', str(REPO / 'packages/nvidia-gsp-bootstrap/cancellation'),
            *(['-target', 'x86_64-macos-none'] if args.host_control else ['-arch', 'x86_64']),
            '-fPIC', '-Werror', '-Wframe-larger-than=4096', '-Werror=frame-larger-than',
            '-c', str(source), '-o', str(target)]
        original.execute(command, cwd=source_root, diagnostic_log=objects / (source.stem + '.log'))
        defined, undefined, sections = original.macho_symbols(target)
        rows.append({'source': relative, 'source_sha256': sha(source.read_bytes()),
            'object': target.name, 'object_sha256': sha(target.read_bytes()),
            'status': 0, 'command': command, 'cwd': str(source_root),
            'definitions': sorted(defined), 'imports': sorted(undefined), 'sections': sections})
    report = {'format': 1, 'status': 'eight-original-tus-and-probe-compiled', **identity,
        'cross_compile_only': args.host_control, 'sdk': sdk,
        'source_contract_sha256': prepared['manifest']['source_contract_sha256'],
        'namespace_sha256': sha(args.namespace.read_bytes()), 'results': rows,
        'v3_full_inventory_verified': True, 'original_translation_units': 8,
        'typed_probe_translation_units': 1, 'full_lock_capability_refused': True,
        'production_candidate_allowed': False, 'kernel_execution': 'not_tested',
        'gpu_access': False, 'original_entry_admission': False}
    write_json(args.output / 'full-tu-compilation.json', report)
    return report

def main():
    result = run(parser(__doc__, compile_only=True).parse_args())
    print(json.dumps({'status': result['status'], 'original_translation_units': 8,
        'typed_probe_translation_units': 1, 'cross_compile_only': result['cross_compile_only'],
        'original_entry_admission': False}))

if __name__ == '__main__':
    main()
