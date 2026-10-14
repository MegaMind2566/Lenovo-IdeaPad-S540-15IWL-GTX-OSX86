# Primo avvio su Samsung 960 EVO USB-C

Questo pacchetto è una prima configurazione da provare sul Lenovo IdeaPad S540-15IWL GTX, BIOS BWCN19WW. I controlli automatici verificano i file e la configurazione; avvio e periferiche richiedono una prova sul portatile.

## Scarica il pacchetto

Nella repository apri **Actions → EFI per la prima prova**, seleziona l'ultima esecuzione riuscita e scarica l'artefatto **S540-81SW-Tahoe-prima-prova**. Estrai lo ZIP dell'artefatto, poi lo ZIP del pacchetto che contiene. Alla fine devi vedere una cartella `EFI` e il file `SCARICA-RECOVERY.cmd` nella stessa cartella.

## Prepara i file da Windows

1. Installa [Python 3 per Windows](https://www.python.org/downloads/windows/) se non è già presente. Il launcher `py` o il comando `python` deve funzionare.
2. Avvia **SCARICA-RECOVERY.cmd**. Scarica la Recovery ufficiale Apple compatibile con il modello Intel scelto. Attendi il messaggio di completamento: vengono scaricati `BaseSystem.dmg` e `BaseSystem.chunklist` in `com.apple.recovery.boot`.
3. Avvia **CONFIGURA-WIFI.cmd** e inserisci SSID e password della rete. `itlwm` usa quel profilo per tentare il collegamento automatico, anche nella Recovery. La rete viene presentata come Ethernet; non aspettarti il normale menu Wi-Fi Apple. Il collegamento nella Recovery è da verificare sul portatile.
4. Usa una **chiavetta separata, da almeno 8 GB, che puoi cancellare**. Con [Rufus](https://rufus.ie/) seleziona la chiavetta controllandone modello e capacità, **Non avviabile**, schema **GPT** e filesystem **FAT32**. La formattazione cancella la chiavetta scelta: il 960 EVO deve restare scollegato durante questo passaggio.
5. Copia nella radice della chiavetta le cartelle `EFI` e `com.apple.recovery.boot`. Deve risultare `EFI/BOOT/BOOTx64.efi`, non `EFI/EFI/BOOT/...`.

Il profilo Wi-Fi scrive la password nel plist locale. Non caricare la EFI configurata con la tua rete su GitHub o in chat. Gli script non inviano SSID o password e non formattano dischi.

Conserva `IDENTITA-SMBIOS.json` insieme al pacchetto. Serve a mantenere gli stessi identificativi nelle future revisioni. Ogni build nuova senza quel file genera identificativi diversi; per adesso evita di collegare i servizi Apple.

## Prova l'avvio

1. Spegni il portatile. Collega la chiavetta a una USB-A e il **960 EVO alla USB-C**, con il box e il cavo destinati all'uso finale. Scollega gli altri dischi esterni.
2. In BIOS lascia **Secure Boot disabilitato** e usa l'avvio UEFI. Non cambiare la modalità del disco interno e non aggiornare il BIOS per questa prova.
3. Apri il menu di avvio Lenovo con **F12/Fn+F12** oppure il pulsante **Novo** e seleziona la chiavetta UEFI.
4. In OpenCore scegli **macOS Base System** o la voce Recovery. Il testo di diagnostica durante l'avvio è previsto.
5. Per la prima prova fermati alla schermata delle **Utility macOS**. Controlla tastiera, touchpad, connessione Internet e presenza del disco USB-C in Utility Disco. Rileva modello e capacità del disco esterno senza inizializzarlo.

Invia l'esito e una foto leggibile dell'ultima schermata se l'avvio si blocca. I log `opencore-*.txt` vengono salvati nella radice della chiavetta. Il log della compilazione è già incluso come `ocvalidate.txt`.

## Cosa contiene la configurazione

- OpenCore 1.0.8 DEBUG; driver OpenRuntime e HfsPlus.
- Identità `MacBookPro16,2`, tra i modelli Intel ammessi da Tahoe. La gestione energetica sul processore Whiskey Lake deve ancora essere verificata.
- UHD 620 con piattaforma `00009B3E` e device-id `9B3E0000`. DVMT non ancora misurato; nessuna correzione memoria aggiunta senza un errore concreto.
- Le sei SSDT compilate del progetto. La patch di spegnimento NVIDIA è **disabilitata** per la prima prova; `-wegnoegpu` evita il driver ma non garantisce lo spegnimento elettrico.
- Mappa USB del portatile con 9 porte; `XhciPortLimit` disabilitato.
- VoodooPS2 per la tastiera; VoodooI2C e VoodooI2CHID per ELAN0662.
- VirtualSMC, SMCProcessor e SMCBatteryManager; lettura della batteria da verificare.
- `itlwm` per Intel AC9560; dopo l'installazione si potrà usare [HeliPort](https://github.com/OpenIntelWireless/HeliPort/releases/tag/v1.5.0).
- IntelBluetoothFirmware e BlueToolFixup attivi. IntelBTPatcher 2.4 presente ma escluso nelle nuove build dopo un panic USB/Bluetooth; `-ibtcompatbeta` rimosso. Per la EFI già consegnata usare la [prova reversibile Bluetooth](../guides/TEST-BLUETOOTH.md). Bluetooth da verificare.
- AppleALC viene caricato **solo su Sequoia**, con layout iniziale 11. L'audio analogico non è ancora ripristinato su Tahoe.
- SIP abilitato; `SecureBootModel=Disabled` e RestrictEvents con `revpatch=sbvmm` per il percorso di aggiornamento Tahoe.

## Disco interno e limiti

La configurazione contiene un tentativo di blocco di `com.apple.iokit.IONVMeFamily` in macOS. Il PM981a interno è comunque stato riferito visibile nella Recovery: l'esclusione non è confermata. Il 960 EVO collegato tramite USB usa lo stack USB. Se verrà montato internamente, la configurazione NVMe dovrà essere riesaminata prima dell'avvio. Il disco Windows resta al suo posto; il firmware del disco non viene modificato.

Avvia Windows direttamente dal menu Lenovo durante le prove. L'uscita HDMI, l'audio analogico su Tahoe, la sospensione, la luminosità, il Bluetooth e l'autonomia sono ancora da verificare o completare.

Nella raccolta USB il box RTL9210 compare sulla porta USB-C a velocità USB 2. La porta SuperSpeed associata è inclusa nella mappa ma senza un dispositivo rilevato: verifica il cavo USB 3 e prova entrambe le orientazioni del connettore. Non si può dedurre dal nome del bridge il modello o la capacità del disco nel box.

Se il blocco avviene su `EXITBS:START`, raccogli il log prima di cambiare opzioni. Il primo tentativo usa `RebuildAppleMemoryMap=true`, `SyncRuntimePermissions=true` e `EnableWriteUnprotector=false`; l'alternativa per firmware privi della mappa attributi va scelta in base al log.

## Riferimenti

- [OpenCore 1.0.8](https://github.com/acidanthera/OpenCorePkg/releases/tag/1.0.8)
- [Guida Coffee Lake / Whiskey Lake](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html)
- [Note per Tahoe](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html)
- [USBToolBox e tipi di connettore](https://github.com/USBToolBox/tool/blob/master/TYPES.md)
- [itlwm: configurazione Wi-Fi](https://openintelwireless.github.io/itlwm/FAQ.html)
