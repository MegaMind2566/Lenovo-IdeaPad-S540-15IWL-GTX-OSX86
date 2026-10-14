# Verifica della grafica Intel dopo l'installazione

## Esito sul dispositivo: 13 ottobre 2026

Con la [correzione della memoria framebuffer](../archive/primo-avvio/docs/TEST-MEMORIA-INTEL.md), Tahoe ha raggiunto la configurazione iniziale e il desktop sul Samsung 960 EVO esterno. Il successivo campione powermetrics rileva IntelAccelerator e boot-args senza `-igfxvesa` né `-x`. Il report system_profiler conferma:

| Voce | Risultato |
|---|---|
| GPU esposta | Intel UHD Graphics 620 |
| Device ID esposto | `0x3ea5`, coerente con la configurazione Whiskey Lake |
| Memoria grafica | Dinamica e condivisa, massimo 1536 MB |
| Supporto Metal | Metal 3 |
| Pannello interno | Online, principale, 1920×1080 |
| Profondità framebuffer | ARGB8888 a 24 bit |

Questi dati confermano il desktop con il driver acceleratore Intel caricato e Metal esposto. Non completano le prove di stabilità, carico Metal, decodifica video, luminosità, sospensione o uscite esterne. L'identificativo PCI fisico rilevato da Windows resta `8086:3EA0`; `0x3ea5` è quello esposto dalla configurazione macOS.

La configurazione applicata conserva `AAPL,ig-platform-id=0900A53E` e `device-id=A53E0000`, con `framebuffer-patch-enable=01000000`, `framebuffer-stolenmem=00003001` e `framebuffer-fbmem=00009000`. Le tre proprietà sono Data di quattro byte. Non sono state aggiunte altre patch dopo la comparsa del desktop.

Prima della configurazione iniziale il pannello è rimasto temporaneamente nero, poi l'interfaccia è comparsa senza una nuova modifica della EFI. Quella prima attesa, da sola, non giustificava una patch della retroilluminazione.

Successivamente è stato riferito che il pannello rimane spento per circa due minuti anche all'avvio, prima della mela, mentre macOS accetta già la password e completa il login. Il controllo del codice WEG e del dump del driver Tahoe ha individuato una [prova del solo BLR](AVVIO-RETE.md), limitata allo stesso UUID framebuffer e con backup reversibile. Dopo il riavvio della prova con `-igfxblr`, il 13 ottobre 2026 è stato riferito **schermo nero risolto, attesa zero**. Si mantiene la correzione funzionante. Memoria 19 MB/9 MB e identità Intel non sono modificate; altre patch della retroilluminazione non sono aggiunte.

## Conservare la EFI funzionante

Prima delle prove successive, creare una copia privata dell'intera cartella EFI corrente sull'HDD OpenCore, inclusi i backup della correzione memoria. Con il volume di avvio montato come `240 GB`, da Terminale:

```sh
ditto -c -k --keepParent "/Volumes/240 GB/EFI" "$HOME/Desktop/EFI-Tahoe-Metal3-$(date +%Y%m%d-%H%M%S).zip"
```

Il comando crea un archivio sul Desktop; va eseguito sul portatile. Se il volume non è montato con quel nome, individuare prima la cartella EFI in Finder. L'archivio contiene configurazione personale e profilo Wi-Fi: conservarlo privatamente, senza aggiungerlo alla repository. La EFI resta sull'HDD finché l'avvio dal Samsung non sarà preparato e verificato separatamente.

## Prove ancora da completare

1. Riavvio e spegnimento ripetibili con questa stessa EFI, annotando eventuali attese del pannello.
2. Uso del desktop e un carico che utilizzi Metal, senza blocchi o artefatti.
3. Ripresa del pannello dopo la sospensione. La regolazione dal cursore macOS è già riferita funzionante. F11/F12 non funzionano e sono rinviati al blocco completo dei tasti funzione nella [roadmap](ROADMAP.md#tasti-funzione-lavoro-rinviato-in-blocco).
4. Decodifica video e monitor esterni, come prove distinte.

Il primo campione powermetrics di circa un secondo riportava 50 °C per la CPU. Due campioni successivi a riposo, ciascuno di cinque secondi, riportano 45–46 °C, 0,80–0,95 W stimati per il pacchetto Intel e frequenza media sistema circa 0,95–0,97 GHz. IORegistry conferma X86PlatformPlugin attivo. Il consumo del pacchetto comprende CPU, iGPU e system agent, senza la NVIDIA. Gli RPM non sono disponibili, ma successivamente è stata riferita una ventola silenziosa da tempo. Temperatura sotto carico e consumo della dGPU restano da verificare. La voce `2Slices on: 100%` indica la permanenza nello stato con due slice attive; il 100% a 300 MHz è un rapporto di frequenza. Nessuna delle due voci dimostra un utilizzo GPU del 100%.

Le altre funzioni restano nella [roadmap hardware](ROADMAP.md). Per una nuova verifica dello stato, questi comandi leggono informazioni senza modificare la EFI:

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

## Riferimenti

- [WhateverGreen 1.7.1: opzioni Intel, incluso -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics)
- [Apple: Resoconto di sistema su Tahoe](https://support.apple.com/guide/system-information/welcome/11.0/mac/26)
- [Apple: creazione di un archivio ZIP con ditto](https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution)
- [Manuale Apple di powermetrics](https://keith.github.io/xcode-man-pages/powermetrics.1.html): potenza stimata, frequenze e sensori istantanei.
- [Dortania: grafica Intel sui portatili Coffee Lake / Whiskey Lake](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties)
