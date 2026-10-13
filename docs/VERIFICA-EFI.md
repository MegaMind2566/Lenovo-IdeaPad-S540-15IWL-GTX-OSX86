# Verifica completa della EFI consegnata

Verifica del 13 ottobre 2026. Sono stati letti lo ZIP completo della prima consegna, il config.plist allegato dopo la modifica Bluetooth e il config della prova Whiskey Lake. Sono state considerate le modifiche note successive. Non è stato sostituito il contenuto della EFI sul portatile. La configurazione Wi-Fi eventualmente salvata dopo la consegna resta nella EFI attuale.

## Esito

Non sono stati trovati file mancanti, versioni OpenCore mischiate, eseguibili di architettura errata, dipendenze di kext fuori ordine o SSDT con checksum errato. La EFI consegnata contiene 55 file, circa 35,75 MB. I 55 SHA-256 corrispondono al manifest. I due ZIP della consegna superano la verifica CRC.

È stato scaricato ocvalidate dalla release ufficiale OpenCore 1.0.8 DEBUG. Dimensione e SHA-256 dell'archivio coincidono con quelli pubblicati nella release. Il programma è stato eseguito nuovamente su entrambi i config disponibili:

| Config verificato | Risultato ocvalidate 1.0.8 |
|---|---|
| File allegato, IntelBTPatcher escluso e VESA assente | No issues found, codice di uscita 0 |
| File preparato per la coppia Whiskey Lake | No issues found, codice di uscita 0 |
| Traccia diretta Intel, avvio normale | No issues found, codice di uscita 0 |
| Traccia diretta Intel, Recovery VESA senza dump automatici | No issues found, codice di uscita 0 |

La validazione certifica la struttura e le regole controllate dal programma, non il funzionamento dell'accelerazione sul dispositivo.

## OpenCore e driver

BOOTx64.efi, OpenCore.efi, HfsPlus.efi e OpenRuntime.efi hanno header PE validi, architettura x64 e formato PE32+. I ruoli PE sono coerenti: applicazioni EFI per i primi due, boot-service driver per HfsPlus e runtime driver per OpenRuntime. Non è stata individuata una mescolanza di release nella consegna.

Il config abilita soltanto OpenRuntime e HfsPlus. Usa il picker integrato, senza voci Misc.Tools. Non servono OpenCanopy, Resources o strumenti aggiuntivi per questo picker. La fine dei log a EXITBS:START descrive il passaggio fuori dai servizi firmware: non contiene il funzionamento successivo di macOS.

## Kext e dipendenze

Le 20 voci Kernel.Add hanno identificativi unici e percorsi PlistPath/ExecutablePath validi. Tutti i 19 eseguibili includono x86_64; UTBMap è correttamente privo di eseguibile. Le dipendenze esterne non Apple sono presenti, precedono i rispettivi client e hanno versioni compatibili con le richieste dei plist.

| Componente | Versione della consegna | Stato previsto con Darwin 25.6 |
|---|---|---|
| Lilu | 1.7.2 | Attivo |
| VirtualSMC | 1.3.8 | Attivo |
| SMCProcessor | 1.3.8 | Attivo |
| SMCBatteryManager | 1.3.8 | Attivo |
| WhateverGreen | 1.7.1 | Attivo |
| RestrictEvents | 1.1.6 | Attivo |
| AppleALC | 1.9.8 | Escluso da MaxKernel 24.99.99 |
| USBToolBox | 1.2.0 | Attivo |
| UTBMap | 1.1 | Attivo, solo plist |
| VoodooInput, plug-in I2C | 1.1.6 | Attivo |
| VoodooI2CServices | 1 | Attivo |
| VoodooGPIO | 1.1 | Attivo |
| VoodooI2C | 2.9.1 | Attivo |
| VoodooI2CHID | 1 | Attivo |
| VoodooPS2Controller | 2.3.7 | Attivo |
| VoodooPS2Keyboard | 2.3.7 | Attivo |
| IntelBluetoothFirmware | 2.4.0 | Attivo |
| IntelBTPatcher | 2.4.0 | Disabilitato dopo il panic |
| BlueToolFixup | 2.7.2 | Attivo |
| itlwm | 2.3.0 | Attivo |

