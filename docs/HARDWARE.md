# Hardware verificato dal report lenovo.HTM

Report ricevuto il 12 ottobre 2026. Sono riportati solo i dati utili al progetto.

| Voce | Dato rilevato | Stato per macOS |
|---|---|---|
| Modello | Lenovo IdeaPad S540-15IWL GTX, famiglia 81SW | Configurazione da costruire sul dispositivo |
| Scheda madre | Lenovo LNVNB161216 | ACPI mancanti |
| BIOS | BWCN19WW, 26 maggio 2021 | UEFI presente; Secure Boot disabilitato nel report |
| CPU | Intel Core i7-8565U, Whiskey Lake-U, 4 core / 8 thread | Base adatta al tentativo |
| RAM | 12 GB DDR4-2400, moduli da 8 e 4 GB | Sufficiente per la prima prova |
| iGPU | Intel UHD 620, PCI 8086:3EA0 | Accelerazione da configurare e verificare |
| dGPU | NVIDIA GTX 1650 Max-Q 4 GB, PCI 10DE:1F91 | Nessun driver macOS; spegnimento da adattare alle ACPI |
| Schermo | BOE NV156FHM-N61, 1920×1080 | Luminosità e collegamento da verificare |
| NVMe | Samsung MZVLB512HBJQ-000L2, 512 GB, firmware 3L1QEXF7 | Famiglia PM981a problematica; non assunta compatibile |
| Wi-Fi | Intel Wireless-AC 9560, PCI 8086:9DF0 | Supportata da OpenIntelWireless; versione driver da scegliere |
| Bluetooth | Intel, USB 8087:0AAA | Firmware e funzionamento su Tahoe da verificare |
| Controller audio | Intel cAVS, PCI 8086:9DC8 | Codec analogico non identificato nel report |
| Tastiera | PS/2 | Driver da configurare |
| Touchpad | Dispositivo HID I2C; controller Intel 8086:9DE8 | Identificativo del touchpad da raccogliere |
| Lettore SD | O2Micro SD Host Controller | Supporto da verificare; diverso dal lettore del progetto lucatek |
| Webcam | TwinHan Integrated Camera USB | Da provare dopo la mappatura USB |

Il nome del driver Windows della grafica integrata riporta UHD 610, ma il chip e l'ID PCI del report identificano UHD 620. La configurazione sarà basata sul chip reale.

## Dati ancora necessari

- DSDT e tutte le SSDT disponibili, con verifica di integrità.
- ID del codec audio analogico e relativi dispositivi Intel SST/HD Audio.
- ID ACPI/HID del touchpad e modalità di collegamento.
- Percorsi ACPI effettivi di dGPU e NVMe, ricavati dai dump.
- Mappa USB del dispositivo: la sola lista dei controller Windows non la sostituisce.
- Disponibilità e modello dell'SSD su cui provare macOS.

Non sono ancora stati verificati avvio, Metal, audio, autonomia, sospensione o HDMI sul Lenovo di Andrea. Nessun voto di compatibilità totale è assegnato prima delle prove.
