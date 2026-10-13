# Hardware verificato dal report lenovo.HTM

Report ricevuto il 12 ottobre 2026. Sono riportati solo i dati utili al progetto.

| Voce | Dato rilevato | Stato per macOS |
|---|---|---|
| Modello | Lenovo IdeaPad S540-15IWL GTX, famiglia 81SW | Configurazione da costruire sul dispositivo |
| Scheda madre | Lenovo LNVNB161216 | DSDT e 12 SSDT analizzate |
| BIOS | BWCN19WW, 26 maggio 2021 | UEFI presente; Secure Boot disabilitato nel report |
| CPU | Intel Core i7-8565U, Whiskey Lake-U, 4 core / 8 thread | Base adatta al tentativo |
| RAM | 12 GB DDR4-2400, moduli da 8 e 4 GB | Sufficiente per la prima prova |
| iGPU | Intel UHD 620, PCI 8086:3EA0 | Configurazione iniziale presente; verifica Metal come prossimo passo |
| dGPU | NVIDIA GTX 1650 Max-Q 4 GB, PCI 10DE:1F91 | Driver disabilitato nella EFI; port Linux mantenuto nella roadmap; spegnimento elettrico da verificare |
| Schermo | BOE NV156FHM-N61, 1920×1080 | Luminosità e collegamento da verificare |
| NVMe | Samsung MZVLB512HBJQ-000L2, 512 GB, firmware 3L1QEXF7 | Famiglia PM981a problematica; non assunta compatibile |
| Wi-Fi | Intel Wireless-AC 9560, PCI 8086:9DF0 | Funzionamento riferito nella Recovery con itlwm; sistema installato da provare |
| Bluetooth | Intel, USB 8087:0AAA | Firmware e funzionamento su Tahoe da verificare |
| Audio | Intel cAVS 8086:9DC8; Realtek ALC257, 10EC:0257 | Codec confermato dal dump Windows; audio analogico Tahoe da ripristinare e verificare |
| Tastiera | PS/2 | Funzionamento riferito nella Recovery con VoodooPS2 |
| Touchpad | ELAN0662, I2C HID; controller Intel 8086:9DE8 | Percorso confermato: `_SB.PCI0.I2C0.TPD0`; funzionamento da provare |
| Lettore SD | O2Micro SD Host Controller | Supporto da verificare; diverso dal lettore del progetto lucatek |
| Webcam | TwinHan Integrated Camera USB | Da provare dopo la mappatura USB |

Il nome del driver Windows della grafica integrata riporta UHD 610, ma il chip e l'ID PCI del report identificano UHD 620. La configurazione sarà basata sul chip reale.

## Dati acquisiti dopo il report

- Una DSDT, 12 SSDT e 7 altre tabelle utili: tutte verificate per lunghezza, checksum e SHA-256.
- Audio Realtek ALC257 su Intel SST, `INTELAUDIO\\FUNC_01&VEN_10EC&DEV_0257`.
- Touchpad ELAN0662 sul percorso `_SB.PCI0.I2C0.TPD0`.
- dGPU: `_SB.PCI0.RP05.PXSX`; metodo nativo `_OFF` presente nella SSDT9.
- NVMe interno: PCI `PciRoot(0x0)/Pci(0x1D,0x0)/Pci(0x0,0x0)`, coerente con `_SB.PCI0.RP09.PXSX`.
- Samsung 960 EVO per la prova di macOS: collegamento esterno USB-C confermato; capacità non riportata nella documentazione ricevuta.

## Dati ancora necessari

- Velocità SuperSpeed e reversibilità della USB-C: mappa a 9 porte ricevuta e verificata.
- Boot-args di un avvio successivo ai ripristini e report della grafica dal sistema installato. Il log delle 02:45 conferma entrambi i parametri diagnostici in quel tentativo.
- Esiti delle prove dei componenti nella [roadmap](ROADMAP.md).

La Recovery ha raggiunto l'interfaccia grafica e l'installazione di Tahoe è stata avviata sul volume esterno «Macintosh SSD». Il primo desktop non è ancora confermato. Metal, audio, autonomia, sospensione e HDMI restano da verificare sul dispositivo. Nessun voto di compatibilità totale è assegnato prima delle prove.

## Esito della prima prova della Recovery

Il 13 ottobre 2026 è stato riferito il raggiungimento della selezione della lingua e il funzionamento di mouse, tastiera e Wi-Fi nella Recovery. Non è stato specificato se il mouse indicato sia il touchpad o un dispositivo USB: il touchpad ELAN resta da verificare separatamente.

L'esito è stato comunicato dopo la proposta del test `-igfxvesa`. I boot-args effettivi non sono stati raccolti, quindi non si attribuisce ancora il risultato con certezza a quel parametro. La comparsa della Recovery non dimostra l'accelerazione Metal, né la compatibilità completa del sistema installato. La [verifica Intel](GRAFICA-INTEL.md) parte da questi dati dopo l'installazione.

## Rilevamento del disco esterno e preferenza per l'interno

Il 960 EVO non compariva perché il modulo M.2 si era sganciato nel box. Dopo averlo reinserito è stato riferito il rilevamento del disco. Questo esito risolve il problema di rilevamento osservato; non conferma ancora la velocità SuperSpeed né entrambe le orientazioni della USB-C.

Il disco interno è stato riferito visibile nella Recovery: l'esclusione tramite blocco del driver NVMe non è risultata verificata in questa prova. È stato richiesto di lasciare il disco Windows al suo posto e procedere sul 960 EVO esterno. Nessuna inizializzazione o modifica delle partizioni del disco interno è stata eseguita. Le prove successive valuteranno eventuali problemi di stabilità.

## Log OpenCore delle 02:45

Il log del 13 ottobre 2026 conferma la selezione del volume USB esterno, con nome **Machintosh SSD**, e la presenza di `-igfxvesa` e `-x`. OpenCore riporta l'iniezione riuscita di Lilu 1.7.2 e WhateverGreen 1.7.1 e l'impostazione delle proprietà Intel. Il log non conferma l'inizializzazione dei driver nel kernel o Metal. Il primo desktop resta da raggiungere.

L'[analisi del log](ANALISI-LOG-AVVIO.md) riporta anche il percorso Apple con immagine BaseSystem, l'assenza della tabella MAT e i limiti del blocco NVMe. Il file originale e gli identificativi SMBIOS non vengono aggiunti alla repository.