Con i limiti del config e il patcher Bluetooth escluso risultano 18 voci applicabili a Darwin 25.6. Questo conteggio non certifica che ogni dispositivo funzioni. I numeri di versione 1 dei componenti I2C appartengono ai file ufficiali del pacchetto e non indicano una mescolanza di versioni. I changelog di Lilu e WhateverGreen dichiarano il supporto macOS 26 nelle versioni incluse: non viene aggiunto un altro flag beta per questi due.

## ACPI e configurazione

Sono presenti cinque SSDT attive e SSDT-DGPU-OFF disabilitata. Tutte e sei hanno firma SSDT, lunghezza dichiarata corretta e checksum valido. Le voci Add e la sostituzione di quattro byte _OSI con XOSI coincidono con il riferimento. La verifica di struttura non sostituisce la prova degli effetti ACPI sull'hardware.

Il config allegato differisce dal riferimento soltanto per IntelBTPatcher disabilitato. Booter, UEFI, ACPI, mappa USB, limiti dei kext e identità della macchina sono conservati. La prova Whiskey Lake cambia solo AAPL,ig-platform-id e device-id; gli altri controlli restano uguali. La mappa USB ha nove porte e XhciPortLimit è disattivato. Il Samsung avviato è USB; il PM981a interno resta installato per Windows.

AppleALC non viene applicato a Tahoe dal limite di versione. Il Bluetooth con il patcher escluso e lo spegnimento elettrico NVIDIA restano da verificare. Questi sono limiti funzionali noti, non nuovi difetti di struttura. Non sono state introdotte modifiche a Booter, firmware, firme o IOVersatile in base alla sola ultima riga visibile.

## Controllo semantico delle patch

È stata completata la [verifica contro DSDT e SSDT OEM](VERIFICA-PATCH-ACPI.md). CPU, EC, RTC, XOSI, PNLF, percorso GPU e metodi _DSM risultano coerenti con le patch custom. Non è stato individuato un errore statico che giustifichi una nuova patch ACPI o memoria framebuffer. La risoluzione congiunta iasl ha un limite su un possibile overlap OEM condizionale; non viene trattato come errore introdotto dalla EFI.

## Cosa manca per spiegare lo stallo

Il log OpenCore 173430 mostra la stessa sequenza del precedente 170413, senza nuovi errori e con i boot-args normali. Dopo il tentativo viene riferito testo fermo con IOVersatile e un secondo messaggio non trascritto completamente. Nel precedente archivio unificato, agli errori IOVersatile seguivano eventi di WindowServer in esecuzione e Language Chooser attivo; entrambi quegli avvii usavano VESA. Non è una prova della causa del nuovo stallo.

La nuova coppia Intel non ha prodotto un'interfaccia visibile nella prova riferita. Nell'ultima raccolta i dodici tracev3 nuovi sono vuoti e i cinque non vuoti coincidono con quelli già analizzati. Le nuove registrazioni timesync confermano altri avvii, ma non aggiungono i messaggi del driver. La [traccia diretta Intel](TRACCIA-INTEL.md) evita di ripetere la stessa raccolta e usa DEBUG delle versioni già presenti, con backup e ripristino dei soli file coinvolti. La coerenza statica della EFI non certifica l'accelerazione.

## Riordino del disco di avvio

La EFI consegnata è già compatta. La pulizia riguarda i log OpenCore e i vecchi pacchetti e strumenti di prova presenti nella radice dell'HDD. La procedura di [riordino](RIORDINO-AVVIO.md) li archivia sul Desktop di Windows conservandone una copia verificata, prima di rimuoverli dall'HDD. Conserva la EFI attuale, i file Recovery e il collector unificato. Non cambia il profilo Intel o i kext.

I file non riconosciuti restano sul disco e vengono elencati nel rapporto. Il riordino non viene presentato come soluzione dello stallo grafico. Il backup sul Desktop conserva i file e le istruzioni per rimetterli nelle loro posizioni.

## Riferimenti

- [OpenCore 1.0.8: release ufficiale](https://github.com/acidanthera/OpenCorePkg/releases/tag/1.0.8).
- [ocvalidate: controlli e limiti](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Utilities/ocvalidate/README.md).
- [Lilu 1.7.2: changelog](https://github.com/acidanthera/Lilu/blob/1.7.2/Changelog.md).
- [WhateverGreen 1.7.1: changelog](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Changelog.md).
- [Analisi della raccolta unificata ricevuta](ANALISI-LOG-UNIFICATI.md).

