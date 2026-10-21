# S540HotkeysVPC source notices

This directory is licensed under **GPL-2.0-only**; the complete license is in `LICENSE`.

The Lenovo VPC register handshake and command meanings follow the following upstream work:

- YogaSMC 1.5.3, commit `0a7a35e1d9aa816137a2d8d5c3ab92a2c6a52121`,
  [`YogaSMC/YogaVPC/IdeaVPC.cpp`](https://github.com/zhen-zen/YogaSMC/blob/0a7a35e1d9aa816137a2d8d5c3ab92a2c6a52121/YogaSMC/YogaVPC/IdeaVPC.cpp),
  particularly `read_ec_data`, `write_ec_data`, `method_vpcr`, `method_vpcw`, and notification delivery.
  Original source notice: **Created by Zhen on 2020/7/11. Copyright © 2020 Zhen. All rights reserved.**
  SPDX license in that file: `GPL-2.0-only`. The state machine in this directory is a deliberately restricted adaptation,
  with new command allowlists, error handling, power synchronization, and registry event delivery.
- Linux `ideapad-laptop`, commit `5029bff09e79ad80883c5ee2828b8c4a263cf3dd`,
  [`drivers/platform/x86/lenovo/ideapad-laptop.c`](https://github.com/torvalds/linux/blob/5029bff09e79ad80883c5ee2828b8c4a263cf3dd/drivers/platform/x86/lenovo/ideapad-laptop.c),
  consulted for capability bits and the event/camera command semantics. No Linux source file is bundled.
- Apple kernel API declarations are supplied at build time by
  [`acidanthera/MacKernelSDK`](https://github.com/acidanthera/MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164),
  commit `3f750085caa17ec3a7880f11c11bf4f48cd6a164`. That SDK is a separate dependency;
  its own copyright and license notices apply.

The adaptive camera baseline/current-state policy is new integration logic. The upstream camera/OSD capability bits
do **not** prove whether this particular firmware already toggles camera power. The driver observes a changed
camera value without writing; it requests a Boolean toggle only for a fresh, single physical event whose current
value still matches a valid baseline. This source has host-side protocol fixtures, not a claim of completed hardware validation.

This component contains no YogaSMC sensor provider, fan/battery controls, WMI methods, or arbitrary firmware interface.
