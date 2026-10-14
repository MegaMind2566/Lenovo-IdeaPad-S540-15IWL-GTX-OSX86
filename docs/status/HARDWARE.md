# Hardware verificato dal report lenovo.HTM

Report ricevuto il 12 ottobre 2026. Sono riportati solo i dati utili al progetto.

| Voce | Dato rilevato | Stato per macOS |
|---|---|---|
| Modello | Lenovo IdeaPad S540-15IWL GTX, famiglia 81SW | Tahoe avviato al desktop sul 960 EVO esterno |
| Scheda madre | Lenovo LNVNB161216 | DSDT e 12 SSDT analizzate |
| BIOS | BWCN19WW, 26 maggio 2021 | UEFI presente; Secure Boot disabilitato nel report |
| CPU | Intel Core i7-8565U, Whiskey Lake-U, 4 core / 8 thread | X86PlatformPlugin attivo; due campioni a riposo con basso consumo Intel stimato e CPU 45–46 °C |
| RAM | 12 GB DDR4-2400, moduli da 8 e 4 GB | Sufficiente per la prima prova |
| iGPU | Intel UHD 620, PCI 8086:3EA0 | IntelAccelerator rilevato e Metal 3 esposto; carico prolungato da provare |
| dGPU | NVIDIA GTX 1650 Max-Q 4 GB, PCI 10DE:1F91 | Driver disabilitato nella EFI; port Linux mantenuto nella roadmap; spegnimento elettrico da verificare |
| Schermo | BOE NV156FHM-N61, 1920×1080 | Pannello e cursore funzionanti; ritardo nero all'avvio eliminato con -igfxblr nella prova; F11/F12 rinviati |
| NVMe | Samsung MZVLB512HBJQ-000L2, 512 GB, firmware 3L1QEXF7 | Famiglia PM981a problematica; non assunta compatibile |
| Wi-Fi | Intel Wireless-AC 9560, PCI 8086:9DF0 | itlwm 2.3.0 caricato e HeliPort riferito funzionante; Ethernet è previsto dal driver; velocità e riconnessione da provare |
| Bluetooth | Intel, USB 8087:0AAA | Funzionamento con cuffie confermato; firmware caricato, NVRAM corretta e IntelBTPatcher escluso; microfono delle cuffie e riconnessione da provare |
| Audio | Intel cAVS 8086:9DC8; Realtek ALC257, 10EC:0257 | Riproduzione, volume graduale e tasti F1–F3 confermati con VoodooHDA 3.6.8 e correzione v3; correzione microfono v2 con primo riscontro positivo dopo il riavvio; report e registrazioni di confronto da acquisire; equalizzazione rinviata, jack da documentare |
| Tastiera | PS/2 | Funzionamento riferito nella Recovery con VoodooPS2 |
| Touchpad | ELAN0662, I2C HID; controller Intel 8086:9DE8 | Percorso confermato: `_SB.PCI0.I2C0.TPD0`; funzionamento da provare |
| Lettore SD | O2Micro SD Host Controller | Supporto da verificare; diverso dal lettore del progetto lucatek |
| Webcam | TwinHan Integrated Camera USB | Immagine presente nella prova Photo Booth; uso prolungato e ripresa da verificare |

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
- Esiti delle prove dei componenti nella [roadmap](ROADMAP.md).

Tahoe ha raggiunto il desktop sul Samsung 960 EVO esterno dopo la correzione della memoria framebuffer. IntelAccelerator e Metal 3 esposto sono confermati; carico grafico prolungato, audio, autonomia, sospensione e HDMI restano da verificare. Nessun voto di compatibilità totale è assegnato prima delle prove.

## Desktop e grafica Intel: 13 ottobre 2026

Il report grafico del sistema installato espone UHD 620 con device-id `0x3ea5`, Metal 3 e memoria grafica condivisa dinamica fino a 1536 MB. Il pannello interno è online a 1920×1080. Il campione powermetrics rileva IntelAccelerator e boot-args senza `-igfxvesa` né `-x`. La correzione e i limiti delle verifiche sono documentati in [TEST-MEMORIA-INTEL.md](../../archive/primo-avvio/docs/TEST-MEMORIA-INTEL.md) e [GRAFICA-INTEL.md](../guides/GRAFICA-INTEL.md).

