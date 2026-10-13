# Log unificati dopo la reinstallazione

La raccolta LOG-UNIFICATI-e8VM9n contiene diagnostics e uuidtext, cinque tracev3, un timesync e due DSC. I 496 file hanno CRC valido; sono circa 220,6 MB decompressi. Gli archivi originali, gli UUID e gli altri identificativi non vengono pubblicati.

I dati sono stati decodificati offline con il binario ufficiale Mandiant macos-UnifiedLogs 0.7.0, verificato contro il checksum e il digest della release. I contenuti delle due directory sono stati riuniti in una cartella di lavoro, conservando la copia originale. Sono stati ottenuti 106.966 eventi relativi a due avvii. Alcuni messaggi sono privati e il parser segnala riferimenti UUID non risolti: l'assenza di un evento non dimostra l'assenza del problema.

## Avvii presenti

Gli orari seguenti sono UTC, secondo i dati timesync; non sono gli orari locali della fotografia.

| Avvio | Intervallo degli eventi | Parametri effettivi |
|---|---|---|
| Primo | 13 ottobre 2026, 10:39:49–10:40:48 | `-igfxvesa` e `-bsdmgroot`; `-x` assente |
| Secondo | 13 ottobre 2026, 10:41:00–10:43:25 | `-igfxvesa`; `-x` e `-bsdmgroot` assenti |

Nel secondo avvio launchd e il kernel riportano gli stessi boot-args. Il flag VESA è quindi effettivamente applicato nel sistema, non soltanto presente in un vecchio config. Questo archivio non contiene un avvio senza VESA della nuova installazione.

## Interfaccia del secondo avvio

| Ora UTC | Processo | Risultato |
|---|---|---|
| 10:41:29.492 | WindowServer | Intel `8086:3e9b`, percorso IGPU, `IONDRVFramebuffer`, acceleratore nullo |
| 10:41:29.530–29.550 | WindowServer | `AppleIntelFramebuffer = 0` e `isAcc=NO` |
| 10:41:29.711 | WindowServer | `Software compositor activated.` |
| 10:41:32.959 | iconservicesagent | `No Metal renderer available.` |
| 10:41:35.293 | Language Chooser, com.apple.macbuddy | Imposta i dati dello sfondo del benvenuto |
| 10:41:35.294 | Language Chooser, com.apple.macbuddy | `Fail to create texture!` |

WindowServer e Language Chooser continuano a registrare eventi dopo l'errore. Nel campione non è stato individuato un loro arresto esplicito. Il puntatore visibile non dimostra che la texture del benvenuto venga disegnata.

Il sorgente di WhateverGreen 1.7.1 legge `-igfxvesa` e impedisce l'avvio di IntelAccelerator. L'assenza di accelerazione in questi avvii è coerente con quella scelta diagnostica. Il fallimento della texture è un errore concreto dell'interfaccia durante VESA; non prova da solo la causa dei precedenti tentativi senza VESA.

Lilu e WhateverGreen producono notifiche di caricamento, come AppleIntelCFLGraphicsFramebuffer. Una notifica di caricamento non dimostra che esista un acceleratore funzionante. Le proprietà iniettate fanno comparire il device-id Intel atteso, ma il framebuffer nativo e Metal restano da verificare. IntelBTPatcher non compare negli eventi, mentre firmware Intel e BlueToolFixup compaiono; la prossima prova deve conservare l'esclusione del patcher.

Non è stata identificata una diagnosi DVMT/stolen-memory che motivi nuove patch. Gli errori AMFI sul contesto e quelli DriverKit non vengono interpretati automaticamente come errori grafici.

## Prossimo passo

Da Windows eseguire **TEST-INTEL.cmd sull'HDD della EFI usata per questi avvii**. Rimuove soltanto `-igfxvesa` e l'eventuale `-x`, conservando la modifica Bluetooth e le altre impostazioni. Il programma e il ripristino sono già disponibili nel pacchetto Intel precedente; il codice di quel pacchetto coincide con il sorgente attuale.

Dopo l'esito "Prova Intel attivata", controllare che sia elencata la rimozione di `-igfxvesa`, quindi avviare lo stesso OpenCore e scegliere **Machintosh SSD**. Questa è la prova normale della nuova installazione. I log `103339` e `103615` senza VESA appartenevano alla precedente installazione e non vengono sostituiti o smentiti dalla nuova raccolta.

Se il programma segnala che i parametri sono già assenti o rifiuta il backup, conservare il messaggio: va verificata la EFI effettivamente usata prima di fare altri cambiamenti. Se lo schermo resta nero dopo una rimozione riuscita, serve il log OpenCore di quel tentativo e una nuova raccolta dei dati unificati. I log precedenti restano sul Data: il confronto va fatto per avvio e boot-args, non assumendo che tutto lo ZIP descriva l'ultima prova.

## Prova successiva dopo la modifica manuale

È stata riferita la rimozione manuale di `-igfxvesa` dal config.plist. La fotografia del nuovo tentativo mostra il caricamento delle collezioni di estensioni e gli errori ripetuti di dipendenze di com.apple.driver.IOVersatile, con codice `0xdc00800e`. DockChannelSerial riporta `has crashed 0 time(s)`. Non è visibile una riga di panic né sono mostrati i boot-args effettivi.

Lo stesso errore IOVersatile era già presente nell'archivio precedente, con VESA attivo, prima dell'avvio di WindowServer. In quel campione DockChannelSerial registrava anche l'avvio riuscito. L'ultima riga della fotografia non identifica quindi da sola il punto che impedisce l'interfaccia. L'errore non è una nuova prova di corruzione o di fallimento Intel.

Per il prossimo confronto servono il log OpenCore appena creato da questo tentativo e il config.plist modificato. Prima di interpretare una nuova raccolta occorre confermare l'assenza runtime di VESA. Non viene applicato un blocco IOVersatile o un nuovo parametro grafico in base alla sola fotografia.

## Riferimenti

- [Mandiant: release ufficiale 0.7.0](https://github.com/mandiant/macos-UnifiedLogs/releases/tag/v0.7.0).
- [Mandiant: struttura della raccolta manuale](https://github.com/mandiant/macos-UnifiedLogs/blob/v0.7.0/RUNNING.md).
- [WhateverGreen 1.7.1: significato di -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md).
- [WhateverGreen 1.7.1: gestione di disableAccel e wrapAcceleratorStart](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_igfx.cpp).
