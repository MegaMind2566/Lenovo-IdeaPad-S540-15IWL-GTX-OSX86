# Panic USB/Bluetooth: prova senza IntelBTPatcher

## Dati della schermata ricevuta il 13 ottobre 2026

La fotografia mostra un kernel panic con questi dati leggibili:

| Dato | Valore |
|---|---|
| Processo del thread corrente | `bluetoothd` |
| Estensioni nella traccia | `com.apple.iokit.IOUSBHostFamily`, `com.zxystd.IntelBTPatcher (2.4)` |
| Percorso USB visibile | `IOUSBHostDevice::deviceRequest`, `IOUSBHostUserClient::controlRequest` |
| Kernel | Darwin `25.6.0` |
| Build macOS | `25G241` |
| Parametro grafico diagnostico | `-igfxvesa` presente |
| Avvio sicuro | `-x` assente dai boot-args mostrati |

La prima riga `panic(...)` e l'inizio della traccia sono fuori dall'inquadratura. La foto individua il percorso Bluetooth/USB e rende IntelBTPatcher il primo componente da isolare; non dimostra ancora il punto esatto che ha provocato il panic. Non è un semplice arresto del testo di avvio.

## Differenza tra la release inclusa e il sorgente aggiornato

La EFI iniziale includeva IntelBluetoothFirmware/IntelBTPatcher **v2.4.0**, pubblicata il 27 febbraio 2024. Il sorgente di IntelBTPatcher in quel tag dichiara Sonoma come versione massima del kernel; `-ibtcompatbeta` ne permetteva il caricamento sulle versioni successive, senza aggiornare la logica della patch USB.

Il progetto ufficiale ha poi corretto la preparazione del descrittore di memoria HCI per Sequoia e successivi:

- [Correzione del 24 giugno 2024](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/commit/50e971c524081a1d97a72794db2640aa0136e284).
- [Limitazione della correzione a Sequoia e successivi](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/commit/01cc1806d71f5cc64c464851b9f4811a3e7b4791).
- [Sorgente con supporto dichiarato per Tahoe, fissato al commit a414375](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/blob/a414375505fa3b014be32f8fca31b5bbfdf9f10f/IntelBTPatcher/IntelBTPatcher.cpp).
- [Release v2.4.0](https://github.com/OpenIntelWireless/IntelBluetoothFirmware/releases/tag/v2.4.0).

La differenza nel codice è verificata. Che sia la causa di questo specifico panic resta un'ipotesi da confermare con la prova. La prima EFI va corretta escludendo il vecchio patcher; un'eventuale riattivazione richiede una build ufficiale del sorgente aggiornato e una prova sul dispositivo.

## Prossimo avvio

1. Torna in Windows. Se hai annullato l'avvio sicuro con `RIPRISTINA-AVVIO.cmd` ma rimane il test VESA, completa ora il ripristino con **RIPRISTINA-GRAFICA.cmd**. Nella foto `-igfxvesa` è ancora presente. Se hai già usato `TEST-INTEL.cmd` sulla EFI attuale, salta i vecchi ripristini.
2. Estrai il pacchetto **S540-test-Bluetooth.zip** nella radice dell'HDD che avvia OpenCore, accanto alla cartella `EFI`.
3. Esegui **TEST-BT.cmd**. Deve confermare che ha escluso solo `IntelBTPatcher.kext` e salvato il backup. Se segnala un errore, conserva il messaggio e interrompi la prova.
4. Spegni il portatile e riaccendilo. Avvia lo stesso OpenCore e scegli **Machintosh SSD**.
5. Riferisci se compare nuovamente il panic oppure l'interfaccia. Un avvio riuscito consentirà di tornare alla verifica Intel e di confrontare poi una versione aggiornata del patcher.

La prova imposta soltanto `Kernel → Add → IntelBTPatcher.kext → Enabled = false`. Conserva IntelBluetoothFirmware, BlueToolFixup e itlwm. Il comportamento del Bluetooth senza il patcher va ancora verificato: la prova non garantisce che tutte le funzioni Bluetooth restino disponibili.

## Ripristino

**RIPRISTINA-BT.cmd** ripristina esattamente i byte di `EFI/OC/config.before-bt-test.plist`. Il ripristino rifiuta di sovrascrivere altre modifiche intervenute dopo la prova. Se sono state applicate più prove, annullale nell'ordine inverso a quello di applicazione.

In alternativa, con un editor plist, il test consiste nel mettere `Enabled = false` soltanto nella voce `IntelBTPatcher.kext` di `Kernel/Add`. Non cancellare la voce o il file del kext.

## Verifica del programma

Il programma è verificato sulla configurazione della EFI già consegnata: cambia un solo booleano, conserva gli altri valori, si può eseguire due volte, ripristina i byte originali e rifiuta backup di un altro stato o modifiche successive. Rifiuta anche configurazioni con la voce mancante, duplicata o con `Enabled` di tipo errato. L'esito sul portatile resta da raccogliere.
