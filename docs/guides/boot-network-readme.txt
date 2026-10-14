S540 — startup panel, Bluetooth, and networking

Result from October 13, 2026: -igfxblr alone eliminated the startup panel
delay, reducing it from about two minutes to zero in the laptop trial.
If the trial is already applied and works, keep this configuration and backup.

The collection requests the first five minutes, but the received report also
included other boots and later events. The analysis separates these segments:
do not treat all events as belonging to the first five minutes.

Extract the S540-avvio-rete folder into Downloads.
Run from the Tahoe desktop with the 240 GB HDD connected.

1. Collect the current state:
   bash "$HOME/Downloads/S540-avvio-rete/RACCOGLI-AVVIO-RETE.command"

   The password is needed to read logs. The command creates
   DIAGNOSI-AVVIO-RETE-XXXXXX.zip on the Desktop. Attach that file to the chat.
   The ZIP contains private data: do not publish it in the repository.

2. Prepare the panel trial:
   bash "$HOME/Downloads/S540-avvio-rete/TEST-SCHERMO-AVVIO.command"

   Check the final message. If the trial is cancelled, the configuration is
   not changed: send the message and the collected ZIP.
   If it is prepared, reboot from the same OpenCore HDD and compare the time
   spent with the panel off against the previous delay of about two minutes.

   This trial adds only -igfxblr. It does not change the framebuffer, memory,
   audio, SIP, drivers, or partitions. Success on the laptop must be checked.

3. After rebooting, check the active argument:
   sysctl -n kern.bootargs

   It must include -igfxblr. If it is absent, the kernel did not try the fix.

Restore before making any other EFI changes:
   bash "$HOME/Downloads/S540-avvio-rete/ANNULLA-SCHERMO-AVVIO.command"

The backup remains in EFI/OC/backup-schermo-avvio. Restore does not overwrite
configurations changed by other trials. To return to the previous state when
Tahoe cannot reach the desktop, run the undo command from Recovery Terminal
or privately copy before.plist from the backup to EFI/OC/config.plist.
Keep the other backups.

The old IntelBTPatcher 2.4 remains disabled. The collection reads firmware,
controller state, and Bluetooth NVRAM variables without enabling that patcher.
Wi-Fi with itlwm appears as Ethernet by design. Native Wi-Fi integration on
Tahoe is a separate task to evaluate.

Local checks: Bash syntax and simulated fixtures. No actual macOS boot was
performed here. The panel trial is restricted to the analyzed CFL driver.
