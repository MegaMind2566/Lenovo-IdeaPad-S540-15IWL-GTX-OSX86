#!/usr/bin/env python3
"""Embed and reverify the two unmodified, release-matched NVIDIA firmware files."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/nvidia-firmware-assets'
SPEC = importlib.util.spec_from_file_location('s540_firmware_acquisition', PACKAGE / 'acquire.py')
ACQUIRE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACQUIRE)
SECTIONS = {'__s540_gsp': ('gsp_tu10x.bin', 's540_gsp'),
            '__s540_ucodes': ('ucodes_tu10x.bin', 's540_ucodes')}


def emit_assembly(assets: Path, output: Path) -> tuple[Path, dict]:
    """The caller assembles from the verified asset directory as working dir."""
    records = ACQUIRE.verify_assets(assets)
    output.mkdir(parents=True, exist_ok=True)
    lines = ['/* Generated immutable firmware bytes; complete NVIDIA agreement is packaged separately. */']
    for section, (filename, prefix) in SECTIONS.items():
        lines += ['.section __TEXT,' + section + ',regular', '.p2align 12',
                  '.globl _' + prefix + '_begin', '.globl _' + prefix + '_end',
                  '_' + prefix + '_begin:', '.incbin "' + filename + '"',
                  '_' + prefix + '_end:']
    path = output / 'S540NvidiaFirmwareBytes.S'
    path.write_text('\n'.join(lines) + '\n')
    return path, {'format': 1, 'release': ACQUIRE.MANIFEST['release'],
                  'source_commit': ACQUIRE.MANIFEST['source_commit'],
                  'assets': records, 'firmware_modified': False,
                  'assembly_contains_host_paths': False}


def verify_embedded_firmware(image: Path) -> dict:
    """Compare actual object/kext section bytes to the approved manifest."""
    data = image.read_bytes()
    if len(data) < 32:
        raise ValueError('The embedded firmware image is truncated.')
    magic, cpu, _, kind, count, _, _, _ = struct.unpack_from('<8I', data)
    if (magic, cpu) != (0xfeedfacf, 0x01000007) or kind not in (1, 11):
        raise ValueError('Embedded firmware verification requires thin Intel Mach-O object/kext.')
    offset, found = 32, {}
    expected = {item['filename']: item for item in ACQUIRE.MANIFEST['assets']}
    for _ in range(count):
        command, size = struct.unpack_from('<II', data, offset)
        if size < 8 or offset + size > len(data):
            raise ValueError('Invalid embedded firmware load-command range.')
        if command == 0x19:
            sections = struct.unpack_from('<I', data, offset + 64)[0]
            for index in range(sections):
                start = offset + 72 + index * 80
                if start + 80 > offset + size:
                    raise ValueError('Invalid embedded firmware section table.')
                section = data[start:start + 16].split(b'\0', 1)[0].decode('ascii')
                if section not in SECTIONS:
                    continue
                segment = data[start + 16:start + 32].split(b'\0', 1)[0]
                _, length, file_offset, alignment = struct.unpack_from('<QQII', data, start + 32)
                flags = struct.unpack_from('<I', data, start + 64)[0]
                if segment != b'__TEXT' or flags & 0xff or alignment < 12:
                    raise ValueError('Firmware bytes are not in the reviewed immutable regular section.')
                filename, _ = SECTIONS[section]
                if filename in found or file_offset + length > len(data):
                    raise ValueError('An embedded firmware section is duplicated or truncated.')
                digest = hashlib.sha256(data[file_offset:file_offset + length]).hexdigest()
                if length != expected[filename]['size'] or digest != expected[filename]['sha256']:
                    raise ValueError('Linked firmware bytes differ from the original NVIDIA file: ' + filename)
                found[filename] = {'size': length, 'sha256': digest,
                                   'section': '__TEXT,' + section, 'modified': False}
        offset += size
    if set(found) != {item[0] for item in SECTIONS.values()}:
        raise ValueError('The kernel image does not contain exactly the approved firmware pair.')
    return {'format': 1, 'status': 'verified', 'release': ACQUIRE.MANIFEST['release'],
            'assets': found, 'firmware_modified': False, 'gpu_executed': False}
