# Analisi delle ACPI — BIOS BWCN19WW

Sono state verificate 20 tabelle originali: una DSDT, 12 SSDT e APIC, DMAR, ECDT, FACP, HPET, LPIT, MCFG. Le 12 SSDT hanno hash distinti e corrispondono al numero enumerato da Windows. I dump originali rimangono materiale di analisi locale e non sono inclusi nella repo.

La dicitura PARZIALE nel rapporto originale contiene una sola nota con codice di uscita non rilevato dello strumento. La successiva verifica dei file conferma lunghezze, checksum e hash corretti per tutte le tabelle. Non è necessario ripetere il dump.

## Patch preparate

| File | Funzione | Evidenza nel firmware | Stato |
|---|---|---|---|
| SSDT-PLUG | Proprietà plugin-type per la gestione CPU | Processor PR00 sotto `_SB` | Compilata; da provare |
| SSDT-EC-USBX | EC di compatibilità e proprietà USB di alimentazione | EC reale `_SB.PCI0.LPCB.H_EC` | Compilata; EC reale conservato |
| SSDT-PNLF | Dispositivo backlight per Intel | iGPU `_SB.PCI0.GFX0` | Compilata; luminosità da provare |
| SSDT-RTC-ENABLE | Rende disponibile il RTC standard in Darwin | RTC._STA dipende dal campo STAS; AWAC._STA restituisce Zero | Compilata; agisce sul flag firmware, non sui registri CMOS |
| SSDT-XOSI | Percorso di inizializzazione Windows 2015 per I2C | TPD0._INI e _CRS dipendono da OSYS | Compilata; richiede rename OEM `_OSI → XOSI` |
| SSDT-DGPU-OFF | Chiama lo spegnimento nativo della GTX | `_SB.PCI0.RP05.PXSX._OFF` nella SSDT9 | Compilata; facoltativa dopo il primo avvio |

I guard `_OSI("Darwin")` limitano gli interventi specifici a macOS. La wrapper XOSI passa le richieste al metodo originale quando viene avviato un altro sistema.

Il metodo nativo di spegnimento NVIDIA contiene attese hardware senza timeout. Per il primo avvio il profilo usa `-wegnoegpu` e mantiene la patch di spegnimento facoltativa: il boot argument evita il driver dGPU ma non garantisce che la scheda sia priva di alimentazione. La prova della sequenza di spegnimento segue un primo avvio riuscito.

## Due possibili collegamenti del 960 EVO

- **960 EVO in box USB:** il PM981a rimane sul percorso RP09. La configurazione di macOS deve escluderlo; occorre confermare il collegamento prima di preparare quel profilo.
- **960 EVO al posto del PM981a:** lo stesso percorso RP09 ospiterà il disco da usare. Escluderlo nasconderebbe il disco di destinazione, quindi questa esclusione non deve essere applicata.

Il formato M.2 NVMe non è una prova di compatibilità. Il modello dichiarato è il 960 EVO; firmware, integrità del disco e funzionamento con Tahoe restano verifiche sul dispositivo.

## Audio e touchpad

Il codec è Realtek ALC257. Su Tahoe manca AppleHDA: il solo AppleALC non ripristina automaticamente altoparlanti e jack. La soluzione analogica viene scelta dopo il primo avvio. Non sono state applicate modifiche al volume di sistema o alle protezioni di macOS.

Il touchpad è ELAN0662, I2C HID, sul bus I2C0. Il firmware imposta HID, indirizzo I2C e risorse in base ai propri parametri. La wrapper XOSI mantiene la scelta del percorso di inizializzazione moderno senza inventare numeri di pin GPIO. Sono previsti VoodooI2C e VoodooI2CHID; il funzionamento reale richiede una prova.

## Compilazione

I sorgenti sono in `acpi/source`. Il comando `python tools/build_acpi.py --iasl /percorso/iasl` produce AML, log e manifest in `build/acpi`. Ogni AML deve avere firma SSDT, lunghezza corrispondente e checksum nullo modulo 256. Il manifest collega anche lo SHA-256 del sorgente al risultato.

Le copie in `acpi/compiled` sono state prodotte con iASL 20240927. Il controllo automatico ricompila i sorgenti con il compilatore dell'ambiente CI e controlla nuovamente i risultati.

Non viene ricaricata in OpenCore la DSDT originale. Questi file sono patch supplementari; la configurazione completa, i driver, i kext e la mappa USB devono ancora essere assemblati e verificati prima di creare l'installer.

## Configurazione iniziale del disco USB-C

Il collegamento esterno del 960 EVO è confermato. La prima EFI blocca l'avvio del driver `com.apple.iokit.IONVMeFamily` con strategia `Disable`, mantenendo le informazioni sulle dipendenze. Il PM981a è l'unico NVMe nativo rilevato; il disco esterno usa lo stack USB. Il blocco vale per tutti gli NVMe nativi e va rimosso prima di montare il 960 EVO internamente. Percorsi ACPI e PCI del PM981a restano documentati per un'eventuale revisione. Il risultato è da verificare nel primo avvio.
