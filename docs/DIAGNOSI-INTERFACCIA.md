# Raccolta dei report dall'installazione senza interfaccia

**Raccolta unificata ricevuta:** lo ZIP LOG-UNIFICATI-e8VM9n è stato decodificato. Entrambi gli avvii usano VESA; nel secondo il benvenuto registra un errore di creazione della texture. La [nuova analisi](ANALISI-LOG-UNIFICATI.md) descrive i dati e la prossima prova con TEST-INTEL.cmd.

I log `opencore-2026-10-13-103339.txt` e `opencore-2026-10-13-103615.txt` confermano l'assenza di `-igfxvesa` e `-x`. IntelBTPatcher non viene iniettato; Lilu e WhateverGreen risultano iniettati con successo. Questo non dimostra che la grafica si inizializzi o che Metal funzioni. Il log termina al passaggio al kernel, prima degli eventi dell'interfaccia.

La nuova fotografia mostra servizi di macOS e caricamento delle collezioni di estensioni, senza una riga di panic. Contiene errori di firma del codice, un limite di memoria esplicitamente non fatale di kernelmanagerd e fault ripetuti di IOUserDockChannelSerial. Nessuna di queste righe identifica da sola la causa del mancato desktop.

La prima raccolta non contiene nuovi report che spieghino lo schermo nero. Anche Invio, nella prova con la configurazione che ha aperto la Recovery, non ha fatto comparire il benvenuto. Ora la stessa raccolta offre `--unified`: oltre a DiagnosticReports e install.log/system.log, copia interamente `private/var/db/diagnostics` e `private/var/db/uuidtext` dal volume Data del Samsung. Non filtra per data o estensione. L'assenza di un report non esclude un processo bloccato o mai avviato.

## Passaggi

1. In Windows estrai **S540-diagnosi-unified-v3.zip** nella radice dell'HDD di OpenCore. Accetta la sostituzione dei file v2. Devono risultare `RACCOGLI-UNIFIED.command` e la cartella `diagnosi-unified` accanto a `EFI`. Il pacchetto contiene il collector aggiornato nella nuova cartella; la modalità unificata è già attiva nel launcher.
2. Conserva la configurazione che ha aperto la Recovery: VESA temporaneo e IntelBTPatcher escluso. Se sei tornato alla prova Intel normale, sullo stesso HDD esegui **RIPRISTINA-INTEL.cmd**. Non ripeterlo se il ripristino è già stato applicato. Se segnala backup mancante o modifiche successive, conserva l'errore senza sostituire il config.
3. Avvia lo stesso OpenCore e scegli **Recovery 26.7.1**, presente nel menu registrato dai nuovi log. Serve la Recovery per leggere i report salvati sul Samsung. Se questa voce non apre le Utility, è presente anche la Recovery originale dell'HDD sotto il nome **240 GB**; seleziona la voce con l'icona Recovery.
4. In **Utility Disco → Vista → Mostra tutti i dispositivi**, individua il Samsung esterno e il suo volume **Data/Dati**. Montalo se necessario. Il nome atteso è **Machintosh SSD - Data**; verifica che sia il volume Data del Samsung, della stessa installazione di Machintosh SSD.
5. Apri **Utility → Terminale** dal menu superiore ed esegui:

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command"
```

6. Attendi la copia e la creazione dello ZIP; i log unificati possono occupare molto più spazio della prima raccolta. Il programma stampa il percorso di **DIAGNOSI-MACOS-….zip**, salvato sull'HDD di OpenCore. Torna in Windows e allega quello ZIP.

Il programma riconosce automaticamente i nomi `Machintosh SSD - Data` e `Machintosh SSD - Dati`, solo se trova la struttura prevista di un volume Data. Questi controlli non verificano il gruppo APFS: la scelta del Samsung va controllata in Utility Disco. Non monta o sblocca volumi automaticamente. Se il nome è diverso, usa il percorso esatto come argomento, per esempio:

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command" "/Volumes/NOME ESATTO DEL VOLUME DATA"
```

Il comando usa il percorso preciso dell'HDD già osservato, `240 GB`. Se cambia il nome dell'HDD, sostituiscilo con quello presente in `/Volumes`. Evita il wildcard del launcher quando ci sono più copie su dischi diversi: diventerebbero argomenti aggiuntivi. Se la raccolta si ferma, fotografa il messaggio del Terminale. Le copie incomplete vengono indicate nel riepilogo dello ZIP. Il programma legge il volume Data montato sotto `/Volumes` e scrive la raccolta sull'HDD contenente il pacchetto; rifiuta una destinazione dentro Data e un'origine nel sistema Recovery. Per `--unified`, se du/df/awk sono disponibili, verifica lo spazio per conservare cartella e ZIP, stimando due volte la dimensione dei log più un margine. Se uno di questi strumenti manca, prosegue con la copia e registra che lo spazio non è stato stimato. Non modifica EFI, boot-args, firme o impostazioni del sistema.

All'avvio deve comparire **Raccolta unificata v3: diagnostics + uuidtext**. La sequenza precedente (errore sul volume con `--unified` da solo, seguito da "Indica al massimo il percorso del volume Data" aggiungendo il percorso) è compatibile con il vecchio collector, che accetta un solo argomento e non riconosce l'opzione. Non identifica un problema del disco. Le fotografie dei controlli confermano la presenza di Library, Users e private/var nel Data; i due primi controlli manuali avevano errori nel percorso. Il nome distinto del launcher e la cartella separata consentono di usare la versione aggiornata senza dipendere dal vecchio script in tools.

Il launcher v2 è stato avviato nella Recovery reale, dove `du` risulta assente. Il controllo obbligatorio della dimensione ha quindi fermato la raccolta prima della copia. La v3 rende opzionale la stima quando mancano gli strumenti, mantenendo attive entrambe le copie di diagnostics e uuidtext. La disponibilità di du nel sistema completo non ne dimostra la presenza nella Recovery.

## Copia diretta dalla Recovery già aperta

Se il raccoglitore v2 si è fermato per l'assenza di du, si può raccogliere direttamente la coppia di dati offline con i comandi seguenti. In questa sessione l'HDD è `240 GB` e il wildcard del Data corrisponde soltanto a Machintosh SSD - Data. Se ci sono più volumi Data con SSD nel nome, indicare il percorso esatto al posto del wildcard.

```bash
log_output=$(mktemp -d "/Volumes/240 GB/LOG-UNIFICATI-XXXXXX") &&
cp -RX /Volumes/*SSD*Data/private/var/db/{diagnostics,uuidtext} "$log_output/" &&
ditto -c -k "$log_output" "$log_output.zip" &&
printf '%s\n' "$log_output.zip"
```

Le righe terminano con `&&` per proseguire solo dopo il successo del comando precedente. Copiano le due directory complete dal Data e producono sull'HDD un ZIP chiamato LOG-UNIFICATI-….zip, mantenendo la cartella. Questa raccolta diretta contiene solo diagnostics e uuidtext: non include i report aggiuntivi del collector, non esegue una stima dello spazio e non converte i dati in un logarchive. Se la copia si ferma, conservare il messaggio e la cartella; non procedere alla compressione di una copia segnalata come incompleta.

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

## Esito della nuova installazione

Anche dopo la nuova installazione da zero viene riferito lo schermo nero. Questo esito non identifica da solo la causa e non prova l'integrità di ogni file. La raccolta `--unified` va ora eseguita sul volume Data della nuova installazione, verificandone il nome in Utility Disco. I report precedenti restano riferiti all'installazione precedente; attendiamo il nuovo ZIP prima di scegliere altre modifiche alla EFI.
