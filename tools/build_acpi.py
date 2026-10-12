"""Compile reviewed ACPI source files and verify every emitted AML header."""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iasl', default=shutil.which('iasl'))
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    if not args.iasl:
        parser.error('iasl compiler is required')
    root = pathlib.Path(__file__).resolve().parents[1]
    output = args.output or root / 'build' / 'acpi'
    output.mkdir(parents=True, exist_ok=True)
    compiler = subprocess.run([args.iasl, '-v'], check=True, capture_output=True, text=True).stdout.strip()
    manifest = []
    sources = sorted((root / 'acpi' / 'source').glob('*.dsl'))
    if not sources:
        raise RuntimeError('No ACPI source files found')
    for source in sources:
        prefix = output / source.stem
        result = subprocess.run([args.iasl, '-ve', '-p', str(prefix), str(source)], capture_output=True, text=True)
        (output / (source.stem + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('ACPI compilation failed: ' + source.name + '\n' + result.stdout + result.stderr)
        aml = prefix.with_suffix('.aml')
        data = aml.read_bytes()
        if len(data) < 36 or data[:4] != b'SSDT':
            raise RuntimeError('Invalid SSDT header: ' + aml.name)
        if struct.unpack_from('<I', data, 4)[0] != len(data) or sum(data) % 256:
            raise RuntimeError('Invalid SSDT length or checksum: ' + aml.name)
        manifest.append({'file': aml.name, 'length': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                         'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    (output / 'manifest.json').write_text(json.dumps({'compiler': compiler, 'tables': manifest}, indent=2) + '\n', encoding='utf-8')
    print('Compiled and verified:', len(manifest), 'SSDT tables')


if __name__ == '__main__':
    main()
