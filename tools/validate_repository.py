#!/usr/bin/env python3
"""Check source syntax, metadata and local documentation links without device access."""
import ast
import json
from pathlib import Path
import plistlib
import re
import subprocess
from urllib.parse import unquote, urlsplit


def main():
    root = Path(__file__).resolve().parents[1]
    failures = []
    count = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(part in ('build', '.git', '__pycache__') for part in path.relative_to(root).parts):
            continue
        count += 1
        try:
            if path.suffix == '.py':
                ast.parse(path.read_text(), filename=str(path))
            elif path.suffix == '.json':
                json.loads(path.read_text())
            elif path.suffix == '.plist':
                plistlib.loads(path.read_bytes())
            elif path.suffix in ('.sh', '.command'):
                subprocess.run(['bash', '-n', str(path)], check=True, capture_output=True)
            elif path.suffix == '.md':
                text = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
                for target in re.findall(r'\]\(([^\n)]+)\)', text):
                    target = target.split(' "', 1)[0].strip('<>')
                    parsed = urlsplit(target)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    destination = (path.parent / unquote(parsed.path)).resolve()
                    if not destination.exists():
                        failures.append(f'{path.relative_to(root)}: link assente {target}')
        except (SyntaxError, ValueError, OSError, subprocess.CalledProcessError) as error:
            failures.append(f'{path.relative_to(root)}: {error}')
    for relative in (
        'tools/microphone_driver_test.sh', 'tools/verify_microphone_driver.sh',
        'tools/build_audio_microphone.py', 'patches/audio-microphone/input-gain.patch',
        'INSTALLA-MICROFONO.command', 'ANNULLA-MICROFONO.command',
        'VERIFICA-MICROFONO.command', 'docs/MICROFONO-FIX.md',
        'archive/README.md', 'docs/README.md',
    ):
        if not (root / relative).is_file():
            failures.append(f'File attivo necessario assente: {relative}')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'PASS: {count} file; sintassi, metadati e collegamenti locali verificati.')


if __name__ == '__main__':
    main()