Un campione di circa un secondo riporta 50 °C per la CPU e 0,98 W stimati per il pacchetto Intel. È una misura istantanea: non verifica la NVIDIA, le ventole o l'autonomia. Lo spegnimento elettrico della dGPU resta aperto.

## Gestione CPU e campioni a riposo: 13 ottobre 2026

IORegistry mostra X86PlatformPlugin registered, matched e active. Dopo l'invito a lasciare il portatile inattivo sono stati forniti due campioni powermetrics, ciascuno con intervallo di cinque secondi:

| Voce | Primo campione | Secondo campione |
|---|---|---|
| Pacchetto Intel stimato, CPU + iGPU + system agent | 0,95 W | 0,80 W |
| Temperatura CPU riportata a fine intervallo | 46 °C | 45 °C |
| Frequenza media sistema riportata | 947,43 MHz | 965,75 MHz |
| Frequenza attiva iGPU riportata | 300 MHz | 300 MHz |

Il driver di gestione CPU è quindi attivo e i campioni mostrano un basso consumo Intel stimato a riposo. Le temperature sono letture istantanee alla fine di ciascun intervallo. Il rapporto GPU 100% è rispetto alla frequenza nominale indicata di 300 MHz, non una misura di utilizzo al 100%.

Il report contiene ancora Invalid key detected e non riporta RPM delle ventole: la telemetria SMC resta parziale. Successivamente è stato riferito che la ventola non fa rumore da tempo: la situazione a riposo è quindi confermata anche dall'osservazione sul portatile. Questi dati non verificano la temperatura sotto carico, il consumo o lo spegnimento elettrico della NVIDIA, la batteria o la sospensione. I campi LastSleepType del plugin non costituiscono una prova di sospensione riuscita.

## Correzione del pannello e stato Bluetooth: 13 ottobre 2026

La prova del solo `-igfxblr` ha eliminato il nero all'avvio nell'esito riferito: da circa due minuti a zero. Si conserva la configurazione, mantenendo memoria Intel, audio e SIP. Il report precedente al test mostra lo stesso UUID framebuffer e Loginwindow pronto circa 31,3 secondi dopo il kernel. La [diagnosi](../guides/AVVIO-RETE.md) distingue il ritardo del pannello dal tempo di avvio del sistema.

Lo stato Bluetooth è On, FirmwareLoaded è Yes e il trasporto è connesso; BlueToolFixup 2.7.2 e IntelBluetoothFirmware 2.4 sono caricati, IntelBTPatcher è assente. Le due variabili NVRAM richieste sono presenti con i valori corretti: un byte zero e quattordici byte zero. Lo stack avvia la scansione e riceve dispositivi BLE. Il 14 ottobre 2026 è stato riferito il funzionamento con cuffie Bluetooth, insieme al funzionamento di HeliPort per la gestione delle reti Wi-Fi. Si conservano i driver e la NVRAM attuali. Questo esito non verifica il microfono delle cuffie, il microfono interno ALC257, il jack analogico o la riconnessione dopo stop.

## Webcam e acquisizione voce: 14 ottobre 2026

Nella prova proposta con Photo Booth è stato riferito che l'immagine è visibile e la voce viene registrata. Il guadagno microfono risulta troppo alto: la successiva regolazione passa bruscamente da troppo alto a troppo basso. Sono da verificare ingresso selezionato e controlli del mixer prima di una modifica. La webcam è quindi funzionante nella prova; il livello dell'ingresso audio non è ancora confermato corretto. Questo esito precede la correzione microfono descritta qui sotto.

## Correzione microfono: 14 ottobre 2026

Il 14 ottobre 2026, dopo la prova del pacchetto **S540-microfono-fix-v2** e il riavvio, è stato riferito un primo esito positivo. Il report della verifica e registrazioni di confronto non sono ancora stati acquisiti. Si conserva questa versione con il backup del driver precedente; equalizzazione e tasti funzione restano rinviati.

