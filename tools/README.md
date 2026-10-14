# Strumenti mantenuti

I comandi `.command` e `.cmd` alla radice sono punti di ingresso o sorgenti per i pacchetti. Le istruzioni di esecuzione sono nelle [guide](../docs/README.md). Gli installer microfono richiedono il pacchetto compilato: il download dei soli sorgenti non contiene il driver.

| Gruppo | File principali | Uso |
|---|---|---|
| Microfono v2 | `build_audio_microphone.py`, `microphone_driver_test.sh`, `test_audio_microphone_patch.py`, `test_microphone_installer.py` | Compilazione, installazione, verifica e ripristino della variante S540 |
| Audio iniziale e volume | `build_audio_tahoe.py`, `audio_tahoe.sh` | Preparazione VoodooHDA 3.6.8 e correzione volume v3; ripristino della prova microfono attraverso il suo pacchetto dedicato |
| Pannello all'avvio | `backlight_boot_test.sh` | Correzione `-igfxblr` e relativo annullamento |
| Avvio e rete | `collect_boot_network.sh` | Raccolta mirata del sistema installato |
| ACPI | `build_acpi.py` | Compilazione e controllo delle SSDT del progetto |
| Inventario Windows | `Raccogli-Dati.ps1` | Nuova raccolta hardware quando necessaria |
| Supporto di avvio | `reorder_boot_disk.py` | Manutenzione del disco, distinta dal riordino dei sorgenti |
| Compatibilità audio V3 | `verify_microphone_driver.sh` | Controllo della variante precedente, usato prima del backup dall'installer v2 |
| Diagnosi audio precedente | `collect_microphone.sh`, `hda_mixer_snapshot.c`, `test_microphone_driver.sh` | Raccolta protetta per VoodooHDA 3.6.8; non supporta la variante 3.6.9 |
| Struttura repository | `validate_repository.py` | Controllo di sintassi, metadati e collegamenti locali senza accesso ai dischi |

Le prove superate del primo avvio e il builder della EFI iniziale sono nell'[archivio](../archive/README.md). I wrapper di preparazione Windows in questa cartella sono sorgenti copiati alla radice dei rispettivi pacchetti; vanno usati secondo la loro guida.
