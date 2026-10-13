# Raccolta dei report dall'installazione senza interfaccia

I log `opencore-2026-10-13-103339.txt` e `opencore-2026-10-13-103615.txt` confermano l'assenza di `-igfxvesa` e `-x`. IntelBTPatcher non viene iniettato; Lilu e WhateverGreen risultano iniettati con successo. Questo non dimostra che la grafica si inizializzi o che Metal funzioni. Il log termina al passaggio al kernel, prima degli eventi dell'interfaccia.

La nuova fotografia mostra servizi di macOS e caricamento delle collezioni di estensioni, senza una riga di panic. Contiene errori di firma del codice, un limite di memoria esplicitamente non fatale di kernelmanagerd e fault ripetuti di IOUserDockChannelSerial. Nessuna di queste righe identifica da sola la causa del mancato desktop.

La prima raccolta non contiene nuovi report che spieghino lo schermo nero. Anche Invio, nella prova con la configurazione che ha aperto la Recovery, non ha fatto comparire il benvenuto. Ora la stessa raccolta offre `--unified`: oltre a DiagnosticReports e install.log/system.log, copia interamente `private/var/db/diagnostics` e `private/var/db/uuidtext` dal volume Data del Samsung. Non filtra per data o estensione. L'assenza di un report non esclude un processo bloccato o mai avviato.

## Passaggi

1. In Windows estrai la versione aggiornata di **S540-diagnosi-interfaccia.zip** nella radice dell'HDD di OpenCore, sostituendo i due file della raccolta precedente. Devono risultare `RACCOGLI-LOG-MACOS.command` accanto a `EFI` e `tools/collect_gui_logs.sh` nella stessa cartella `tools`.
2. Conserva la configurazione che ha aperto la Recovery: VESA temporaneo e IntelBTPatcher escluso. Se sei tornato alla prova Intel normale, sullo stesso HDD esegui **RIPRISTINA-INTEL.cmd**. Non ripeterlo se il ripristino è già stato applicato. Se segnala backup mancante o modifiche successive, conserva l'errore senza sostituire il config.
3. Avvia lo stesso OpenCore e scegli **Recovery 26.7.1**, presente nel menu registrato dai nuovi log. Serve la Recovery per leggere i report salvati sul Samsung. Se questa voce non apre le Utility, è presente anche la Recovery originale dell'HDD sotto il nome **240 GB**; seleziona la voce con l'icona Recovery.
4. In **Utility Disco → Vista → Mostra tutti i dispositivi**, individua il Samsung esterno e il suo volume **Data/Dati**. Montalo se necessario. Il nome atteso è **Machintosh SSD - Data**; verifica che sia il volume Data del Samsung, della stessa installazione di Machintosh SSD.
5. Apri **Utility → Terminale** dal menu superiore ed esegui:

```bash
bash /Volumes/*/RACCOGLI-LOG-MACOS.command --unified
```

6. Attendi la copia e la creazione dello ZIP; i log unificati possono occupare molto più spazio della prima raccolta. Il programma stampa il percorso di **DIAGNOSI-MACOS-….zip**, salvato sull'HDD di OpenCore. Torna in Windows e allega quello ZIP.

Il programma riconosce automaticamente i nomi `Machintosh SSD - Data` e `Machintosh SSD - Dati`, solo se trova la struttura prevista di un volume Data. Questi controlli non verificano il gruppo APFS: la scelta del Samsung va controllata in Utility Disco. Non monta o sblocca volumi automaticamente. Se il nome è diverso, usa il percorso esatto come argomento, per esempio:

```bash
bash /Volumes/*/RACCOGLI-LOG-MACOS.command --unified "/Volumes/NOME ESATTO DEL VOLUME DATA"
```

Se ci sono più copie del launcher su dischi diversi, usa il percorso esatto del launcher sull'HDD invece dell'asterisco. Se la raccolta si ferma, fotografa il messaggio del Terminale. Le copie incomplete vengono indicate nel riepilogo dello ZIP. Il programma legge il volume Data montato sotto `/Volumes` e scrive la raccolta sull'HDD contenente il pacchetto; rifiuta una destinazione dentro Data e un'origine nel sistema Recovery. Per `--unified` verifica lo spazio per conservare cartella e ZIP, stimando due volte la dimensione dei log più un margine. Non modifica EFI, boot-args, firme o impostazioni del sistema.

