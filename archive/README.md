# Previous investigations

This archive preserves the tools used before Tahoe reached the desktop. Files were moved rather than duplicated into additional ZIP packages. Follow the [current documentation](../docs/README.md) for supported procedures.

| Group | Contents | Current relevance |
|---|---|---|
| [Initial EFI](efi-iniziale/) | Original OpenCore template builder and workflow | Reference template preceding the Intel, audio and backlight fixes; it does not reproduce the private working EFI |
| [First boot](primo-avvio/) | VESA, safe boot, Whiskey Lake, framebuffer memory, Intel traces and Recovery logging | Historical investigations that led to the working desktop |
| [Trace licenses](primo-avvio/licenses/intel-trace/) | Licenses for diagnostic build dependencies | Preserved with their builders and pinned asset versions |

## Investigation notes

- [Intel framebuffer memory fix](primo-avvio/docs/TEST-MEMORIA-INTEL.md).
- [Intel tracing](primo-avvio/docs/TRACCIA-INTEL.md).
- [Boot log analysis](primo-avvio/docs/ANALISI-LOG-AVVIO.md).
- [Unified log analysis](primo-avvio/docs/ANALISI-LOG-UNIFICATI.md).
- [Recovery log collection](primo-avvio/docs/DIAGNOSI-INTERFACCIA.md).

These notes and launchers describe the package names, driver guards and conditions of their original investigation.

## Dependencies and provenance

The memory and tracing experiments share `tools/trace_intel.py`. Their internal `tools`, `docs`, `profiles` and `licenses` structure is retained so that generated diagnostic packages keep their original runtime paths. The initial EFI builder reads the shared hardware configuration under `config/` and recovery helpers under `packages/recovery/`.

Archived workflows are not run automatically by GitHub Actions. Some launchers were intended to be copied to the root of their generated packages. The original unified collector also depends on the old `diagnosi-unified` package layout; it is retained as a reference rather than a current procedure.

The [move manifest](manifest.json) records old and new paths, SHA-256 hashes and the source commit. Batch-script hashes use LF-normalized text to account for Git's CRLF checkout setting; other files are checked byte for byte. Git history preserves earlier versions. Repository maintenance does not modify the laptop's EFI or private backups.
