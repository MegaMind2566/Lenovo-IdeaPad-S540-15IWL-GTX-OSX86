# Roadmap hardware

Obiettivo: rendere utilizzabili tutti i componenti del Lenovo IdeaPad S540-15IWL GTX su macOS Tahoe. Ogni componente richiede una prova sul dispositivo. La ricerca NVIDIA resta aperta e prevista dopo la stabilizzazione della grafica Intel.

## Ordine delle prove

1. Completare l'installazione sul 960 EVO esterno e raggiungere il desktop.
2. Verificare e completare l'accelerazione della UHD 620 seguendo [GRAFICA-INTEL.md](GRAFICA-INTEL.md).
3. Verificare periferiche, rete, USB e audio nel sistema installato.
4. Completare luminosità, gestione energetica, sospensione e riavvii.
5. Trasferire la EFI corrente sul 960 EVO e provare l'avvio senza l'HDD, conservando il supporto già funzionante come ripiego.
6. Avviare la ricerca NVIDIA e verificare le uscite video secondo il percorso hardware rilevato.

## Stato e criteri

| Componente | Stato attuale | Prova necessaria |
|---|---|---|
| Avvio Tahoe | Installazione in corso su «Macintosh SSD» | Desktop, spegnimento e riavvio ripetibili |
| Intel UHD 620 | Configurazione iniziale presente; boot-args da raccogliere | Metal funzionante, risoluzione nativa, assenza di artefatti |
| Tastiera | Funziona nella Recovery | Uso nel sistema installato e tasti funzione |
| Touchpad ELAN | Driver presenti; il «mouse» riferito non identifica il dispositivo | Puntamento, clic, scorrimento e gesti |
| Wi-Fi Intel AC9560 | Funziona nella Recovery con itlwm | Connessione, trasferimenti e riconnessione dopo sospensione |
| Bluetooth Intel | Panic USB/Bluetooth con IntelBTPatcher 2.4; [prova di esclusione](TEST-BLUETOOTH.md) pronta; sorgente aggiornato da verificare | Avvio senza panic, confronto con patcher aggiornato, associazione e uso di una periferica, riconnessione dopo sospensione |
| Audio ALC257 | Audio analogico su Tahoe da completare | Altoparlanti, cuffie, microfono e commutazione delle uscite |
| USB-A e USB-C | Mappa a 9 porte verificata; 960 EVO rilevato | USB 2/3, entrambe le orientazioni USB-C e riconnessione |
| Samsung 960 EVO esterno | Box ripristinato; installazione in corso | Uso prolungato senza disconnessioni e ripresa dalla sospensione |
| NVMe PM981a interno | Visibile nella Recovery; mantenuto per Windows | Verificare eventuali effetti sulla stabilità di macOS |
| Display e luminosità | Interfaccia Recovery visibile | Risoluzione, regolazione luminosità e ripresa del pannello |
| CPU, batteria e ventole | Driver e ACPI iniziali presenti | Letture coerenti, gestione frequenze, temperature e autonomia |
| Sospensione | Non provata | Chiusura coperchio, risveglio e recupero delle periferiche |
| Webcam | Porta interna mappata; non provata | Acquisizione video e ripresa dopo sospensione |
| Lettore SD O2Micro | Identificato; supporto da valutare | Driver applicabile e lettura di una scheda |
| Lettore impronte | Porta USB interna mappata; supporto da valutare | Valutare driver e integrazione con macOS |
| HDMI e video USB-C | Funzionamento e percorso non verificati | Individuare la GPU collegata a ciascuna uscita e provare monitor esterno |
| NVIDIA GTX 1650 Max-Q | Port Linux mantenuto come ricerca; nessun driver utilizzabile nella EFI | Milestone di inizializzazione, esecuzione GPU e integrazione grafica |

Le prove della Recovery non vengono estese automaticamente al sistema installato. Le voci ancora da completare rimangono aperte fino a un esito documentato.

## Ricerca NVIDIA

La GTX 1650, PCI `10DE:1F91`, è elencata tra le GPU compatibili con i moduli kernel open source NVIDIA. Il repository contiene parti indipendenti dal sistema operativo e interfacce specifiche per Linux. I moduli richiedono anche firmware GSP e componenti del driver in spazio utente della stessa versione.

Mesa/NVK offre un driver Vulkan aperto per NVIDIA, ma la sua implementazione attuale richiede Linux. Entrambe le basi vanno valutate: nessuna delle due è già un driver macOS per la GTX 1650.

Il percorso proposto è una valutazione tecnica, non un port già validato:

1. Studiare dipendenze da Linux, firmware e parti riutilizzabili su Darwin/IOKit.
2. Preparare un prototipo per il dispositivo PCI, la memoria e gli interrupt su macOS Intel.
3. Provare l'inizializzazione della GPU e l'esecuzione di un comando minimo, con risultati osservabili sul portatile.
4. Valutare la parte in spazio utente e il percorso verso Vulkan o altre funzioni sperimentali.
5. Affrontare separatamente integrazione con Metal, sistema grafico di macOS, gestione energetica e uscite video.

Il successo di un prototipo kernel non dimostra l'accelerazione del desktop. La GPU ibrida del portatile aggiunge la necessità di verificare collegamenti del pannello e delle uscite. Le prove sperimentali useranno una EFI separata da quella stabilizzata con Intel.

Nella EFI di uso iniziale resta `-wegnoegpu`. Lo spegnimento elettrico della NVIDIA e il port del suo driver sono attività distinte. La SSDT opzionale che richiama `_OFF` rimane disabilitata finché non viene verificato il comportamento del metodo firmware.

## Riferimenti

- [NVIDIA: open GPU kernel modules e GPU compatibili](https://github.com/NVIDIA/open-gpu-kernel-modules)
- [Mesa: NVK, supporto hardware e requisiti Linux](https://docs.mesa3d.org/drivers/nvk.html)
- [Acidanthera: WhateverGreen](https://github.com/acidanthera/WhateverGreen)
- [Dortania: note per Tahoe](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html)
