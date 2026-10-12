# Hardware verificato dal report lenovo.HTM

Report ricevuto il 12 ottobre 2026. Sono riportati solo i dati utili al progetto.

| Voce | Dato rilevato | Stato per macOS |
|---|---|---|
| Modello | Lenovo IdeaPad S540-15IWL GTX, famiglia 81SW | Configurazione da costruire sul dispositivo |
| Scheda madre | Lenovo LNVNB161216 | DSDT e 12 SSDT analizzate |
| BIOS | BWCN19WW, 26 maggio 2021 | UEFI presente; Secure Boot disabilitato nel report |
| CPU | Intel Core i7-8565U, Whiskey Lake-U, 4 core / 8 thread | Base adatta al tentativo |
| RAM | 12 GB DDR4-2400, moduli da 8 e 4 GB | Sufficiente per la prima prova |
| iGPU | Intel UHD 620, PCI 8086:3EA0 | Accelerazione da configurare e verificare |
| dGPU | NVIDIA GTX 1650 Max-Q 4 GB, PCI 10DE:1F91 | Nessun driver macOS; spegnimento da adattare alle ACPI |
| Schermo | BOE NV156FHM-N61, 1920×1080 | Luminosità e collegamento da verificare |
| NVMe | Samsung MZVLB512HBJQ-000L2, 512 GB, firmware 3L1QEXF7 | Famiglia PM981a problematica; non assunta compatibile |
| Wi-Fi | Intel Wireless-AC 9560, PCI 8086:9DF0 | Supportata da OpenIntelWireless; versione driver da scegliere |
| Bluetooth | Intel, USB 8087:0AAA | Firmware e funzionamento su Tahoe da verificare |
| Audio | Intel cAVS 8086:9DC8; Realtek ALC257, 10EC:0257 | Codec confermato dal dump Windows; audio analogico Tahoe da ripristinare e verificare |
| Tastiera | PS/2 | Driver da configurare |
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
- Samsung 960 EVO per la prova di macOS: collegamento esterno USB-C confermato; capacità da rilevare prima di inizializzarlo.

## Dati ancora necessari

- Velocità SuperSpeed e reversibilità della USB-C: mappa a 9 porte ricevuta e verificata.
- Capacità e contenuti del Samsung 960 EVO prima dell'installazione.
- Chiavetta USB vuota per l'installer.

Non sono ancora stati verificati avvio, Metal, audio, autonomia, sospensione o HDMI sul dispositivo. Nessun voto di compatibilità totale è assegnato prima delle prove.
