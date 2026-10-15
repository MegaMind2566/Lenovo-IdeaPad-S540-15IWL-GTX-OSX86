# Matching NVIDIA firmware assets

This component acquires and verifies the unmodified NVIDIA 615.78.08 GSP/UCODES pair for TU117. It advances beyond synthetic parser fixtures: the actual two files have been extracted from NVIDIA's official archive, hashed, parsed and checked using the shared C++ implementation. The NVIDIA installer is never executed. This component does not initialize a GPU, authenticate firmware through the GPU secure-boot chain or upload firmware.

`MANIFEST.json` pins the official HTTPS archive, NVIDIA-published archive SHA256, exact archive size, exact makeself payload line/byte offset, both image sizes/hashes, GNU build-id, UCODES header fingerprint and full driver-license notice. The source references are pinned to `NVIDIA/open-gpu-kernel-modules` commit `1a82fbfda8f321b056eb3568850f9316c5e465c5`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `gsp_tu10x.bin` | 22,901,632 | `0c6124c11d59900a05ab5461e5fc7087fc6687a1badead49a7eeca6ed13eeb3b` |
| `ucodes_tu10x.bin` | 8,837,632 | `6027ab3736f733b5a06e6e61aaae957d1f990426a263849ebcfa8a49eeb4a5d0` |
| `NVIDIA-DRIVER-LICENSE.txt` | 22,653 | `c692fb14ad4f499c6aee1b9e144e6905148c420e6225b17cb2937366c1e507ad` |

TU117 selects the `.fwsignature_tu11x` section from `gsp_tu10x.bin`. The exact ELF64 release, ten sections, 4,096-byte signature section and GNU build-id are checked. The signature's presence and an approved distribution hash identify an original matching binary; this is separate from executing NVIDIA's signature verification on the GPU.

UCODES uses the published `BINDATA_UCODES_BIN_HEADER` and 24-byte native-64 storage directory. The pinned file has 496 possible entries and 38 present uncompressed external records. The parser checks header/version/count, complete directory bounds, null on-disk pointers, the selected flag profile, 256-byte payload alignment, nonempty bounded ranges and pairwise non-overlap. Empty directory records must be fully zero. Exact matching asset hashes pair the files from the same NVIDIA release; the kernel-client subset's generated bindata fingerprint is not substituted for the GSP image's fingerprint.

The pure radix3 planner follows `kgspCreateRadix3_IMPL`'s four page-count levels with 4 KiB pages and 512 entries per level. It checks overflow, the one-root limit and total allocation capacity. It computes sizes only. It neither creates page tables nor publishes addresses to a device.

`acquire.py` first verifies the complete installer archive. It locates the pinned zstd payload from header data without executing shell code, then reads tar members through bounded decompression. Extraction permits exactly two regular firmware files and the complete license; it rejects traversal, selected links/sparse files, duplicates, excess size/count and mismatched hashes. Unrelated driver files are not extracted. Assets stay outside the source repository and enter compiled packages only as the three unmodified pinned files.

The firmware remains governed by the complete [NVIDIA Driver License Agreement](NVIDIA-DRIVER-LICENSE.txt), including its redistribution conditions in section 1.1(d) and NVIDIA-platform limitations in section 2. It is separate from the MIT-licensed bridge/parser implementation. A compiled package must preserve the full unmodified agreement alongside the unmodified binaries. The intended kernel is Apple's open-source XNU; this component does not patch firmware, translate firmware or bypass its authentication.

The userspace C ABI in `src/S540NvidiaFirmwareAssets.h` reads only those three filenames using `openat`, rejects symbolic links, nonregular files and unexpected sizes, hashes actual bytes, invokes the shared parser and releases every buffer/file descriptor. Nonblocking opens prevent a FIFO from blocking before its type is checked. Reports separate `present`, `hashesVerified`, `containerParsed`, `ucodesParsed`, `pairReady` and `cleanup`. `pairReady` means that the approved pair is ready as immutable CPU input. It does not imply that hardware transport or GSP/RM startup is ready. Kernel metadata must not claim that these userspace image checks occurred inside the kernel.

Build/check example, executed on a native build host:

```bash
python3 -m pip install -r packages/nvidia-firmware-assets/requirements-build.txt
python3 builders/check_nvidia_firmware_assets.py --download --assets-dir /tmp/s540-firmware-assets --build-dir /tmp/s540-firmware-checks
```

The checker runs sixteen targeted provenance/extraction tests, the real-image native validator, and the C ABI against the real pair and eight failure paths, plain and with fatal AddressSanitizer/UndefinedBehaviorSanitizer. No installer, driver, firmware or GPU action is executed by these checks.
