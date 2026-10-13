# Pannello spento all'avvio, Bluetooth e Wi-Fi

Queste sono le priorità correnti. Batteria e contatori sono conservati in [BATTERIA-SOSPENSIONE.md](BATTERIA-SOSPENSIONE.md). Le prove di sospensione, i tasti funzione e l'equalizzazione sono rinviati.

## Distinguere avvio del sistema e accensione del pannello

Il 13 ottobre 2026 è stato riferito un pannello letteralmente spento per circa due minuti, prima della comparsa della mela. Durante quel periodo macOS accetta già la password e permette il login. Questo orienta la diagnosi verso l'accensione del pannello e la retroilluminazione; non documenta un blocco dell'intero sistema.

Il codice ufficiale WhateverGreen 1.7.1 include due correzioni: BLR (`-igfxblr`) intercetta le scritture dei registri PWM; BLT (`-igfxblt`) riconosce e riscrive specifiche sequenze inlined. La guida generale consiglia BLT per KBL/CFL da macOS 13.4, perché in quei driver le chiamate erano state incorporate nelle funzioni.

Nel dump Tahoe già raccolto, il framebuffer CFL ha UUID `7E294F0F-852E-3252-B54D-61D9A7BBE6B2`. La sezione executable è completa: 601466 byte. La sequenza LEA con displacement `0xFFF37DA7`, richiesta dal probe BLT per CFL, non è presente. Sono invece presenti chiamate a una funzione comune per i registri PWM `0xC8254` e `0xC8258`. Il dump è mappato in memoria e non conserva LINKEDIT: i nomi delle funzioni non sono risolvibili direttamente.

**Inferenza:** per questo preciso driver, il solo BLR è un candidato più coerente del BLT generico. La prova richiede lo stesso UUID del driver caricato e Darwin 25.6.0. Non è una correzione confermata sul portatile né una raccomandazione per tutte le versioni Tahoe. Non si combinano BLR, BLT e altre opzioni grafiche.

## Raccolta dal desktop

`RACCOGLI-AVVIO-RETE.command` legge i primi cinque minuti dell'avvio corrente, i driver caricati e il loro UUID, lo stato Bluetooth/USB, la grafica e i servizi di rete. Le due variabili NVRAM Bluetooth sono lette separatamente; la loro assenza non impedisce lo ZIP. Le letture attuali dei dispositivi sono successive all'avvio.

Il comando non modifica EFI, NVRAM o driver. La password serve solo alla lettura dei log. Crea sulla Scrivania una cartella privata e `DIAGNOSI-AVVIO-RETE-XXXXXX.zip`, da allegare nella chat. Il report può contenere indirizzi hardware e messaggi dei processi: non va aggiunto alla repository. Non include config completo, PlatformInfo o Info.plist di itlwm con credenziali.

Estrarre il pacchetto in Downloads e avviare:

```sh
bash "$HOME/Downloads/S540-avvio-rete/RACCOGLI-AVVIO-RETE.command"
```

Non serve Recovery, una reinstallazione o un nuovo driver DEBUG. I vecchi log OpenCore terminano prima degli eventi del kernel; quelli unificati disponibili descrivono prove precedenti alla correzione memoria e non accertano la causa del nero attuale.

## Prova del pannello

```sh
bash "$HOME/Downloads/S540-avvio-rete/TEST-SCHERMO-AVVIO.command"
```

La prova salva il config corrente privatamente in `EFI/OC/backup-schermo-avvio`, verifica il driver effettivamente caricato e aggiunge soltanto `-igfxblr`. Conserva identità, memoria framebuffer 19 MB/9 MB, layout audio e SIP. Riavviare dallo stesso HDD OpenCore e confrontare l'attesa a pannello spento. Dopo il riavvio, `sysctl -n kern.bootargs` deve includere `-igfxblr`: se manca, la patch non è stata provata nel kernel.

Per annullarla:

```sh
bash "$HOME/Downloads/S540-avvio-rete/ANNULLA-SCHERMO-AVVIO.command"
```

Il ripristino verifica il backup e conserva i byte originali. **Prima di altre modifiche alla EFI, annullare questa prova.** Anche il ripristino audio v3 protegge config e albero dei kext con hash; non si riscrivono i suoi snapshot per aggirare quei controlli. Un eventuale mantenimento definitivo della correzione richiede gestire insieme gli stati di ripristino.

## Bluetooth

IntelBTPatcher 2.4 resta escluso dopo il panic. Il suo sorgente precede la correzione del descrittore HCI USB per Sequoia e successivi. Una build di sviluppo 2.5.0 del sorgente ufficiale `a414375505fa3b014be32f8fca31b5bbfdf9f10f`, con supporto Tahoe dichiarato, è disponibile da Dortania; non è una release stabile.

BlueToolFixup 2.7.2 è già presente. Il progetto richiede per Intel le variabili NVRAM `bluetoothExternalDongleFailed` Data `00` e `bluetoothInternalControllerInfo` Data di tredici byte zero, nel GUID Apple `7C436110-AB2A-4BBB-A880-FE41995C9F82`. Nella EFI esaminata non sono impostate. La raccolta controlla se esistono nella NVRAM attiva e se il firmware è caricato. I dati serviranno a scegliere la modifica; il vecchio patcher non viene riabilitato.

## Wi-Fi indicato come Ethernet

È il comportamento previsto di itlwm 2.3.0: usa IOEthernetController. Rinominare il servizio non lo trasforma in una periferica IO80211. La gestione delle reti può avvenire con HeliPort o con i profili del driver; il progetto dichiara che questa rappresentazione non riduce le prestazioni.

La release stabile ufficiale AirportItlwm 2.3.0 ha pacchetti fino a Sonoma, senza un asset Tahoe. Le strategie con vecchi driver Airport e ripristino dei framework Wi-Fi richiedono modifiche più ampie al sistema e al SIP. L'integrazione nativa su Tahoe resta un lavoro separato; non si sostituisce ora il driver funzionante soltanto per cambiare la voce Ethernet e non si promette AirDrop.

## Verifiche e limiti

Gli script sono verificati per sintassi Bash e con fixture simulate su Linux. La raccolta copre finestra del boot, timeout, errori, filtro dei dati e creazione ZIP. Le operazioni native macOS e la prova della retroilluminazione devono essere eseguite sul portatile.

## Fonti

- [WhateverGreen 1.7.1: codice delle correzioni di retroilluminazione](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/WhateverGreen/kern_igfx_backlight.cpp).
- [WhateverGreen 1.7.1: guida Intel](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md#fix-the-3-minute-black-screen-issue-on-kblcfl-platforms-running-macos-134-or-later).
- [Manuale Apple di log](https://keith.github.io/xcode-man-pages/log.1.html).
- [OpenIntelWireless: differenze tra itlwm e AirportItlwm](https://openintelwireless.github.io/itlwm/FAQ.html).
- [BlueToolFixup: variabili NVRAM Intel](https://github.com/acidanthera/BrcmPatchRAM#bluetoolfixupkext).
- [Correzione IntelBTPatcher del descrittore HCI](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/commit/50e971c524081a1d97a72794db2640aa0136e284).
- [Build di sviluppo IntelBluetoothFirmware a414375](https://github.com/dortania/build-repo/releases/tag/IntelBluetoothFirmware-a414375).