La [prova](../guides/MICROFONO-FIX.md) usa VoodooHDA 3.6.9 variante S540: il cursore ingresso controlla i 64 livelli dell'ADC, il boost microfono resta a 0 dB e il volume PCM degli altoparlanti conserva la correzione v3. Il pacchetto v2 elimina la dipendenza dell'installer da strumenti Xcode. I controlli CI su formato, integrità, firma e ripristino sono passati; il primo riscontro d'uso non viene esteso al jack o al recupero dopo stop.

## Batteria e contatori di stop: 13 ottobre 2026

Il campione pmset mostra batteria interna presente, 100%, charged e alimentazione AC Power. I contatori del sistema sono Sleep Count 1, User Wake Count 1, Dark Wake Count 0. Impostazioni e limiti sono conservati in [BATTERIA-SOSPENSIONE.md](BATTERIA-SOSPENSIONE.md): non sono ancora verificati passaggio a batteria, autonomia o recupero completo delle periferiche. Le ulteriori prove di stop sono rinviate, dando priorità al pannello spento all'avvio, Bluetooth e gestione Wi-Fi.

## Pannello e tasti luminosità: 13 ottobre 2026

Il cursore macOS regola realmente la luminosità del pannello. I tasti F11/F12 non funzionano nella prova riferita; il risultato con Fn non è ancora specificato. La retroilluminazione è quindi funzionante e non si aggiungono nuove patch PNLF o framebuffer per il solo problema dei tasti.

Il DSDT originale contiene i metodi H_EC._Q8E e _Q8F che inviano al pannello GFX0.DD1F le notifiche ACPI 0x86 e 0x87, con condizioni firmware che possono sopprimere alcuni eventi. Il lavoro su F11/F12 è stato rinviato, su richiesta, a un unico blocco con gli altri tasti funzione. In quella fase si verificheranno Fn e gli eventi prodotti, poi si valuterà BrightnessKeys come candidato mirato; non è stato applicato. F1–F3 funzionanti e cursore luminosità vengono conservati. Non si rinominano preventivamente i metodi _Q.

## Audio dal desktop: 13 ottobre 2026

`system_profiler SPAudioDataType` non espone dispositivi. Tra i kext cercati è caricato soltanto Lilu 1.7.2: AppleALC e AppleHDA sono assenti dall'elenco. La configurazione esclude AppleALC oltre Darwin 24; Tahoe ha rimosso AppleHDA. È stata preparata una [prova reversibile VoodooHDA 3.6.8](../guides/AUDIO-TAHOE.md) in Library/Extensions, con layout 11 incluso per ALC257. Dopo la correzione del controllo SIP è stato riferito il funzionamento della riproduzione audio e dei tasti F1–F3. Il difetto iniziale del volume, percepibile soltanto a zero/muto, è stato superato dopo la prova v3 con VoodooHDAEnableVolumeChangeFix=true. È stato riferito un esito positivo della riproduzione e della regolazione graduale. L'equalizzazione è annotata per un affinamento più avanti; jack, microfono e ripresa restano da documentare. Il ripristino AppleHDA nel volume di sistema resta una strategia successiva.

Le sezioni successive descrivono i tentativi precedenti al raggiungimento del desktop.

## Esito della prima prova della Recovery

Il 13 ottobre 2026 è stato riferito il raggiungimento della selezione della lingua e il funzionamento di mouse, tastiera e Wi-Fi nella Recovery. Non è stato specificato se il mouse indicato sia il touchpad o un dispositivo USB: il touchpad ELAN resta da verificare separatamente.

L'esito è stato comunicato dopo la proposta del test `-igfxvesa`. I boot-args effettivi non sono stati raccolti, quindi non si attribuisce ancora il risultato con certezza a quel parametro. La comparsa della Recovery non dimostra l'accelerazione Metal, né la compatibilità completa del sistema installato. La [verifica Intel](../guides/GRAFICA-INTEL.md) parte da questi dati dopo l'installazione.

