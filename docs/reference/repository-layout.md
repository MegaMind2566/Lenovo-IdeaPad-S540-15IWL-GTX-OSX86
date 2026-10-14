# Repository layout

The root contains the project README and directories with distinct roles.

| Directory | Role |
|---|---|
| `packages/` | Runtime sources grouped by feature: launcher files and their helpers |
| `builders/` | Build and packaging entry points |
| `tests/` | Policy, installer and repository checks |
| `config/` | ACPI sources and compiled tables, hardware profiles, asset locks and USB map |
| `docs/` | Status, current guides and technical reference |
| `patches/` | Changes applied to pinned upstream driver sources |
| `licenses/` | License texts included in generated audio packages |
| `archive/` | Previous investigations and their provenance |

## Source layout and package layout

A source download is a development checkout. The microphone module does not contain its compiled driver; use a verified build artifact for installation.

Builders copy feature modules into the generated ZIP layout. Existing package names and runtime paths are retained: for example, `S540-microfono-fix-v2/INSTALLA-MICROFONO.command` and its adjacent `tools/` helpers. Moving repository sources does not change commands already supplied for downloaded packages.

The VoodooHDA 3.6.8 verifier is shared by the microphone installer and the older microphone diagnostic package. There is one source copy under `packages/microphone/tools/`; both builders copy it to the required artifact location.

## Verification

Run `python3 tests/validate_repository.py` to check source syntax, metadata, local documentation links and required package inputs without accessing device configuration. GitHub Actions also compile ACPI, run the Windows inventory collector and build/test the microphone driver on macOS Intel.

The archive's initial EFI builder remains a reference template. The private working EFI, SMBIOS identity, Wi-Fi credentials and original device reports are not part of this repository.
