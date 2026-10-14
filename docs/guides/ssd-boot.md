# Independent boot from the external SSD

Tahoe currently runs on the external Samsung 960 EVO while OpenCore is read from the separate 240 GB HDD. The next step places the current private boot files on the SSD's existing EFI system partition.

## Observed layout

| Device in the October 14 listing | Layout | Role |
|---|---|---|
| `disk1`, external, 240.1 GB | GUID; one Microsoft Basic Data partition named `240 GB` | Current source EFI at `/Volumes/240 GB/EFI` |
| `disk2`, external, 250.1 GB | GUID; 209.7 MB EFI partition and 249.8 GB APFS partition | Samsung 960 EVO running Tahoe |

Device numbers are observations from that listing, not fixed installer settings. The helper resolves the current system's APFS backing disk and requires the verified external layout before writing.

## Transfer

Extract **S540-ssd-boot.zip** into Downloads and run:

```bash
bash "$HOME/Downloads/S540-ssd-boot/INSTALL-SSD-BOOT.command"
```

Use the source HDD connected and mounted as **240 GB**. The package checks the current source, preserves a private Desktop backup and verifies the copied BOOT and OC trees. Follow the launcher's completion message before attempting the independent boot.

The public v0.1.0 release is an earlier snapshot. This transfer uses the current private working files from the HDD. Audio installed in `/Library/Extensions` and other dependencies already present on Tahoe remain on the SSD's system volume.

## Independent boot check

1. After the helper reports a verified copy, shut down.
2. Disconnect the 240 GB HDD and leave the Samsung connected.
3. Open the Lenovo boot menu with **F12** or **Fn+F12** at power-on.
4. Select the UEFI entry for the Samsung's USB enclosure. Its name may reflect the bridge rather than Samsung.
5. Select the macOS volume in OpenCore and confirm that Tahoe reaches the desktop with the HDD disconnected.

Keep the HDD available as the existing recovery route. Reconnect it and select its UEFI entry if the new path does not reach OpenCore or the desktop. Firmware boot-order changes can follow the successful independent boot.

Copy verification establishes file integrity, not firmware detection or a successful boot. Independent SSD boot remains pending until observed on the laptop.

## References

- [Dortania: moving OpenCore to the macOS drive](https://dortania.github.io/OpenCore-Post-Install/universal/oc2hdd.html)
- [Lenovo: USB boot menu on IdeaPad](https://support.lenovo.com/sn/en/solutions/ht500207)