## Rilevamento del disco esterno e preferenza per l'interno

Il 960 EVO non compariva perché il modulo M.2 si era sganciato nel box. Dopo averlo reinserito è stato riferito il rilevamento del disco. Questo esito risolve il problema di rilevamento osservato; non conferma ancora la velocità SuperSpeed né entrambe le orientazioni della USB-C.

Il disco interno è stato riferito visibile nella Recovery: l'esclusione tramite blocco del driver NVMe non è risultata verificata in questa prova. È stato richiesto di lasciare il disco Windows al suo posto e procedere sul 960 EVO esterno. Nessuna inizializzazione o modifica delle partizioni del disco interno è stata eseguita. Le prove successive valuteranno eventuali problemi di stabilità.

## Log OpenCore delle 02:45

Il log del 13 ottobre 2026 conferma la selezione del volume USB esterno, con nome **Machintosh SSD**, e la presenza di `-igfxvesa` e `-x`. OpenCore riporta l'iniezione riuscita di Lilu 1.7.2 e WhateverGreen 1.7.1 e l'impostazione delle proprietà Intel. Il log non conferma l'inizializzazione dei driver nel kernel o Metal. In quel tentativo il desktop non era ancora stato raggiunto.

L'[analisi del log](../../archive/primo-avvio/docs/ANALISI-LOG-AVVIO.md) riporta anche il percorso Apple con immagine BaseSystem, l'assenza della tabella MAT e i limiti del blocco NVMe. Il file originale e gli identificativi SMBIOS non vengono aggiunti alla repository.

## Panic USB/Bluetooth successivo

La fotografia ricevuta successivamente mostra un vero panic con processo `bluetoothd`, estensioni IOUSBHostFamily e IntelBTPatcher 2.4 nella traccia, Darwin 25.6.0 e build macOS 25G241. Nei boot-args visibili manca `-x`, mentre rimane `-igfxvesa`. L'intestazione del panic è fuori dall'inquadratura, quindi la causa precisa resta da confermare.

La [prova Bluetooth](../guides/TEST-BLUETOOTH.md) esclude solo IntelBTPatcher dalla EFI attuale. La versione 2.4 precede la correzione ufficiale della gestione del descrittore di memoria USB per Sequoia e successivi; il builder la esclude dalle nuove EFI. Il firmware Intel, BlueToolFixup e itlwm restano presenti. La prova sul portatile ha superato il panic e raggiunto uno schermo nero con il puntatore. È stata riferita attività del disco, senza comparsa di finestre. Il log di questo tentativo è stato ricevuto: conferma `-igfxvesa` attivo e `-x` assente. Non contiene l'iniezione di IntelBTPatcher; firmware Intel e BlueToolFixup sono ancora iniettati. L'iniezione di Lilu/WhateverGreen riesce, ma non dimostra l'inizializzazione della grafica nel kernel. Due log successivi, `103339` e `103615`, confermano la rimozione di VESA e dell'avvio sicuro mantenendo IntelBTPatcher escluso. Una nuova foto mostra lo stallo sul testo con errori di servizi, firme del codice e DriverKit, senza una riga di panic. Il caricamento di Lilu/WhateverGreen non prova Metal. La successiva [raccolta dei report del sistema da Recovery](../../archive/primo-avvio/docs/DIAGNOSI-INTERFACCIA.md) ha preceduto la diagnosi del panic Intel e la correzione memoria. Il confronto con una build aggiornata del patcher e le funzioni Bluetooth restano da verificare.

## Prima raccolta dei report in Recovery

La Recovery ha aperto l'interfaccia e il Terminale e ha letto Machintosh SSD - Data. Il report APFS mostra un container da 249.8 GB sul supporto esterno, il volume System sigillato e Data montato senza FileVault. La raccolta contiene un vecchio panic Bluetooth e i log dell'installazione, che arriva al benvenuto Hello; in quella raccolta la configurazione iniziale non era ancora completata. Non è una verifica di Metal o del funzionamento del Bluetooth.
