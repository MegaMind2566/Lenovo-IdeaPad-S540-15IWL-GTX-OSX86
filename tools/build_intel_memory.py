#!/usr/bin/env python3
"""Package the targeted Intel stolen-memory test without private configs."""
from pathlib import Path
import hashlib
import zipfile


def main():
    root = Path(__file__).resolve().parent.parent
    output = root / 'build/intel-memory'
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'S540-memoria-Intel.zip'
    files = [
        'TEST-MEMORIA-INTEL.cmd',
        'RECOVERY-MEMORIA-INTEL.cmd',
        'RIPRISTINA-MEMORIA-INTEL.cmd',
        'tools/test_intel_memory.py',
        'tools/trace_intel.py',
        'RACCOGLI-INTEL.command',
        'tools/collect_gui_logs.sh',
        'docs/TEST-MEMORIA-INTEL.md',
    ]
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        for name in files:
            target.write(root / name, name)
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:
            raise ValueError('Invalid final ZIP')
        if any(name.startswith('EFI/') for name in target.namelist()):
            raise ValueError('Unexpected EFI content in package')
    print(archive)
    print('SHA-256:', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
