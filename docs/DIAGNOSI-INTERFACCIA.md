# Raccolta dei report dall'installazione senza interfaccia

I log `opencore-2026-10-13-103339.txt` e `opencore-2026-10-13-103615.txt` confermano l'assenza di `-igfxvesa` e `-x`. IntelBTPatcher non viene iniettato; Lilu e WhateverGreen risultano iniettati con successo. Questo non dimostra che la grafica si inizializzi o che Metal funzioni. Il log termina al passaggio al kernel, prima degli eventi dell'interfaccia.

La nuova fotografia mostra servizi di macOS e caricamento delle collezioni di estensioni, senza una riga di panic. Contiene errori di firma del codice, un limite di memoria esplicitamente non fatale di kernelmanagerd e fault ripetuti di IOUserDockChannelSerial. Nessuna di queste righe identifica da sola la causa del mancato desktop.

Ora servono i report del sistema installato: WindowServer, loginwindow, Setup Assistant, DriverKit o un altro processo coinvolto. La raccolta copia le cartelle DiagnosticReports complete, incluse le sottocartelle, e i file install.log/system.log se esistono. Non filtra per data o estensione. L'assenza di un report non esclude un processo bloccato o mai avviato.

## Passaggi

1. In Windows estrai **S540-diagnosi-interfaccia.zip** nella radice dell'HDD di OpenCore. Devono risultare `RACCOGLI-LOG-MACOS.command` accanto a `EFI` e `tools/collect_gui_logs.sh` nella stessa cartella `tools`.
2. Sullo stesso HDD esegui **RIPRISTINA-INTEL.cmd**, il ripristino del test appena applicato. Ripristina il parametro VESA per tentare l'accesso alla Recovery e conserva l'esclusione Bluetooth presente prima del test Intel. Se segnala backup mancante o modifiche successive, conserva l'errore senza sostituire il config.
3. Avvia lo stesso OpenCore e scegli **Recovery 26.7.1**, presente nel menu registrato dai nuovi log. Serve la Recovery per leggere i report salvati sul Samsung. Se questa voce non apre le Utility, è presente anche la Recovery originale dell'HDD sotto il nome **240 GB**; seleziona la voce con l'icona Recovery.
4. In **Utility Disco → Vista → Mostra tutti i dispositivi**, individua il Samsung esterno e il suo volume **Data/Dati**. Montalo se necessario. Il nome atteso è **Machintosh SSD - Data**; verifica che sia il volume Data del Samsung, della stessa installazione di Machintosh SSD.
5. Apri **Utility → Terminale** dal menu superiore ed esegui:

```bash
bash /Volumes/*/RACCOGLI-LOG-MACOS.command
```

6. Il programma stampa il percorso di **DIAGNOSI-MACOS-….zip**, salvato sull'HDD di OpenCore. Torna in Windows e allega quello ZIP.

Il programma riconosce automaticamente i nomi `Machintosh SSD - Data` e `Machintosh SSD - Dati`, solo se trova la struttura prevista di un volume Data. Questi controlli non verificano il gruppo APFS: la scelta del Samsung va controllata in Utility Disco. Non monta o sblocca volumi automaticamente. Se il nome è diverso, usa il percorso esatto come argomento, per esempio:

```bash
bash /Volumes/*/RACCOGLI-LOG-MACOS.command "/Volumes/NOME ESATTO DEL VOLUME DATA"
```

Se la raccolta si ferma, fotografa il messaggio del Terminale. Le copie incomplete vengono invece indicate nel riepilogo dello ZIP. Il programma legge il volume Data e scrive soltanto la raccolta sull'HDD contenente il pacchetto; rifiuta una destinazione dentro Data. Non modifica EFI, boot-args, firme o impostazioni del sistema.

## Limiti e ritorno alla prova normale

I report raccolti descrivono il sistema sul Samsung. Un normale `log show` o `sysdiagnose` eseguito in Recovery descriverebbe la Recovery in esecuzione; non viene usato come sostituto dei log del tentativo bloccato. Se questi report non bastano, la raccolta dei dati unificati offline richiederà un passaggio distinto.

Per tornare al test normale dopo la raccolta, **TEST-INTEL.cmd** rimuove nuovamente VESA dalla EFI attuale. Il suo backup resta valido se non vengono apportate altre modifiche tra ripristino e riapplicazione. Non usare il ripristino del precedente test grafico dopo la modifica Bluetooth.

La raccolta è verificata con un volume Data simulato, nomi contenenti spazi, report nelle sottocartelle, cartelle mancanti, controlli della destinazione e creazione dello ZIP. L'esecuzione nella Recovery reale e il contenuto dei report restano da raccogliere.

## Fonti

- [Apple DTS: raccogliere l'intero contenuto di DiagnosticReports](https://developer.apple.com/forums/thread/763928).
- [Apple: montare un volume in Utility Disco](https://support.apple.com/guide/disk-utility/mount-a-volume-thats-been-ejected-dskutl1027/mac).
- [Apple WWDC22: log del sistema in esecuzione e archivi espliciti](https://developer.apple.com/videos/play/wwdc2022/10119/).

## Esito della raccolta UN5FYU

Il volume Data è stato letto e lo ZIP contiene il vecchio panic Bluetooth, install.log e system.log. L'unico errore di copia riguarda gli attributi estesi del file panic: il contenuto è presente e leggibile. Il collector aggiornato usa `cp -RX`, che copia i dati senza attributi estesi o resource fork; non occorre ripetere questa raccolta per recuperare quel panic.

Il panic nomina bluetoothd e IntelBTPatcher 2.4, con `-igfxvesa` presente e uptime coincidente con la precedente foto. Non descrive il tentativo normale con patcher escluso e VESA assente. Non ci sono report WindowServer o Setup Assistant nello ZIP; questo non prova che tali processi funzionino.

Install.log registra `Install Succeeded`, la fine di Template Migration e la cronologia di macOS 26.7.1. In uno degli avvii Language Chooser registra `hello started`, imposta a zero l'opacità della finestra di progresso e la nasconde. Il marcatore di configurazione iniziale è assente. Sono evidenze dell'arrivo al benvenuto, senza conferma che venga disegnato o completato. Gli orologi differiscono: questi messaggi non vanno attribuiti automaticamente all'ultimo tentativo senza VESA.

La prossima prova è avviare Machintosh SSD con la configurazione che ha aperto la Recovery, mantenendo IntelBTPatcher escluso e VESA temporaneo. Se ricompare lo schermo nero con il puntatore, premere una volta Invio e osservare se appare la scelta di lingua/paese. È una prova dell'avanzamento del benvenuto, non una correzione della grafica o una conferma di Metal.