## Limiti e ritorno alla prova normale

I report raccolti descrivono il sistema sul Samsung. Un normale `log show` o `sysdiagnose` eseguito in Recovery descriverebbe la Recovery in esecuzione; non viene usato come sostituto dei log del tentativo bloccato. La modalità `--unified` conserva la coppia completa in `UnifiedLogs/diagnostics` e `UnifiedLogs/uuidtext`, compresi timesync e dsc se presenti. Sono dati offline da decodificare dopo la raccolta, non un `.logarchive` già convertito. I messaggi rimasti soltanto in memoria non sono recuperabili dopo il riavvio.

Per tornare al test normale dopo la raccolta, **TEST-INTEL.cmd** rimuove nuovamente VESA dalla EFI attuale. Il suo backup resta valido se non vengono apportate altre modifiche tra ripristino e riapplicazione. Non usare il ripristino del precedente test grafico dopo la modifica Bluetooth.

La prima raccolta è stata eseguita nella Recovery reale. La modalità unificata è verificata con volumi simulati, nomi contenenti spazi, coppia diagnostics/uuidtext completa, directory mancanti, controlli dell'origine e della destinazione, spazio insufficiente e creazione dello ZIP. L'esecuzione della modalità unificata nella Recovery reale resta da ricevere.

## Fonti

- [Apple DTS: raccogliere l'intero contenuto di DiagnosticReports](https://developer.apple.com/forums/thread/763928).
- [Apple: montare un volume in Utility Disco](https://support.apple.com/guide/disk-utility/mount-a-volume-thats-been-ejected-dskutl1027/mac).
- [Apple WWDC22: log del sistema in esecuzione e archivi espliciti](https://developer.apple.com/videos/play/wwdc2022/10119/).
- [Apple WWDC16: struttura e persistenza dei log unificati](https://devstreaming-cdn.apple.com/videos/wwdc/2016/721wh2etddp4ghxhpcg/721/721_unified_logging_and_activity_tracing.pdf).
- [Mandiant: raccolta manuale di diagnostics e uuidtext per l'analisi offline](https://github.com/mandiant/macos-UnifiedLogs/blob/main/RUNNING.md).

## Esito della raccolta UN5FYU

Il volume Data è stato letto e lo ZIP contiene il vecchio panic Bluetooth, install.log e system.log. L'unico errore di copia riguarda gli attributi estesi del file panic: il contenuto è presente e leggibile. Il collector aggiornato usa `cp -RX`, che copia i dati senza attributi estesi o resource fork; non occorre ripetere questa raccolta per recuperare quel panic.

Il panic nomina bluetoothd e IntelBTPatcher 2.4, con `-igfxvesa` presente e uptime coincidente con la precedente foto. Non descrive il tentativo normale con patcher escluso e VESA assente. Non ci sono report WindowServer o Setup Assistant nello ZIP; questo non prova che tali processi funzionino.

Install.log registra `Install Succeeded`, la fine di Template Migration e la cronologia di macOS 26.7.1. In uno degli avvii Language Chooser registra `hello started`, imposta a zero l'opacità della finestra di progresso e la nasconde. Il marcatore di configurazione iniziale è assente. Sono evidenze dell'arrivo al benvenuto, senza conferma che venga disegnato o completato. Gli orologi differiscono: questi messaggi non vanno attribuiti automaticamente all'ultimo tentativo senza VESA.

La prova di avanzamento con Invio non ha avuto effetto. È stata avviata una nuova installazione da zero: attendere il completamento con la stessa EFI e IntelBTPatcher escluso. Se lo schermo nero ricompare, raccogliere i log unificati della nuova installazione con il comando sopra. Il nome del volume Data può cambiare dopo l'inizializzazione: controllarlo di nuovo in Utility Disco.

I messaggi di installazione riuscita non certificano l'integrità di ogni componente; i dati precedenti non dimostrano una corruzione. Una reinstallazione può ripristinare file danneggiati, ma un problema della EFI o della grafica potrebbe ripresentarsi. L'esito della nuova installazione resta da verificare.
