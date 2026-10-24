# v0.3.0 public non-NVIDIA EFI recipe

The recipe preserves the active payload of the working internal EFI, including OpenCore 1.0.8 RELEASE and the previous direct-match BigSurSDXC driver confirmed by the user. It does not include the S18R/3V3 candidate.

The public config differs from the tested private config only by placeholder SMBIOS identity fields and removal of disabled Kernel/Add and ACPI/Add entries. All 53 non-config EFI files match the active source bytes. This is an ongoing project snapshot, not a statement that all hardware works.

Run `python3 builders/build_non_nvidia_release.py --download` from the repository checkout. Existing pinned public release assets recover the exact binaries; no native compilation or toolchain is required. The final ZIP contains only `EFI/OC` as a boot payload. Its `examples/refind.conf` is a reference, not an automatic boot-manager installation.

See the versioned release instructions before merging files into an existing ESP. Preserve `EFI/BOOT`, `EFI/Microsoft`, rEFInd and firmware entries. The public identity must be personalized before booting.
