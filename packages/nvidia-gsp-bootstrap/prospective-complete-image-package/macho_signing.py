"""Restrict ad-hoc signing changes to signature metadata and LINKEDIT growth."""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import uuid


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(data: bytes) -> dict:
    require(len(data) >= 32, 'Truncated signing image')
    header = struct.unpack_from('<8I', data)
    require(header[:2] == (0xfeedfacf, 0x01000007) and header[3] == 11,
            'Signing requires a thin Intel MH_KEXT_BUNDLE')
    end = 32 + header[5]
    require(end <= len(data), 'Truncated signing load commands')
    commands, sections, identifiers = [], [], []
    signature = linkedit = None
    position = 32
    for _ in range(header[4]):
        require(position + 8 <= end, 'Truncated signing command')
        kind, size = struct.unpack_from('<II', data, position)
        require(size >= 8 and size % 8 == 0 and position + size <= end,
                'Invalid signing command bounds')
        raw = data[position:position + size]
        if kind == 0x1d:
            require(signature is None and size == 16, 'Invalid code signature command')
            offset, length = struct.unpack_from('<II', raw, 8)
            require(length > 0 and offset >= end and offset + length <= len(data),
                    'Invalid code signature payload')
            signature = {'offset': offset, 'bytes': length,
                         'sha256': digest(data[offset:offset + length])}
        else:
            if kind == 0x19:
                require(size >= 72, 'Truncated signing segment')
                name = raw[8:24].split(b'\0', 1)[0].decode('ascii')
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<4Q', raw, 24)
                count = struct.unpack_from('<I', raw, 64)[0]
                require(size == 72 + 80 * count and fileoff + filesize <= len(data),
                        'Invalid signing segment bounds')
                if name == '__LINKEDIT':
                    require(linkedit is None and count == 0, 'Invalid LINKEDIT segment')
                    linkedit = {'address': vmaddr, 'virtual_bytes': vmsize,
                                'offset': fileoff, 'bytes': filesize}
                    normalized = bytearray(raw)
                    struct.pack_into('<Q', normalized, 32, 0)
                    struct.pack_into('<Q', normalized, 48, 0)
                    raw = bytes(normalized)
                for index in range(count):
                    section = raw[72 + 80 * index:152 + 80 * index]
                    fields = struct.unpack('<16s16sQQIIIIIIII', section)
                    sec, seg, address, length, offset = fields[:5]
                    flags = fields[8]
                    payload = None
                    if flags & 0xff not in (1, 0xc, 0x12):
                        require(offset >= end and offset + length <= len(data),
                                'Invalid signing section bytes')
                        payload = digest(data[offset:offset + length])
                    sections.append({'segment': seg.split(b'\0', 1)[0].decode('ascii'),
                        'name': sec.split(b'\0', 1)[0].decode('ascii'),
                        'metadata': section.hex(), 'address': address, 'bytes': length,
                        'offset': offset, 'flags': flags, 'sha256': payload})
            elif kind == 0x1b:
                require(size == 24, 'Invalid image UUID command')
                identifiers.append(str(uuid.UUID(bytes=raw[8:24])).upper())
            commands.append(raw.hex())
        position += size
    require(position == end and linkedit is not None and len(identifiers) == 1,
            'Incomplete signing image inventory')
    require(linkedit['offset'] + linkedit['bytes'] == len(data),
            'Unreviewed bytes follow LINKEDIT')
    if signature:
        require(signature['offset'] >= linkedit['offset'] and
                signature['offset'] + signature['bytes'] <= len(data),
                'Signature is outside LINKEDIT')
    start = min((s['offset'] for s in sections if s['bytes'] and s['sha256'] is not None),
                default=end)
    payload_end = signature['offset'] if signature else len(data)
    require(payload_end >= start, 'Invalid signing payload range')
    return {'header': list(header), 'normalized_commands': commands, 'sections': sections,
            'linkedit': linkedit, 'signature': signature, 'uuid': identifiers[0],
            'header_end': end, 'payload_start': start, 'payload_end': payload_end,
            'sha256': digest(data), 'bytes': len(data)}


def compare(before: Path, after: Path) -> dict:
    original, signed = before.read_bytes(), after.read_bytes()
    a, b = inspect(original), inspect(signed)
    require(b['signature'] is not None, 'Signed image lacks a signature command')
    require(all(a['header'][i] == b['header'][i] for i in (0, 1, 2, 3, 6, 7)),
            'Signing changed Mach-O header semantics')
    require(a['normalized_commands'] == b['normalized_commands'],
            'Signing changed an existing load command')
    require(a['sections'] == b['sections'], 'Signing changed section metadata or bytes')
    require(b['header_end'] - a['header_end'] in (0, 16),
            'Signing changed unexpected command-table bytes')
    padding = max(a['header_end'], b['header_end'])
    require(original[padding:a['payload_start']] == signed[padding:b['payload_start']],
            'Signing changed existing header padding')
    require(a['linkedit']['offset'] == b['linkedit']['offset'] and
            a['linkedit']['address'] == b['linkedit']['address'] and
            b['linkedit']['bytes'] >= a['linkedit']['bytes'] and
            b['linkedit']['virtual_bytes'] >= a['linkedit']['virtual_bytes'],
            'Signing changed LINKEDIT placement or shrank it')
    require(a['payload_start'] == b['payload_start'] and b['payload_end'] >= a['payload_end'] and
            original[a['payload_start']:a['payload_end']] ==
            signed[b['payload_start']:a['payload_end']], 'Signing changed existing payload bytes')
    require(not any(signed[a['payload_end']:b['payload_end']]),
            'Signing added unreviewed nonzero payload')
    sig = b['signature']
    require(not any(signed[sig['offset'] + sig['bytes']:]),
            'Signing added bytes after the signature')
    return {'status': 'signature-only-image-change-verified',
            'presign_sha256': a['sha256'], 'signed_sha256': b['sha256'],
            'uuid': b['uuid'], 'sections': b['sections'],
            'existing_load_commands_unchanged': True,
            'all_existing_payload_bytes_unchanged': True,
            'only_signature_and_linkedit_growth_allowed': True,
            'presign_linkedit': a['linkedit'], 'signed_linkedit': b['linkedit'],
            'signature': sig}
