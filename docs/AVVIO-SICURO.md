# Prova di avvio sicuro da Macintosh SSD

Nel tentativo dal volume «Macintosh SSD», il log indica `WindowServer: Job state = running`, errori AppleKeyStore nelle richieste di `bluetoothd`, attività `com.apple.fskit.msdos` e `AppleActuatorDevice ... returned error 0xe00002c7`. L'ultimo codice indica una funzione non supportata. Il log continua dopo l'errore e non mostra un kernel panic esplicito. La comparsa del nome del volume e l'avvio del processo WindowServer non confermano il completamento dell'installazione o il funzionamento della grafica.

Questi messaggi non identificano da soli la causa del mancato passaggio alla schermata grafica. Il test aggiunge **solo `-x`**, che richiede l'avvio sicuro. Non disabilita singolarmente i kext e non sostituisce la configurazione completa. Gli altri boot-args, incluso l'eventuale `-igfxvesa`, restano quelli presenti.

## Quando usare la prova

Usa questa prova per il volume di macOS, quando l'avvio resta sulla schermata di testo senza avanzare. Se nel menu compare ancora **macOS Installer**, completa prima quella fase. Mantieni alimentatore, HDD di avvio e SSD esterno collegati.

## Da Windows

1. Scarica `S540-avvio-sicuro.zip` e avvia Windows dal menu Lenovo.
2. Estrai il contenuto **nella radice dell'HDD che contiene la EFI attuale**. Devono risultare `AVVIO-SICURO.cmd` accanto a `EFI`, e `tools/test_safe_boot.py` nella cartella `tools` dello stesso HDD.
3. Avvia **AVVIO-SICURO.cmd**. Usa Python 3, gia usato per la Recovery. Attendi il messaggio **Prova attivata: aggiunto solo -x**.
4. Riavvia dallo stesso OpenCore e scegli **Macintosh SSD**.
5. Se compare la configurazione iniziale, prosegui fino al desktop e raccogli i dati indicati sotto. Se si ferma, raccogli la nuova schermata e il tempo trascorso.

Il backup e `EFI/OC/config.before-safe-boot.plist`. Lo script preserva identificativi SMBIOS, ACPI, proprieta Intel, impostazioni dei dischi e profilo Wi-Fi. Verifica la riscrittura dei boot-args in NVRAM e `EnableSafeModeSlide`, gia presente nella EFI iniziale. Non scrive partizioni, non scarica kext e non invia dati.

## Dati dal desktop, se raggiunto

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

L'avvio sicuro puo limitare servizi e prestazioni. Un eventuale successo restringe l'indagine, ma non identifica un driver specifico e non dimostra Metal. Anche un insuccesso, da solo, non esclude un problema software.

## Ripristino

Da Windows avvia **RIPRISTINA-AVVIO.cmd** sullo stesso HDD. Ripristina esattamente il plist precedente e conserva il backup. Se sono state aggiunte altre modifiche, lo script rifiuta il ripristino automatico.

Il backup di questo test e quello del precedente test grafico sono distinti. Ripristina prima la prova di avvio sicuro; l'eventuale rimozione di `-igfxvesa` viene valutata dopo i dati del sistema installato.

## Riferimenti

- [OpenCore 1.0.8: safe mode, -x e EnableSafeModeSlide](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex)
- [Apple: codici IOKit, incluso kIOReturnUnsupported](https://github.com/apple-oss-distributions/xnu/blob/main/iokit/IOKit/IOReturn.h)
