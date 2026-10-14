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

Lo stesso errore IOVersatile era già presente nell'archivio precedente, con VESA attivo. Dopo quegli errori WindowServer risultava in esecuzione e Language Chooser proseguiva. In quel campione DockChannelSerial registrava anche l'avvio riuscito. L'ultima riga della fotografia non identifica quindi da sola il punto che impedisce l'interfaccia. L'errore non è una nuova prova di corruzione o di fallimento Intel.

Per il prossimo confronto servono il log OpenCore appena creato da questo tentativo e il config.plist modificato. Prima di interpretare una nuova raccolta occorre confermare l'assenza runtime di VESA. Non viene applicato un blocco IOVersatile o un nuovo parametro grafico in base alla sola fotografia.

## Avvio senza VESA confermato: 170135 e 170413

Entrambi i nuovi log OpenCore del 13 ottobre 2026 selezionano Machintosh SSD sul Samsung USB e mostrano `MBA:NV` e `MBA:OUT` senza `-igfxvesa`, `-x` o `-bsdmgroot`. Lilu 1.7.2 e WhateverGreen 1.7.1 sono iniettati con successo; IntelBTPatcher non compare nelle iniezioni. Le proprietà AAPL,ig-platform-id e device-id sono impostate con esito Success, ma i valori non sono stampati.

I file terminano a EXITBS:START alle 17:01:41 e 17:04:18 secondo l'orologio del booter. Non contengono gli eventi successivi di macOS: questa fine del log non localizza lo stallo. La rimozione manuale è effettiva per entrambi i tentativi. I messaggi NVRAM sul valore già presente sono coerenti con boot-args identici a quelli desiderati.

Il precedente ZIP unificato conteneva avvii con VESA e non documenta il funzionamento Intel di questi tentativi. Il config.plist è stato successivamente ricevuto e controllato, come descritto sotto. Restano necessari gli eventi persistiti di un avvio normale per verificare l'acceleratore. Non viene ripetuta la rimozione del parametro già assente.

## Configurazione ricevuta e prova Whiskey Lake

Il file si apre correttamente come plist. Il confronto con la configurazione di riferimento mostra solo IntelBTPatcher disabilitato; gli altri valori sono conservati. Le proprietà Intel sono entrambe Data di quattro byte: AAPL,ig-platform-id `00009B3E` e device-id `9B3E0000`, sul percorso PciRoot(0x0)/Pci(0x2,0x0). La struttura e i tipi statici sono stati confrontati con Sample.plist ufficiale OpenCore 1.0.8; ocvalidate non è stato eseguito.

Il profilo attuale è mobile e non è privo di connettori. La guida Dortania Coffee/Whiskey Lake lo propone per UHD 620. Il manuale di WhateverGreen 1.7.1 indica invece per UHD 620 Whiskey Lake il fake device-id `A53E0000` e il framebuffer portatile predefinito 0x3EA50009, che si scrive come Data `0900A53E`.

Dopo i due tentativi normali è stata preparata una prova di questa coppia specifica, cambiando soltanto quei due valori. Il pacchetto privato contiene il config di prova e un backup identico, byte per byte, a quello ricevuto. Parsing del plist, confronto delle sole due modifiche e CRC dello ZIP sono verificati; il risultato sul portatile non è ancora disponibile. Il config completo e il backup non vengono pubblicati nel repository.

La [procedura](TEST-WHISKEY-LAKE.md) conserva boot-args, stato Bluetooth e identità della macchina. Entrambi i framebuffer dichiarano 58 MB di memoria stolen: questo test non risolve né accerta un eventuale limite DVMT. Non vengono aggiunte patch di memoria o connettori in assenza di una diagnosi. Se il risultato non cambia, la raccolta successiva deve includere gli eventi del test normale e di questa prova, da distinguere per avvio.



## Verifica completa richiesta dopo la prova

Dopo il tentativo 173430 è stato riferito testo fermo con IOVersatile e un secondo messaggio non trascritto completamente. È stata richiesta la verifica della EFI già consegnata, tenendo conto delle poche modifiche note, prima di scegliere ulteriori cambiamenti. La [verifica completa](../../../docs/reference/VERIFICA-EFI.md) ha confermato file, architetture, dipendenze e ACPI; ocvalidate 1.0.8 è stato eseguito sui due config disponibili con risultato No issues found. Nessuna nuova modifica grafica deriva da questi controlli. Per riordinare i vecchi log e le prove sul disco è disponibile la [procedura con archivio verificato](../../../docs/guides/RIORDINO-AVVIO.md).

## Riferimenti

- [Mandiant: release ufficiale 0.7.0](https://github.com/mandiant/macos-UnifiedLogs/releases/tag/v0.7.0).
- [Mandiant: struttura della raccolta manuale](https://github.com/mandiant/macos-UnifiedLogs/blob/v0.7.0/RUNNING.md).
- [WhateverGreen 1.7.1: significato di -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md).
- [WhateverGreen 1.7.1: gestione di disableAccel e wrapAcceleratorStart](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_igfx.cpp).
