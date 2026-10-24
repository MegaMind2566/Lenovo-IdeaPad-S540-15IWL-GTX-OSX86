#!/usr/bin/env python3
"""Build the exact S18R-only external-EFI SD candidate; never execute its code."""
from pathlib import Path
import argparse, hashlib, json, plistlib, stat, struct, subprocess, uuid, zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "S540-SD-3V3-v1"
BINARY_SHA = "dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7"
INFO_SHA = "d3dc9a76442bddf030389ea527045070a8e08153edb6b926ce3d60ddc70f4ae2"
TEXT_SHA = "11b2fbe0068e69cb7efc772c6290323524bb7496d79e962e6728e069b54ca9d7"
SEED = "https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/sd-s18r-3v3-v1/"
def sha(data): return hashlib.sha256(data).hexdigest()
def check(ok, message):
    if not ok: raise ValueError(message)

def macho(data, offset, size):
    header = struct.unpack_from("<8I", data, offset)
    check(header[0] == 0xFEEDFACF and header[1] == 0x01000007 and header[3] == 11, "Expected x86_64 Mach-O kext")
    cursor, sections, commands = offset + 32, [], []
    for _ in range(header[4]):
        kind, length = struct.unpack_from("<II", data, cursor)
        check(length >= 8 and cursor + length <= offset + 32 + header[5], "Invalid load command")
        commands.append((kind, cursor, length))
        if kind == 0x19:
            for index in range(struct.unpack_from("<I", data, cursor + 64)[0]):
                name, segment, address, count, fileoff, *_ = struct.unpack_from("<16s16sQQ8I", data, cursor + 72 + index * 80)
                sections.append((name.rstrip(b"\0"), segment.rstrip(b"\0"), address, count, offset + fileoff))
        cursor += length
    check(cursor == offset + 32 + header[5] and cursor <= offset + size, "Invalid load-command extent")
    text, = [s for s in sections if s[:2] == (b"__text", b"__TEXT")]
    uuid_command, = [c for c in commands if c[0] == 0x1B]
    signature_command, = [c for c in commands if c[0] == 0x1D]
    symtab_command, = [c for c in commands if c[0] == 2]
    check(uuid_command[2] == 24, "Invalid LC_UUID")
    return header, commands, sections, text, uuid_command[1] + 8, signature_command[1], symtab_command[1]

def signature_pages(data, offset, command):
    relative, size = struct.unpack_from("<II", data, command + 8)
    start = offset + relative
    magic, length, count = struct.unpack_from(">III", data, start)
    check(magic == 0xFADE0CC0 and length <= size, "Invalid embedded signature container")
    directories = [struct.unpack_from(">II", data, start + 12 + 8 * i) for i in range(count)]
    cd = start + next(relative for slot, relative in directories if slot == 0)
    values = struct.unpack_from(">9I4BI", data, cd)
    _, cdlen, _, _, hashes, _, _, slots, limit, hashsize, algorithm, _, pagebits, _ = values
    check(algorithm == 2 and hashsize == 32 and pagebits == 12 and slots == 33 and limit == 135136, "Unexpected CodeDirectory contract")
    check(hashes + slots * hashsize <= cdlen and limit <= relative, "Invalid CodeDirectory bounds")
    mismatch = [i for i in range(slots) if hashlib.sha256(data[offset + i * 4096:offset + min(limit, (i + 1) * 4096)]).digest() != data[cd + hashes + 32 * i:cd + hashes + 32 * (i + 1)]]
    return {"matched_pages": slots - len(mismatch), "total_pages": slots, "mismatched_pages": mismatch,
            "blob_sha256": sha(data[start:start + size]), "blob_offset": start, "blob_bytes": size, "valid_apple_signature": False}

