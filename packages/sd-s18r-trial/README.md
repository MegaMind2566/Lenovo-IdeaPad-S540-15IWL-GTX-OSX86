# S540 S18R-disabled external SD trial

Experimental candidate for the already reviewed BigSurSDXC 1.9.0 x86_64 image and direct-match Info.plist. The 8 GB FAT32 card is Windows-readable; the target trace identified a failed 1.8 V transition path before media publication. This trial avoids requesting S18R at two ACMD41 sites and stamps a distinct runtime UUID.

The builder requires exact local inputs; no download, install, EFI edit or native execution occurs:

```sh
python3 builders/build_sd_s18r_candidate.py \
  --binary /path/to/original/BigSurSDXC.kext/Contents/MacOS/BigSurSDXC \
  --info /path/to/direct-baseline/BigSurSDXC.kext/Contents/Info.plist \
  --collector-source packages/sd-s18r-trial/RACCOGLI-STATO-SD.template.command \
  --output-dir build/sd-s18r
```

The binary is pinned to SHA-256 `dfb316e5e4ce745da6dbbb7470af1720e6719741e2a900aff3b3114e35060bd7`; the current direct-match Info.plist to `d3dc9a76442bddf030389ea527045070a8e08153edb6b926ce3d60ddc70f4ae2`. The two four-byte patches and 16 UUID bytes are the only changes. ARM, layout and the embedded upstream signature blob remain unchanged; the original and candidate are not claimed to have valid Apple signatures.

Use only the external test EFI and the supplied exact rollback. Do not change ACPI, NVIDIA, NVRAM, SIP or the internal EFI. The older initialization-trace wrapper pins the original UUID; use this package's passive collector for this candidate. Boot admission, actual media reading, speed and wake/hotplug behavior remain target observations, not packaging results. See [evidence and limits](../../docs/status/sd-fingerprint.md).
