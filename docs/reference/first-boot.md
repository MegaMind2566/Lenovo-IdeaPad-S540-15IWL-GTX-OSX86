> Historical initial-template procedure. This workflow is archived. For the current release, use the [EFI setup instructions](../../packages/efi/README.md).

# First boot with a Samsung 960 EVO over USB-C

This guide describes the initial test configuration for the Lenovo IdeaPad S540-15IWL GTX, BIOS BWCN19WW. Automated checks validate its files and configuration; booting and peripherals require testing on the laptop.

## Download the package

In the repository, open **Actions**, select the initial EFI test workflow and its latest successful run, then download the **S540-81SW-Tahoe-prima-prova** artifact. Extract the artifact ZIP, then the package ZIP it contains. The resulting folder should contain an `EFI` folder and `SCARICA-RECOVERY.cmd` alongside it.

## Prepare the files in Windows

1. Install [Python 3 for Windows](https://www.python.org/downloads/windows/) if it is not already installed. The `py` launcher or `python` command must work.
2. Run **SCARICA-RECOVERY.cmd**. It downloads the official Apple Recovery image compatible with the selected Intel model. Wait for completion: `BaseSystem.dmg` and `BaseSystem.chunklist` are downloaded into `com.apple.recovery.boot`.
3. Run **CONFIGURA-WIFI.cmd** and enter the network SSID and password. `itlwm` uses that profile to attempt automatic connection, including in Recovery. The network is presented as Ethernet rather than through Apple's normal Wi-Fi menu. Recovery connectivity requires testing on the laptop.
4. Use a **separate USB drive of at least 8 GB that can be erased**. In [Rufus](https://rufus.ie/), select it after checking its model and capacity, then choose **Non bootable**, **GPT** and **FAT32**. Formatting erases the selected USB drive. Keep the 960 EVO disconnected during this step.
5. Copy `EFI` and `com.apple.recovery.boot` to the USB drive's root. The boot file must be at `EFI/BOOT/BOOTx64.efi`, not `EFI/EFI/BOOT/...`.

The Wi-Fi profile stores the password in the local plist. Do not upload an EFI configured with your network credentials to GitHub or chat. The scripts do not send SSIDs or passwords and do not format disks.

Keep `IDENTITA-SMBIOS.json` with the package. It preserves the same identifiers across future revisions. A new build without that file generates different identifiers; avoid connecting Apple services at this stage.

## Test booting

1. Shut down the laptop. Connect the USB boot drive to USB-A and the **960 EVO to USB-C**, using the enclosure and cable intended for regular use. Disconnect other external disks.
2. In the BIOS, leave **Secure Boot disabled** and use UEFI boot. Do not change the internal disk mode or update the BIOS for this test.
3. Open the Lenovo boot menu with **F12/Fn+F12** or the **Novo** button, then select the UEFI USB drive.
4. In OpenCore, choose **macOS Base System** or the Recovery entry. Diagnostic boot text is expected.
5. For the first test, stop at **macOS Utilities**. Check the keyboard, touchpad, Internet connection and USB-C disk in Disk Utility. Record the external disk's model and capacity without erasing it.

Report the result and provide a readable photograph of the last screen if booting stalls. `opencore-*.txt` logs are saved at the USB drive's root. The build-validation log is included as `ocvalidate.txt`.

## Configuration contents

- OpenCore 1.0.8 DEBUG, with OpenRuntime and HfsPlus drivers.
- `MacBookPro16,2`, an Intel model supported by Tahoe. Power management on the Whiskey Lake processor still requires verification at this stage.
- UHD 620 with platform `00009B3E` and device-id `9B3E0000`. DVMT has not yet been measured; no memory correction is added without a specific error.
- The project's six compiled SSDTs. The NVIDIA power-off patch is **disabled** for the first test; `-wegnoegpu` prevents its driver from loading but does not guarantee electrical power-off.
- The laptop's nine-port USB map, with `XhciPortLimit` disabled.
- VoodooPS2 for the keyboard; VoodooI2C and VoodooI2CHID for ELAN0662.
- VirtualSMC, SMCProcessor and SMCBatteryManager; battery readings require verification.
- `itlwm` for Intel AC9560; [HeliPort](https://github.com/OpenIntelWireless/HeliPort/releases/tag/v1.5.0) can be used after installation.
- IntelBluetoothFirmware and BlueToolFixup enabled. IntelBTPatcher 2.4 is present but excluded from subsequent builds after a USB/Bluetooth panic; `-ibtcompatbeta` is removed. For the already delivered EFI, use the [reversible Bluetooth test](../guides/bluetooth.md). Bluetooth requires verification at this stage.
- AppleALC loads **only on Sequoia**, initially using layout 11. Analog audio has not yet been restored on Tahoe in this initial configuration.
- SIP enabled; `SecureBootModel=Disabled` and RestrictEvents with `revpatch=sbvmm` for the Tahoe update path.

## Internal disk and limitations

The configuration attempts to block `com.apple.iokit.IONVMeFamily` in macOS. The internal PM981a was nevertheless reported visible in Recovery, so exclusion is not confirmed. The USB-connected 960 EVO uses the USB stack. If it is installed internally, the NVMe configuration must be reviewed before booting. The Windows disk remains installed; its firmware is not modified.

Start Windows directly from the Lenovo boot menu during testing. HDMI, analog audio on Tahoe, sleep, brightness, Bluetooth and battery life still require testing or completion for this initial configuration.

In the USB inventory, the RTL9210 enclosure appears on USB-C at USB 2 speed. Its associated SuperSpeed port is included in the map but has no detected device. Check the USB 3 cable and test both connector orientations. The bridge name does not establish the model or capacity of the enclosed disk.

If booting stops at `EXITBS:START`, collect the log before changing settings. The first attempt uses `RebuildAppleMemoryMap=true`, `SyncRuntimePermissions=true` and `EnableWriteUnprotector=false`. An alternative for firmware without a memory-attributes table must be selected from the log evidence.

## References

- [OpenCore 1.0.8](https://github.com/acidanthera/OpenCorePkg/releases/tag/1.0.8)
- [Coffee Lake / Whiskey Lake guide](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html)
- [Tahoe notes](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html)
- [USBToolBox connector types](https://github.com/USBToolBox/tool/blob/master/TYPES.md)
- [itlwm Wi-Fi configuration](https://openintelwireless.github.io/itlwm/FAQ.html)
