# S540 Tasti

Functional integration of the missing Lenovo IdeaPad S540-15IWL GTX (81SW)
hotkeys: microphone mute (F4), Wi-Fi/Bluetooth power and restoration (F7),
firmware camera power (F8), and macOS screen lock request (Fn+F9).

The kernel component matches VPC2004/VPC0 only and requires the observed
`_CFG=0xFE0D0014`. Deferred ACPI notifications expose a versioned immutable
snapshot and a bounded numeric event ring. It uses the VPC protocol already
implemented in Linux ideapad-laptop and YogaSMC, restricted to event reads and
the camera power command. It does not implement sensors, battery policy, fans,
Fn-mode or arbitrary ACPI operations. There is no user write interface.

The Cocoa companion performs microphone and radio actions through macOS APIs.
It never records audio or general keyboard events. A narrowly matched PS/2 F9
listener is opt-in and requires Input Monitoring and Accessibility. Direct F9
is indistinguishable from the ordinary Command+L sequence on this keyboard;
that sequence is deliberately preserved. Fn+F9 requests Control+Command+Q.

Camera ownership is not inferred from capability flags. An observed change
since the valid baseline is accepted without writing; an unchanged state on a
fresh camera key event is toggled once and read back. Failure disables camera
writes until a fresh load or wake baseline. This is a guarded integration policy,
not a claim that the complete combination has already been tested on the laptop.

The installer preserves the existing EFI, bootloader chain, Windows and audio
driver. It tracks exactly the installed bundles and user LaunchAgent for restore.
Read `LEGGIMI.txt` for the single installation and functional check.

Host fixtures, native compilation, packaging, target loading and actual function
are distinct milestones. Native CI does not load the driver or change host radios.

## References

- Linux `ideapad-laptop.c`, commit
  `5029bff09e79ad80883c5ee2828b8c4a263cf3dd`, VPC command handshake and camera
  read/write commands: <https://github.com/torvalds/linux/blob/5029bff09e79ad80883c5ee2828b8c4a263cf3dd/drivers/platform/x86/lenovo/ideapad-laptop.c>.
- YogaSMC 1.5.3, commit `0a7a35e1d9aa816137a2d8d5c3ab92a2c6a52121`,
  IdeaVPC event bits and ACPI implementation:
  <https://github.com/zhen-zen/YogaSMC/tree/0a7a35e1d9aa816137a2d8d5c3ab92a2c6a52121>.
- ReYogaSMC, commit `99368b692a72343251b059604426e44bf65b9db3`, modern
  IdeaVPC reference: <https://github.com/hoaug-tran/ReYogaSMC/tree/99368b692a72343251b059604426e44bf65b9db3>.
- `blueutil` documents the Bluetooth controller power API used by the app:
  <https://github.com/toy/blueutil>.

No complete YogaSMC/ReYogaSMC binary or EFI from another laptop is installed.
The camera integration and radio state restoration require the final functional
check on the intended laptop. Existing F1–F3, F5, F6 and F11/F12 are not remapped.
