# Installation on the external Samsung 960 EVO

Recovery reached its graphical interface, with mouse, keyboard, Wi-Fi and 960 EVO detection reported working. The M.2 module had come loose inside its enclosure and was reseated. Keep using the port and cable through which the disk is now detected.

During the 13 October 2026 test, the installer displays **macOS Tahoe** and the destination **Macintosh SSD**. Installation is already in progress. The erase instructions below are for a new preparation and must not be repeated during that installation.

## Erase the target and start installation

1. On the Utilities screen, confirm that the installer entry identifies macOS Tahoe. If it names another version, record that version before proceeding.
2. Open Disk Utility and choose View → Show All Devices.
3. Select the physical external device containing the 960 EVO, at the top of its hierarchy.
4. Choose Erase. Set the name to **macOS**, the format to **APFS**, and the scheme to **GUID Partition Map**. This erases the data on the selected 960 EVO.
5. Close Disk Utility, choose **Reinstall macOS Tahoe**, and select **macOS** as the destination.
6. Keep AC power, the boot HDD and the external SSD connected. Wait for download and installation to complete.

## Restarts

Installation may restart the computer several times. Use OpenCore from the prepared boot HDD each time. When **macOS Installer** appears, select that entry to continue. At completion, select the volume by its assigned name: **Macintosh SSD** in this test, or **macOS** in the preparation example. Do not return to Recovery at every restart.

If the menu entries differ or the installer reports an error, capture a readable photograph before changing the configuration. Do not disconnect the disks during installation.

## After the first desktop

Keep the current EFI throughout installation. The optional `-igfxvesa` test argument is temporary: reaching Recovery does not confirm Intel acceleration. After reaching the desktop, follow the [Intel verification guide](../guides/intel-graphics.md), then the [hardware roadmap](../status/roadmap.md). OpenCore initially remains on the boot HDD. Moving the EFI to the external SSD follows testing of the installed system.

The internal Windows disk stays installed, as requested. Its detection in Recovery does not confirm either the effectiveness of the initial NVMe block or stability under load.

## References

- [Apple: erase a device with Disk Utility](https://support.apple.com/en-gb/guide/disk-utility/dskutl14079/mac)
- [Apple: reinstall macOS from Recovery](https://support.apple.com/en-ie/102655)
- [Dortania: installation with OpenCore](https://dortania.github.io/OpenCore-Install-Guide/installation/installation-process.html)