def collector(template, original_uuid, candidate_uuid):
    text = template.decode()
    text = text.replace("set -uo pipefail", "set -uo pipefail\numask 077")
    text = text.replace("S540_PID=\n", 'S540_RAW=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/S540-SD-raw.XXXXXX") || exit 1\nS540_PID=\n', 1)
    text = text.replace("trap cleanup EXIT", 'cleanup_all() { cleanup; /bin/rm -rf "$S540_RAW"; }\ntrap cleanup_all EXIT')
    text = text.replace('> "$S540_REPORT/$name.txt"', '> "$S540_RAW/$name.txt"')
    start = text.index("capture macos 5")
    end = text.index("printf 'Il report non dichiara", start)
    commands = r'''capture macos 5 /usr/bin/sw_vers
/bin/cp "$S540_RAW/macos.txt" "$S540_REPORT/macos.txt"
capture driver 10 /usr/bin/kmutil showloaded
printf 'UUID prova: @NEW@\nUUID ripristino: @OLD@\n' > "$S540_REPORT/driver-sd.txt"
while IFS= read -r line; do
    case "$line" in *com.apple.driver.BigSurSDXC*|*com.apple.driver.BgSurSDXC*|*com.apple.driver.AppleSDXC*)
        driver=BigSurSDXC; case "$line" in *com.apple.driver.AppleSDXC*) driver=AppleSDXC;; esac
        if [[ "$line" =~ ([[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}) ]]; then
            observed=$(printf '%s' "${BASH_REMATCH[1]}" | /usr/bin/tr '[:lower:]' '[:upper:]')
            printf '%s UUID osservato: %s\n' "$driver" "$observed" >> "$S540_REPORT/driver-sd.txt"
            if [ "$driver" = BigSurSDXC ]; then
                case "$observed" in @NEW@) printf 'Identita: candidato 3V3\n';; @OLD@) printf 'Identita: ripristino originale\n';; *) printf 'Identita: diversa/non confermata\n';; esac >> "$S540_REPORT/driver-sd.txt"
            fi
        fi;; esac
done < "$S540_RAW/driver.txt"
capture controller 10 /usr/sbin/ioreg -a -r -c BgSurSDXC -l -w0
capture slot 10 /usr/sbin/ioreg -a -r -c BgSurSDXCSlot -l -w0
capture dischi 15 /usr/sbin/diskutil list -plist
capture avvio 10 /usr/sbin/diskutil info -plist /
project() {
    local file=$1 key=$2 value
    if value=$(/usr/bin/plutil -extract "$key" json -o - "$S540_RAW/$file.txt" 2>/dev/null); then
        printf '%s = %s\n' "$key" "$value" >> "$S540_REPORT/$file-selezionato.txt"
    fi
}
for key in IOClass IONameMatched CFBundleIdentifier; do project controller "0.$key"; done
for key in IOClass 'Card Present' 'Specification Version' 'Clock Speed' 'Bus Width' 'Base Frequency' 'Clock Divisor' 'Bus Voltage' 'Card Configured'; do project slot "0.$key"; done
for key in AllDisks WholeDisks; do project dischi "$key"; done
for key in DeviceIdentifier ParentWholeDisk Internal BusProtocol FilesystemType Content TotalSize Writable Mounted; do project avvio "$key"; done
for ((index=0; index<64; index++)); do
    for key in DeviceIdentifier Content Size Internal; do project dischi "AllDisksAndPartitions.$index.$key"; done
done
printf 'Solo campi selezionati: nessun nome volume, seriale, UUID volume o dump IORegistry grezzo.\n' > "$S540_REPORT/privacy.txt"
'''.replace("@NEW@", candidate_uuid).replace("@OLD@", original_uuid)
    return (text[:start] + commands + text[end:]).replace("S540-SD-esterno.", "S540-SD-3V3.").encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "sd-probe-private/BigSurSDXC")
    parser.add_argument("--info", type=Path, default=ROOT / "sd-external-test-delivery/S540-SD-Test-Esterna-v1/Prova/BigSurSDXC.kext/Contents/Info.plist")
    parser.add_argument("--collector-source", type=Path, default=ROOT / "sd-external-test-work/RACCOGLI-STATO-SD.command")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "sd-s18r-delivery")
    args = parser.parse_args()
    original, info, template = args.binary.read_bytes(), args.info.read_bytes(), args.collector_source.read_bytes()
    check(sha(original) == BINARY_SHA and sha(info) == INFO_SHA, "Pinned binary or direct baseline Info.plist differs")
    metadata = plistlib.loads(info)
    check(metadata["CFBundleIdentifier"] == "com.apple.driver.BigSurSDXC" and metadata["CFBundleVersion"] == "1.9.0", "Unexpected baseline bundle")
    magic, count = struct.unpack_from(">II", original)
    check(magic == 0xCAFEBABE and count == 2, "Expected the exact two-slice FAT image")
    arches = [struct.unpack_from(">IIIII", original, 8 + 20 * i) for i in range(count)]
    check(all(o + s <= len(original) and o % (1 << a) == 0 for _, _, o, s, a in arches), "Invalid FAT slice bounds")
    x86, = [a for a in arches if a[0] == 0x01000007]
    arm, = [a for a in arches if a[0] == 0x0100000C]
    _, _, offset, size, _ = x86
    header, commands, sections, text, uuid_offset, sigcmd, symcmd = macho(original, offset, size)
    check(sha(original[text[4]:text[4] + text[3]]) == TEXT_SHA, "Pinned x86 __text changed")
    symbols, symbol_count, strings, _ = struct.unpack_from("<4I", original, symcmd + 8)
    function_addresses = []
    for index in range(symbol_count):
        string, kind, section, _, value = struct.unpack_from("<IBBHQ", original, offset + symbols + 16 * index)
        name = original[offset + strings + string:original.index(b"\0", offset + strings + string)]
        if section == sections.index(text) + 1 and not kind & 0xE0: function_addresses.append((value, name))
    function, = [v for v, n in function_addresses if n == b"__ZN13BgSurSDXCSlot10ProcessOCREv"]
    function_end = min(v for v, _ in function_addresses if v > function)
    candidate = bytearray(original)
    patch_records = []
    for address, absolute in ((0x98CF, 43215), (0x9955, 43349)):
        mapped = text[4] + address - text[2]
        check(mapped == absolute and function <= address < address + 4 <= function_end, "Patch is not the reviewed ProcessOCR instruction")
        check(original[mapped:mapped + 4] == bytes.fromhex("410f94c0"), "Original SETE r8b bytes differ")
        candidate[mapped:mapped + 4] = bytes.fromhex("4531c090")
        patch_records.append({"vm_address":hex(address), "file_offset":mapped, "before":"410f94c0", "after":"4531c090"})
    old_uuid = str(uuid.UUID(bytes=original[uuid_offset:uuid_offset + 16])).upper()
    new_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, SEED + BINARY_SHA)).upper()
    candidate[uuid_offset:uuid_offset + 16] = uuid.UUID(new_uuid).bytes
    changed = [i for i, (before, after) in enumerate(zip(original, candidate)) if before != after]
    expected = set(range(uuid_offset, uuid_offset + 16)) | {p["file_offset"] + i for p in patch_records for i in range(4)}
    check(len(candidate) == len(original) and set(changed) == expected and len(changed) == 24, "Unexpected changed byte set")
    masked = bytearray(candidate); masked[uuid_offset:uuid_offset + 16] = original[uuid_offset:uuid_offset + 16]
    check(masked[offset:offset + 32 + header[5]] == original[offset:offset + 32 + header[5]], "A non-UUID load/header byte changed")
    check(candidate[:offset] == original[:offset] and candidate[arm[2]:arm[2] + arm[3]] == original[arm[2]:arm[2] + arm[3]], "FAT header/padding or ARM64 slice changed")
    baseline_sig, candidate_sig = signature_pages(original, offset, sigcmd), signature_pages(candidate, offset, sigcmd)
    check(baseline_sig["matched_pages"] == 25 and baseline_sig["mismatched_pages"] == [13,14,17,24,25,26,27,32], "Baseline signature mismatch evidence differs")
    check(candidate_sig["matched_pages"] == 23 and candidate_sig["mismatched_pages"] == [0,9,13,14,17,24,25,26,27,32], "Candidate signature mismatch evidence differs")
    check(baseline_sig["blob_sha256"] == candidate_sig["blob_sha256"], "Embedded signature blob changed")
    candidate = bytes(candidate)
    report = {"schema":1, "package":NAME, "source_binary_sha256":BINARY_SHA, "direct_info_sha256":INFO_SHA,
        "candidate_binary_sha256":sha(candidate), "original_uuid_x86_64":old_uuid, "candidate_uuid_x86_64":new_uuid,
        "uuid_offset":uuid_offset, "uuid_derivation":"uuid5(NAMESPACE_URL, seed + original_binary_sha256)", "uuid_seed":SEED,
        "patches":patch_records, "changed_file_offsets":changed, "source_text_sha256":TEXT_SHA,
        "candidate_text_sha256":sha(candidate[text[4]:text[4] + text[3]]), "fat_header_and_arm64_identical":True,
        "original_x86_slice_sha256":sha(original[offset:offset + size]), "candidate_x86_slice_sha256":sha(candidate[offset:offset + size]),
        "arm64_slice_sha256":sha(original[arm[2]:arm[2] + arm[3]]),
        "non_uuid_load_commands_identical":True, "baseline_code_directory":baseline_sig, "candidate_code_directory":candidate_sig,
        "embedded_signature_preserved":True, "resigned":False, "native_code_executed":False, "target_boot_tested":False,
        "semantics":"Only the S18R boolean is forced to zero in two existing ProcessOCR call sites. HCS/XPC construction and all other instruction bytes remain unchanged.",
        "recipe_sha256":sha(Path(__file__).read_bytes()), "collector_template_sha256":sha(template)}
    guide = f'''S540 — PROVA SD A 3,3 V (CANDIDATO)

1. Salva una copia della EFI ESTERNA attuale.
2. Copia SOLO Prova/BigSurSDXC.kext in EFI/OC/Kexts della EFI ESTERNA,
   sostituendo il precedente BigSurSDXC.kext. Non cambiare config, ACPI o NVIDIA.
3. Spegni il computer. A computer spento togli e reinserisci la SD.
4. Avvia dalla EFI ESTERNA con la SD già inserita.
5. Controlla Finder e prova ad aprire un file già presente sulla scheda.
6. Se la scheda non compare, apri RACCOGLI-STATO-SD.command e invia lo ZIP
   che crea sulla Scrivania. La raccolta è passiva e non chiede password.

RIPRISTINO: avvia macOS con la EFI interna funzionante; copia
Ripristino/BigSurSDXC.kext soltanto nella EFI ESTERNA, al posto del candidato.
Spegni il computer e poi riprova l'avvio dalla EFI esterna.
Il ripristino contiene binario originale e Info.plist diretto esatti.

UUID prova: {new_uuid}
UUID ripristino: {old_uuid}
Questa prova disabilita soltanto la richiesta S18R di passaggio a 1,8 V.
Il funzionamento sul portatile resta da verificare. La firma incorporata era
già incoerente nel binario di partenza ed è conservata identica: nessuna nuova
firma Apple valida viene aggiunta. Nessun file della EFI interna è incluso.
'''.encode()
    files = {"Prova/BigSurSDXC.kext/Contents/Info.plist":(info,0o644), "Prova/BigSurSDXC.kext/Contents/MacOS/BigSurSDXC":(candidate,0o755),
        "Ripristino/BigSurSDXC.kext/Contents/Info.plist":(info,0o644), "Ripristino/BigSurSDXC.kext/Contents/MacOS/BigSurSDXC":(original,0o755),
        "MANIFEST.json":((json.dumps(report,indent=2,sort_keys=True)+"\n").encode(),0o644), "LEGGIMI.txt":(guide,0o644),
        "RACCOGLI-STATO-SD.command":(collector(template,old_uuid,new_uuid),0o755)}
    files["SHA256SUMS"] = ("".join(f"{sha(data)}  {name}\n" for name,(data,_) in sorted(files.items())).encode(),0o644)
    package = args.output_dir / NAME; package.mkdir(parents=True,exist_ok=True)
    for name,(data,mode) in files.items():
        path=package/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data); path.chmod(mode)
    subprocess.run(["/bin/bash","-n",str(package/"RACCOGLI-STATO-SD.command")],check=True)
    archive=args.output_dir/(NAME+".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for name,(data,mode) in sorted(files.items()):
            entry=zipfile.ZipInfo(NAME+"/"+name,(2026,10,24,0,0,0)); entry.create_system=3; entry.external_attr=(stat.S_IFREG|mode)<<16
            output.writestr(entry,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(archive) as output: check(output.testzip() is None and len(output.namelist())==8,"ZIP integrity/file count")
    archive.with_suffix(".zip.sha256").write_text(f"{sha(archive.read_bytes())}  {archive.name}\n")
    print(json.dumps({"archive":str(archive),"candidate_sha256":sha(candidate),"new_uuid":new_uuid,"changed_bytes":len(changed)},indent=2))
if __name__ == "__main__": main()
