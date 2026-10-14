# EFI dependency notices

The EFI redistributes the upstream components below. Copyright and license terms remain with their respective authors. The included license texts are copied from the listed release tags.

| Component | Upstream source / version |
|---|---|
| OpenCore | https://github.com/acidanthera/OpenCorePkg/tree/1.0.8 |
| Lilu | https://github.com/acidanthera/Lilu/tree/1.7.2 |
| WhateverGreen | https://github.com/acidanthera/WhateverGreen/tree/1.7.1 |
| VirtualSMC | https://github.com/acidanthera/VirtualSMC/tree/1.3.8 |
| RestrictEvents | https://github.com/acidanthera/RestrictEvents/tree/1.1.6 |
| VoodooPS2 | https://github.com/acidanthera/VoodooPS2/tree/2.3.7 |
| VoodooI2C | https://github.com/VoodooI2C/VoodooI2C/tree/v2.9.1 |
| USBToolBox | https://github.com/USBToolBox/kext/tree/1.2.0 |
| itlwm | https://github.com/OpenIntelWireless/itlwm/tree/v2.3.0 |
| IntelBluetooth | https://github.com/OpenIntelWireless/IntelBluetoothFirmware/tree/v2.4.0 |
| BrcmPatchRAM | https://github.com/acidanthera/BrcmPatchRAM/tree/2.7.2 |
| HfsPlus | https://github.com/acidanthera/OcBinaryData/tree/32500d5e3313f11cad00351ba1c6f9a4aa6cb0f7 |

Lilu's Capstone, LLVM and HDE notices are included separately. Intel firmware notices are included with itlwm and IntelBluetoothFirmware. VoodooInput is bundled by VoodooI2C.

USBToolBox 1.2.0 source files state: Copyright © 2020–2021 Dhinak G. All rights reserved. That tag does not contain a separate license file.

HfsPlus.efi is the binary supplied by OcBinaryData at the pinned commit above. That repository snapshot does not provide a separate license text for this binary. Its original licensing terms apply; this project does not assign it a new license.

The precise dependency URLs, sizes and SHA256 hashes are recorded in `manifest.json`. Custom ACPI tables and the UTBMap configuration come from this project's tracked sources.
