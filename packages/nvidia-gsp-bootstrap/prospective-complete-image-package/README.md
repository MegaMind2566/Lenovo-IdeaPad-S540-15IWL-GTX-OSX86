# Complete-image idle ABI packaging prerequisite

This directory is an isolated packager and reporter workflow, reconstructed as
new source after the transient workspace was lost. Its controls and evidence
must be regenerated. Local source controls do not emit a bundle. Packaging
requires a complete successful fresh native image build.

`package.py` requires Intel macOS, Apple clang, an independently supplied exact
SHA256 of the untouched strict native image report, its intact native build
tree, the same clean pinned SDK and the exact firmware/license directory. It
rechecks the composition and compilation inputs, closed loader source, strict
final imports, typed 25-root keeper and actual loader pointers. Fresh independent
SDK references validate the combined three-metaclass graph before a bundle is
created. The exact acquired notice is `NVIDIA-DRIVER-LICENSE.txt`; the archive
member name `LICENSE` is never accepted as an acquired-directory fallback.

The executing eight builder modules must have the exact canonical paths and
bytes bound by the strict native report. Two additional independently reviewed
helpers are pinned. These bindings are checked again before publication.

```sh
python3 packages/nvidia-gsp-bootstrap/prospective-complete-image-package/package.py \
  --report /absolute/native-build/first-transaction-image.json \
  --report-sha256 INDEPENDENT_NATIVE_REPORT_SHA256 \
  --kernel-sdk /absolute/clean/pinned/MacKernelSDK \
  --assets-dir /absolute/verified/firmware-assets \
  --output /absolute/fresh/S540IdleCompleteImageABI
```

The native-report hash and separately published packaging-attestation hash bind
different stages of the same image. Outputs are `packaging-attestation.json`,
`SHA256SUMS`, `S540IdleCompleteImage.kext`, `s540-idle-image-ctl`, four shell
scripts, `READ-ME-FIRST.md` and `evidence/`.

The bundle retains the actual kmod identifier/version and exact prototype's
single IOResources idle personality. Declared dependencies are Apple IOKit,
IOPCIFamily and the BSD/libkern/mach/unsupported KPIs required by independently
authored operations. Exact export/vtable acceptance remains a target loader
observation; public SDK compilation alone does not establish it.

The packager invokes native ad-hoc signing and strict verification for the
bundle and read-only controller. The strict report binds the presign image;
the packaging attestation independently binds the signed image and inventory.
The comparison permits only code-signature metadata and LINKEDIT growth. All
existing load commands, header padding outside an added signature command,
code/data section metadata and bytes, UUID, symbols, strings, imports, roots,
pointers and firmware remain unchanged. Actual final-image verifiers run again
on the signed executable.

The delivered scripts are explicit temporary load/report/normal-unload steps
described in TARGET-GUIDE.md. They never run during packaging, issue no original
entry request, install no system files and modify no security settings. All
admission and initialization fields remain closed. Synthetic Mach-O controls
and the actual loader-state decoder validate packaging logic only; they cannot
manufacture a native image pass, usable bundle or target result.
