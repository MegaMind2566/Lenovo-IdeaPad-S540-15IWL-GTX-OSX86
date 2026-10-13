# Verifica delle patch contro le tabelle originali

Verifica del 13 ottobre 2026 sul config ricevuto, sul config della prova Whiskey Lake e sulle 20 tabelle ACPI originali del Lenovo S540-15IWL. Il controllo della struttura della EFI è descritto in [VERIFICA-EFI](VERIFICA-EFI.md). Qui sono stati esaminati i percorsi e i metodi reali: non è stato trovato un errore statico che giustifichi una nuova patch DSDT.

Aggiornamento dopo la traccia diretta: il dump del driver e la foto identificano un errore specifico di memoria stolen insufficiente nel calcolo Apple. La [prova memoria](TEST-MEMORIA-INTEL.md) interviene sulle proprietà framebuffer del config; i riscontri ACPI riportati sotto restano validi.

## Patch e oggetti

| Patch o impostazione | Riscontro nel firmware | Esito |
|---|---|---|
| SSDT-PLUG | Il processore è `\_SB.PR00`; nel suo scope non compare un `_DSM` OEM concorrente | Percorso e tipo corretti |
| SSDT-EC-USBX | Il controller reale è `\_SB.PCI0.LPCB.H_EC`, indicato anche da ECDT; non esistono Device EC o USBX concorrenti | Il controller reale viene conservato |
| SSDT-RTC-ENABLE | RTC restituisce stato attivo quando STAS=1; AWAC restituisce Zero | La scelta RTC è coerente |
| `_OSI → XOSI` | Undici occorrenze OEM nel DSDT; le query Windows arrivano fino al 2015 | Il proxy copre le query reali, senza rinomina concorrente |
| SSDT-PNLF | GFX0 esiste a PCI device 2, function 0; nessun Device PNLF OEM omonimo | Percorso corretto, UID `0x13` = 19 decimale |
| SSDT-DGPU-OFF | Il metodo reale è `\_SB.PCI0.RP05.PXSX._OFF` | Percorso corretto, ma la SSDT resta disabilitata |

OpenCore 1.0.8 applica le patch alle tabelle OEM prima di aggiungere le SSDT custom. Le chiamate `_OSI("Darwin")` nei nuovi SSDT non vengono pertanto rinominate in XOSI. Il proxy non crea la ricorsione che si avrebbe modificando anche la propria chiamata a `_OSI`.

La PNLF usa il valore Coffee Lake previsto anche per questi identificativi Whiskey Lake. Il sample ufficiale seleziona UID 19 nel ramo CFL. L'assenza del lungo metodo di inizializzazione PWM del sample non dimostra una mancanza nel nostro profilo: quel ramo non esegue le riscalature previste per le altre generazioni.

## GPU e proprietà del config

Il DSDT espone GFX0 con `_ADR=0x00020000` sotto PCI0. Questo corrisponde a `PciRoot(0x0)/Pci(0x2,0x0)`, dove OpenCore inserisce le proprietà Intel. Le SSDT OEM aggiungono i metodi completi della GPU.

Il `_DSM` Intel gestisce il proprio GUID e i metadati del pannello: non restituisce proprietà Apple `AAPL,ig-platform-id`, `device-id` o framebuffer che sovrascrivano quelle del config. Il metodo `_INI` grafico esaminato aggiorna l'elenco dei display, senza un ciclo di attesa. La rinomina del dispositivo operata da WhateverGreen nel registro I/O non richiede una rinomina binaria GFX0 nel namespace AML.

| Proprietà Data di quattro byte | Config ricevuto | Prova Whiskey Lake già consegnata |
|---|---|---|
| AAPL,ig-platform-id | `00009B3E` | `0900A53E` |
| device-id | `9B3E0000` | `A53E0000` |

Il manuale WhateverGreen indica la coppia della prova per UHD 620 Whiskey Lake. Entrambi i framebuffer sono mobili e dichiarano 58 MB di memoria stolen. La differenza non basta a identificare la causa del blocco e la prova è già stata riferita senza un'interfaccia funzionante. L'ultimo archivio non include un nuovo config che permetta di certificare i valori effettivamente letti in quell'avvio.

GUMA, GIVD, GMFN, ASLB e BGMS sono campi PCI/OpRegion/GNVS valutati a runtime. Queste tabelle non misurano il DVMT assegnato dal BIOS. Non viene assunto un valore di 32 MB e non vengono aggiunte patch stolenmem, fbmem o connettori senza una misura o un errore del driver.

## Limiti della verifica ACPI

DSDT e dodici SSDT OEM sono stati disassemblati separatamente con iasl 20230628. La risoluzione congiunta degli esterni non è riuscita: SSDT9 definisce RP05._PR0, mentre SSDT11 lo definisce nel ramo RPIN=4. RPIN è un campo letto a runtime; il suo valore non è presente nel dump. Questo è un possibile overlap OEM condizionale, non una collisione introdotta dalle SSDT custom. Gli altri errori della disassemblazione congiunta non vengono usati per dedurre ulteriori collisioni non confermate nei sorgenti. Le tabelle originali non vengono eliminate o sostituite sulla base di questo risultato.

Nei log OpenCore MAT support è 0. Il codice 1.0.8 tollera l'assenza della MAT durante RebuildAppleMemoryMap; SyncRuntimePermissions conserva anche un intervento sulla mappa normale. Non c'è una regola che imponga automaticamente EnableWriteUnprotector=True in questo caso. Recovery e avvio VESA raggiungono l'interfaccia: senza un errore delle chiamate runtime non viene modificata la combinazione Booter per spiegare il blocco grafico.

## Passo diagnostico conseguente

Le patch esaminate restano invariate. Nell'ultimo archivio dodici nuovi tracev3 sono vuoti e i cinque non vuoti coincidono con quelli precedenti: ripetere la stessa raccolta non registrerebbe necessariamente l'errore Intel. La [traccia diretta Intel](TRACCIA-INTEL.md) usa Lilu e WhateverGreen DEBUG delle stesse versioni presenti e salva anche la configurazione esatta della prova. È uno strumento diagnostico, non una correzione dell'accelerazione già confermata.

## Riferimenti primari

- [OpenCore 1.0.8, ordine ACPI e quirks Booter](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex).
- [OpenCore 1.0.8, sample PNLF](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/AcpiSamples/Source/SSDT-PNLF.dsl).
- [OpenCore 1.0.8, gestione della mappa](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcAfterBootCompatLib/ServiceOverrides.c).
- [OpenCore 1.0.8, gestione degli attributi](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcMemoryLib/MemoryAttributes.c).
- [WhateverGreen 1.7.1, manuale Intel](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md).
- [WhateverGreen 1.7.1, rinomina GPU nel registro I/O](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_weg.cpp).
