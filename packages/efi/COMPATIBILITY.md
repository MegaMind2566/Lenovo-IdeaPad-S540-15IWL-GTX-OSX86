# Compatibility — v0.1.0

Target: **Lenovo IdeaPad S540-15IWL GTX (81SW)** with macOS Tahoe 26. Status reflects the current complete installation; audio and Bluetooth prerequisites are described in `README.md`.

## Working

- macOS boot and desktop on the external Samsung 960 EVO.
- Intel UHD 620 acceleration, Metal 3 and internal 1920×1080 display.
- Brightness slider and startup backlight without the previous black-screen delay.
- Internal speakers, gradual volume control and F1–F3 audio keys.
- Internal microphone with the S540 VoodooHDA input-gain correction.
- Intel AC9560 Wi-Fi through itlwm and HeliPort.
- Bluetooth headphone playback.
- Webcam, CPU power management and battery detection.
- External Samsung 960 EVO access over USB.

## Not working

- NVIDIA GTX 1650 Max-Q graphics acceleration.
- F11/F12 brightness keys.
- Native macOS Wi-Fi management; use HeliPort.

## Pending

- Touchpad and gestures.
- Analog audio jack and Bluetooth microphone.
- HDMI and USB-C video output.
- USB SuperSpeed and both USB-C connector orientations.
- SD card and fingerprint readers.
- Battery runtime, sleep and wake.
- NVIDIA electrical power-off.
- Moving OpenCore from the separate USB HDD to the external SSD.

Audio equalization and the remaining function keys are planned improvements. A Linux NVIDIA driver port remains a research objective.
