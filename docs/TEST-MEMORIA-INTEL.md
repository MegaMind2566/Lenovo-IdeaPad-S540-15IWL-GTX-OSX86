# Prova mirata della memoria framebuffer Intel

Il panic ricevuto dopo la traccia diretta è stato localizzato nel driver AppleIntelCFLGraphicsFramebuffer effettivamente caricato. Il requisito minimo di memoria stolen supera quello che il driver calcola dal firmware. Questa prova riduce il requisito con proprietà WhateverGreen documentate, conservando la coppia Whiskey Lake già applicata.

## Evidenza dal dump

L'archivio contiene il dump Mach-O del driver e i config originali, della prova normale e della Recovery. Gli hash dei config e dei due kext originali sono validi. La coppia `0900A53E` / `A53E0000` è presente in tutti i config. Quello normale non contiene VESA né proprietà di memoria framebuffer. Il config Recovery attuale coincide byte per byte con lo snapshot previsto.

La prima riga del panic non è visibile nella foto, ma il dump permette di ricostruirne la causa attraverso entrambi gli indirizzi di ritorno:

| Punto relativo al driver | Verifica |
|---|---|
| `0x357bf` | Chiamata alla routine di errore; l'indirizzo successivo `0x357c4` coincide con GetUnifiedMemorySize nella foto |
| `0x92eb7` | Routine che stampa l'asserzione `minStolenSize <= fStolenMemorySize`, AppleIntelController.cpp, riga 29505 |
| `0x92ef3` | Chiamata panic; l'indirizzo successivo `0x92ef8` coincide con FramebufferTerminate nella foto |
| `0x353fa` / `0x353fd` | Confronto della memoria disponibile con il minimo richiesto; il ramo unsigned inferiore raggiunge la chiamata dell'errore |

Il profilo WHL nel dump dichiara 57 MB stolen e 1 MB di riserva nel calcolo del driver: il requisito è quindi 58 MB. Il driver calcola il valore disponibile da GGC PCI, offset 0x50. L'errore dimostra che il risultato è inferiore al requisito. Il valore di 32 MB meno 4 KB è l'inferenza compatibile con quel calcolo per un'allocazione non nulla, non una misura indipendente del BIOS.

L'uptime della foto è circa 51,098 secondi. La lettura precedente di cinque secondi era errata. Il file del driver è presente; il log Lilu previsto dopo 60 secondi è assente. I report non contengono un nuovo panic completo.

## Modifica proposta

In `DeviceProperties/Add/PciRoot(0x0)/Pci(0x2,0x0)` vengono aggiunte esclusivamente queste proprietà Data di quattro byte:

| Proprietà | Data | Scopo |
|---|---|---|
| framebuffer-patch-enable | `01000000` | Attiva la patch semantica |
| framebuffer-stolenmem | `00003001` | Imposta il requisito stolen a 19 MB |
| framebuffer-fbmem | `00009000` | Riserva 9 MB al framebuffer |

È la combinazione prevista dalla guida Coffee Lake/Whiskey Lake per una memoria preallocata limitata. Il test normale rimuove VESA e modalità sicura. Non cambia platform-id, device-id, ACPI, connettori, unifiedmem, identità, Bluetooth, Wi-Fi o impostazioni Booter. Non scrive i registri del BIOS e non cambia l'allocazione firmware: riduce il requisito del driver.

## Applicazione

1. Da Windows estrarre **S540-memoria-Intel.zip** nella radice dell'HDD OpenCore, accanto a EFI. Accettare la sostituzione degli strumenti inclusi.
2. Eseguire **TEST-MEMORIA-INTEL.cmd**. Se trova la precedente traccia valida, il programma ripristina automaticamente Lilu, WhateverGreen e il config originali, poi salva un backup separato e applica la prova memoria. Non occorre ripristinare manualmente la traccia prima di questo comando.
3. Avviare lo stesso OpenCore e scegliere **Machintosh SSD** sul Samsung. La prova usa l'accelerazione Intel. Se appare la configurazione iniziale, proseguire; l'accelerazione Metal andrà verificata una volta raggiunta la scrivania.
4. Se compare un nuovo panic, conservare la prima riga e la foto. Per riaprire la Recovery da Windows usare **RECOVERY-MEMORIA-INTEL.cmd**: mantiene le proprietà di memoria e aggiunge VESA.
5. Per annullare la prova usare **RIPRISTINA-MEMORIA-INTEL.cmd**: ripristina byte per byte il config salvato dopo l'uscita dalla traccia. Le altre modifiche successive al config vengono rilevate e il ripristino automatico viene rifiutato.

I vecchi comandi della traccia restano riferiti al loro backup precedente. Per questa prova usare i tre comandi MEMORIA-INTEL. Se il sistema resta bloccato, il collector incluso può raccogliere anche i config della prova memoria dalla Recovery; non è necessario reinstallare macOS per applicare queste proprietà.

Il backup è `EFI/OC/config.before-intel-memory.plist`, con un manifest JSON e i due snapshot `config.intel-memory.normal.plist` / `config.intel-memory.recovery.plist`. Conservare questi quattro file. Il collector li include quando presenti; l'eventuale dump framebuffer precedente resta un dato della vecchia traccia. Inoltre WhateverGreen scrive il dump prima delle patch, quindi una tabella originale nel file non dimostra che una patch successiva sia stata ignorata.

La correzione è giustificata dal panic specifico. Il suo esito fisico e l'eventuale presenza di problemi successivi restano da verificare sul portatile.

## Verifica dello strumento

Sono passati nove gruppi di prove su applicazione, autorestore della traccia, conservazione degli altri campi, Recovery, ripristino esatto, modifiche successive, backup incompleti/alterati e guasto della scrittura. Una prova separata sulla copia della EFI consegnata, con i backup e il config Recovery dell'ultimo archivio, ha verificato l'intero passaggio DEBUG → kext originali → patch memoria. I config normale e Recovery generati superano ocvalidate 1.0.8; il ripristino restituisce i byte esatti del config e dei kext pre-traccia. Il collector copia anche tutti e quattro i file privati della prova memoria. I test sono stati eseguiti in Linux; i launcher Windows e l'avvio fisico restano da eseguire sul portatile.

## Riferimenti primari

- [WhateverGreen 1.7.1, custom framebuffer patching](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md#custom-patching).
- [Dortania, Coffee Lake/Whiskey Lake, proprietà per DVMT limitato](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties).
- [WhateverGreen 1.7.1, struttura delle tabelle framebuffer](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/IntelFramebuffer.bt).
