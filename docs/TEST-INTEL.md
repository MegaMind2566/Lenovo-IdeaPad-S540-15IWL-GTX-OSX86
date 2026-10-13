# Prova Intel dopo il puntatore con scia

Nel tentativo da «Macintosh SSD» è comparso il puntatore senza finestre. È stata riferita una scia durante il movimento. Questo è compatibile con un problema di ridisegno dello schermo, ma non identifica da solo driver, framebuffer o memoria come causa.

La configurazione effettivamente avviata non è stata raccolta: non si assume che siano presenti `-x` o `-igfxvesa`. Questa prova controlla la EFI locale e rimuove **soltanto questi due parametri**, se presenti. `-x` richiede l'avvio sicuro; `-igfxvesa` disabilita l'accelerazione Intel. La rimozione permette di provare l'avvio normale con la configurazione UHD 620 già preparata. Non garantisce che Metal funzioni.

## Applicazione da Windows

Usa la prova sul volume di macOS. Se è ancora presente **macOS Installer** nel menu OpenCore, completa prima quella fase.

1. Avvia Windows dal menu Lenovo.
2. Estrai `S540-test-Intel.zip` **nella radice dell'HDD che contiene la EFI usata per l'avvio**. Devono risultare `TEST-INTEL.cmd` accanto a `EFI`, e `tools/test_safe_boot.py` nella cartella `tools` dello stesso HDD. Accetta la sostituzione di questo script se proviene dal pacchetto di avvio sicuro precedente.
3. Avvia **TEST-INTEL.cmd**. Serve lo stesso Python 3 usato per la Recovery.
4. Leggi l'esito. Se compare **Prova Intel attivata**, il programma elenca i parametri che ha rimosso. Se segnala che sono assenti, non modifica il file: raccogli il testo della finestra prima di proseguire con altri cambiamenti.
5. Dopo una modifica riuscita, riavvia dallo stesso HDD con OpenCore e scegli **Macintosh SSD**.

Il backup è `EFI/OC/config.before-intel-test.plist`. Gli identificativi SMBIOS, le proprietà Intel, i kext, le ACPI e le altre impostazioni vengono conservati. Il profilo Wi-Fi resta nel proprio kext. Non si sovrascrive l'intera EFI e non si inizializzano dischi.

## Come leggere il risultato

- Se compare la configurazione iniziale di macOS, prosegui fino al desktop e raccogli i dati indicati sotto.
- Se l'avvio si blocca, raccogli la nuova schermata. Tornando a Windows, **RIPRISTINA-INTEL.cmd** recupera esattamente la configurazione presente prima di questa prova.
- Se il puntatore continua a lasciare la scia, serviranno i boot-args effettivi, i log e il framebuffer applicato. La scia non dimostra automaticamente che DVMT sia impostato a 32 MB.

Dal desktop, apri Terminale ed esegui:

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

Per questa prova usa il suo ripristino, **RIPRISTINA-INTEL.cmd**. I backup dei precedenti test restano separati. Gli script rifiutano il ripristino se sono state aggiunte altre modifiche, così non le cancellano.

## Riferimenti

- [WhateverGreen 1.7.1: -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics)
- [OpenCore 1.0.8: -x e avvio sicuro](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex)
- [Dortania: UHD 620 su Coffee Lake e Whiskey Lake](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties)
