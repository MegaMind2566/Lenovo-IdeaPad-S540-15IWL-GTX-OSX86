# Roll back v0.4.0-nvidia-experimental.1

Rollback has two independent parts:

1. restore the known-good **v0.3.0 Intel EFI**, which disables NVIDIA with
   `-wegnoegpu`; and
2. remove the experimental NullMoth/NMXAudio macOS-side files and rebuild the
   Auxiliary Kernel Collection with the retained upstream uninstaller.

Do not treat one part as a substitute for the other. Keep the stable EFI,
Windows/rEFInd route and macOS-side backups until both have been verified.

## Normal rollback while macOS still boots

### 1. Preserve the failure evidence

Before changing the failed state, save the installer/verifier output and note:

- current macOS build;
- active EFI/loader path;
- whether the internal display and brightness work;
- which NVIDIA/NMXAudio bundles are reported loaded; and
- whether the failure happened before or after a restart/update.

Remove private SMBIOS, account, volume, network and NVRAM identifiers before
sharing any report.

### 2. Locate the exact prepared NullMoth package

Use the prepared package retained by the verified release kit. Its
`uninstall.sh` belongs to the same signed NullMoth 2.7.2 source that was locally
patched and installed. Do not download a current “latest” uninstaller or use a
script from a different build.

Keep the installer-created backups until the whole rollback has passed.

### 3. Run the upstream uninstaller before tightening SIP

While booted with the experimental profile's reduced SIP still applied, run the
retained `uninstall.sh` with `sudo`. Read its preflight result before allowing it
to continue.

The uninstaller is expected to:

- create a rollback copy of the current driver/KC state;
- stage every unrelated third-party kext from `/Library/Extensions`;
- build and inspect a replacement Auxiliary Kernel Collection;
- remove NullMoth GPU bundles, NMXAudio and its update/guard state; and
- publish only a collection that no longer lists the NullMoth/selector bundles.

It deliberately removes NMXAudio because that driver belongs to the experimental
HDMI path. It must preserve the separate VoodooHDA/internal-audio path and other
unrelated third-party extensions.

If the uninstaller refuses because filesystem protections are enabled, stop.
Do not manually delete half the driver tree. Boot the reviewed recovery route
that applies the required reduced-SIP state, then run the exact uninstaller
again.

If it reports a rebuild, inspection or publication failure, retain its rollback
directory and output. Do not restart until it states that the previous state was
restored or that removal completed successfully.

### 4. Restore only the stable OpenCore directory

Mount the intended EFI partition after identifying it again with
`diskutil list physical`. Disk numbers are not permanent.

Restore the private backed-up v0.3.0 `EFI/OC` directory, including its
known-working local SMBIOS identity. Preserve:

- `EFI/Microsoft`;
- the existing `EFI/BOOT` fallback/rEFInd choice;
- rEFInd configuration and firmware boot entries; and
- any other unrelated vendor directory.

Do not format the ESP and do not copy the public placeholder identity over the
working private one. Validate the restored config with OpenCore 1.0.8
`ocvalidate` before restarting.

### 5. Restart and verify the stable state

After the uninstaller has completed and the stable `EFI/OC` is restored, restart
through the known-good route. Confirm:

- `-wegnoegpu` is active and the normal Intel desktop appears;
- internal-panel brightness and F11/F12 work;
- Wi-Fi, Bluetooth, USB, touchpad and the known SD-card path retain their stable
  behavior;
- VoodooHDA internal/3.5 mm audio still works;
- NullMoth GPU bundles and NMXAudio are absent from the loaded/AuxKC inspection;
- the public/private SMBIOS distinction is intact; and
- Windows remains selectable through its native rEFInd/firmware path.

HDMI through the NVIDIA controller is expected to be unavailable again in
v0.3.0. That is the stable profile's intended boundary, not a failed rollback.

## Emergency path when the experimental EFI does not boot

Use the independently selectable v0.3.0 EFI or external recovery route to regain
the Intel desktop. Restore the stable `EFI/OC` first if needed, but do not erase
`EFI/Microsoft`, rEFInd or the experimental backup.

Once macOS is accessible, inspect the installed NullMoth/NMXAudio state before
writing to it. Run the exact retained uninstaller as described above. If it
refuses due to SIP, use a reviewed recovery config that changes only the
necessary security state; do not re-enable the failing NVIDIA framebuffer just
to reach the desktop and do not bypass the uninstaller's checks.

An EFI rollback can stop the experimental GPU from initializing, but it does not
by itself remove the files already installed under `/Library`.

## If only HDMI or brightness fails

First confirm that the complete reviewed boot-argument set is present. The
working profile requires:

```text
nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth gfxrst=4 applbkl=1
```

The known brightness regression was caused by an omitted `applbkl=1`. Do not
apply unrelated ACPI/backlight changes or duplicate NMXAudio in the EFI. If the
exact config is present and the fault remains, use the normal rollback rather
than stacking additional experimental patches.

## macOS update rollback boundary

Never copy the 25G241 Auxiliary Kernel Collection onto macOS 26.7.2 (25G332) or
another build. Kernel Collections are build- and driver-set-bound.

After an update, inspect the current build and current collection read-only.
Use a same-build rebuild from the real `/Library/Extensions` contents or return
to a full same-build system backup. Do not force the 25G241 installer/uninstaller
past a build/hash refusal and do not assume that reinstalling every component is
the correct first action.

## Actions not used as routine rollback

- Do not perform a blanket NVRAM reset unless evidence identifies an NVRAM
  problem and the consequences for the dual-boot entries are understood.
- Do not manually delete individual NullMoth kexts and leave the old Auxiliary
  Kernel Collection in place.
- Do not install generic NMXAudio over the exact-match bundle.
- Do not restore the whole EFI partition over Windows/rEFInd files.
- Do not publish the private failed EFI, Kernel Collection or unredacted logs.

After successful rollback, retain the release kit, checksums, prepared package
and sanitized diagnostics until the cause has been reviewed. They are the exact
inputs needed to reproduce or explain the transition safely.
