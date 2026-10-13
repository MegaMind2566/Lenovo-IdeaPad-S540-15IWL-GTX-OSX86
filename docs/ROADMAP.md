# Roadmap hardware

Obiettivo: rendere utilizzabili tutti i componenti del Lenovo IdeaPad S540-15IWL GTX su macOS Tahoe. Ogni componente richiede una prova sul dispositivo. La ricerca NVIDIA resta aperta e prevista dopo la stabilizzazione della grafica Intel.

## Ordine delle prove

1. Conservare una copia privata della EFI corrente: il desktop di Tahoe sul 960 EVO esterno è stato raggiunto.
2. Completare le prove di stabilità della UHD 620 seguendo [GRAFICA-INTEL.md](GRAFICA-INTEL.md); IntelAccelerator e Metal 3 esposto sono già confermati.
3. Verificare periferiche, rete, USB e audio nel sistema installato.
4. Completare luminosità, gestione energetica, sospensione e riavvii.
5. Trasferire la EFI corrente sul 960 EVO e provare l'avvio senza l'HDD, conservando il supporto già funzionante come ripiego.
6. Avviare la ricerca NVIDIA e verificare le uscite video secondo il percorso hardware rilevato.

Priorità aggiornate il 13 ottobre 2026: il pannello spento all'avvio è **risolto nella prova con -igfxblr, attesa da circa due minuti a zero**. Si conserva la EFI corrente. Il 14 ottobre 2026 è stato confermato anche il funzionamento con cuffie Bluetooth e di HeliPort. La prova Photo Booth mostra immagine e registra la voce; il guadagno microfono è eccessivo e la regolazione nelle impostazioni è in corso. Velocità rete e riconnessione restano aperte. Il percorso è in [AVVIO-RETE.md](AVVIO-RETE.md). Batteria e contatori sono [archiviati](BATTERIA-SOSPENSIONE.md); le altre prove di sospensione sono rinviate, insieme al blocco tasti funzione e all'equalizzazione già annotati.

## Stato e criteri

| Componente | Stato attuale | Prova necessaria |
|---|---|---|
| Avvio Tahoe | Desktop sul 960 EVO; ritardo del pannello eliminato nella prova del solo -igfxblr, attesa riferita zero | Conservare la correzione e verificare spegnimento/riavvio ripetibili nell'uso |
| Intel UHD 620 | IntelAccelerator rilevato, Metal 3 esposto, memoria condivisa fino a 1536 MB; avvio senza VESA | Carico Metal e uso prolungato senza blocchi o artefatti |
| Tastiera | Funziona nella Recovery | Uso nel sistema installato e tasti funzione |
| Touchpad ELAN | Driver presenti; il «mouse» riferito non identifica il dispositivo | Puntamento, clic, scorrimento e gesti |
| Wi-Fi Intel AC9560 | itlwm 2.3.0 caricato, Ethernet su en0 previsto dal driver; HeliPort riferito funzionante | Velocità, cambio rete e riconnessione; integrazione Wi-Fi nativa Tahoe separata |
| Bluetooth Intel | Funzionamento con cuffie confermato; firmware caricato, NVRAM corretta, IntelBTPatcher 2.4 escluso | Microfono delle cuffie e riconnessione da provare; conservare i driver attuali |
| Audio ALC257 | Riproduzione, volume graduale e F1–F3 confermati; voce acquisita nella prova video, guadagno microfono eccessivo | Verificare nuova registrazione dopo regolazione ingresso; equalizzazione rinviata, jack e ripresa da documentare |
| USB-A e USB-C | Mappa a 9 porte verificata; 960 EVO rilevato | USB 2/3, entrambe le orientazioni USB-C e riconnessione |
| Samsung 960 EVO esterno | Box ripristinato; Tahoe avviato al desktop | Uso prolungato senza disconnessioni e ripresa dalla sospensione |
| NVMe PM981a interno | Visibile nella Recovery; mantenuto per Windows | Verificare eventuali effetti sulla stabilità di macOS |
| Display e luminosità | Pannello interno 1920×1080 e cursore luminosità funzionanti; F11/F12 non funzionano nella prova riferita | F11/F12 rinviati al blocco tasti funzione; ripresa del pannello da provare |
| CPU, batteria e ventole | X86PlatformPlugin attivo; riposo 45–46 °C e 0,80–0,95 W Intel stimati; ventola silenziosa. Batteria rilevata al 100% su AC. Telemetria SMC parziale | Temperature sotto carico, stato dGPU, passaggio a batteria e autonomia |
| Sospensione | pmset registra Sleep Count 1, User Wake Count 1 e Dark Wake Count 0; [dati conservati](BATTERIA-SOSPENSIONE.md) | Prove rinviate: recupero periferiche, coperchio e stop prolungato restano da verificare |
| Webcam | Immagine presente nella prova Photo Booth del 14 ottobre 2026 | Uso prolungato e ripresa da verificare |
| Lettore SD O2Micro | Identificato; supporto da valutare | Driver applicabile e lettura di una scheda |
| Lettore impronte | Porta USB interna mappata; supporto da valutare | Valutare driver e integrazione con macOS |
| HDMI e video USB-C | Funzionamento e percorso non verificati | Individuare la GPU collegata a ciascuna uscita e provare monitor esterno |
| NVIDIA GTX 1650 Max-Q | Port Linux mantenuto come ricerca; nessun driver utilizzabile nella EFI | Milestone di inizializzazione, esecuzione GPU e integrazione grafica |

Le prove della Recovery non vengono estese automaticamente al sistema installato. Le voci ancora da completare rimangono aperte fino a un esito documentato.

## Tasti funzione: lavoro rinviato in blocco

Verificare e sistemare insieme **tutti i tasti funzione**, includendo F11/F12 per la luminosità, comportamento Fn e le altre funzioni disponibili sulla tastiera. La richiesta del 13 ottobre 2026 rinvia questo lavoro: non si preparano ora modifiche per i soli tasti luminosità.

F1–F3 per muto e volume sono già riferiti funzionanti e vanno conservati. Il cursore luminosità macOS funziona. Fn+F11/F12 e l'eventuale gestione ACPI con BrightnessKeys saranno valutati nel blocco completo, prima di scegliere le modifiche necessarie.

## Attività audio rinviata

**Equalizzazione ALC257:** da rivedere più avanti. L'esito positivo del 13 ottobre 2026 conferma audio e volume dopo la correzione v3. Per ora si conserva la configurazione funzionante; l'affinamento timbrico sarà una prova separata, senza riaprire il problema del volume.

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
