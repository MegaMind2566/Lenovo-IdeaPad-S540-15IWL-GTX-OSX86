# Recuperare i dati dell'avvio normale bloccato

Il controllo della EFI è completato e non ha individuato un difetto di struttura. L'obiettivo resta raggiungere l'interfaccia e verificare Intel. I log OpenCore disponibili terminano prima degli eventi del sistema; l'unico archivio unificato decodificato descriveva avvii VESA. Ora occorrono gli eventi persistiti dell'avvio normale già tentato sul Samsung. Il riordino del supporto non è un prerequisito: i vecchi log sono già stati eliminati direttamente.

Il pacchetto **S540-recupero-avvio-normale.zip** prepara temporaneamente l'accesso Recovery e raccoglie quei dati. Non chiede di ripetere il tentativo normale bloccato prima della raccolta.

## Passaggi

1. Da Windows estrarre il contenuto del pacchetto nella radice dell'HDD di OpenCore, accanto a EFI. Accettare la sostituzione del launcher RACCOGLI-UNIFIED.command e della cartella diagnosi-unified precedenti. Devono essere nello stesso livello di EFI anche PREPARA-RECOVERY-LOG.cmd e RIPRISTINA-PROVA-INTEL.cmd.
2. Aprire **PREPARA-RECOVERY-LOG.cmd**. Aggiunge soltanto -igfxvesa ai boot-args del config corrente. Conserva esattamente il file precedente in EFI/OC/config.before-runtime-logs.plist. Le proprietà Intel, l'identità, i kext e tutte le altre impostazioni sono conservati; IntelBTPatcher deve essere già escluso. Non usa i vecchi backup dell'intera EFI.
3. Avviare lo stesso OpenCore e scegliere **Recovery 26.7.1**; è disponibile anche la Recovery originale dell'HDD con nome **240 GB**, già usata. L'accesso Recovery era stato verificato con VESA e IntelBTPatcher escluso; la preparazione conserva le altre impostazioni attuali.
4. In Utility Disco mostrare tutti i dispositivi, individuare il Samsung esterno e montare **Machintosh SSD - Data**. Aprire Utility → Terminale ed eseguire il comando seguente.

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command"
```

5. Attendere il percorso **DIAGNOSI-MACOS-….zip** stampato sullo schermo. Tornare in Windows e allegare quel file ZIP. È la raccolta del sistema sul Samsung, con dati sufficienti a separare i diversi avvii; non occorre una fotografia del blocco.

Il launcher deve mostrare **Raccolta unificata v4: dati del sistema installato**. Se il nome del Data è cambiato, il percorso può essere passato come unico argomento. Il collector conserva la coppia completa diagnostics/uuidtext, inclusi timesync e dsc presenti, senza filtro per data o estensione. Con strumenti du/df/awk mancanti la stima dello spazio è opzionale e la copia prosegue. Le copie incomplete vengono segnalate nel riepilogo.

## Config associato alla prova

Quando trova il backup dedicato, la v4 include nel report **config-avvio-normale.plist**, identico al backup prima di aggiungere VESA, e **config-recovery.plist**. Questi file restano privati nello ZIP e non vengono pubblicati nel repository. Servono a leggere i valori Intel esatti e a distinguere lo stato del test da quello necessario alla lettura in Recovery. Il collector non modifica nessuno dei due file.

Il fatto di avviare Recovery in VESA non cambia retroattivamente gli eventi dell'avvio normale salvati sul Data. Il confronto successivo va fatto per avvio, orario e boot-args effettivi. Non si usa il log della Recovery in esecuzione per giudicare l'accelerazione del sistema installato.

## Ripristino

Dopo la raccolta, da Windows **RIPRISTINA-PROVA-INTEL.cmd** ripristina byte per byte il config precedente, mantenendo la stessa identità e la modifica Bluetooth. Il backup resta conservato. Se esistono modifiche successive non compatibili con la preparazione, il programma rifiuta il ripristino automatico anziché sovrascriverle. Anche la preparazione rifiuta un backup di un altro stato, oppure VESA già presente senza il backup dedicato; in quei casi conservare il messaggio completo.

## Verifica e limiti

La preparazione e il ripristino sono controllati con il config reale della prova, in cartelle temporanee: cambia solo boot-args, l'identità e le proprietà Intel sono conservati, il backup è identico, le ripetizioni sono gestite e i conflitti non modificano il config. Il collector è controllato con volumi simulati, copie binarie, strumenti assenti, sorgenti non valide e confronto del contenuto sorgente prima e dopo. Le copie dei due config sono byte per byte identiche e i file originali restano invariati. La parte Windows dei launcher non è stata eseguita su questo host Linux.

La raccolta e l'avvio Recovery sul portatile restano da effettuare. I messaggi presenti soltanto in memoria nel momento del riavvio possono mancare. Se la raccolta non contiene eventi dell'avvio normale, servirà una diagnosi con registrazione dedicata, da scegliere dopo avere verificato i dati effettivamente disponibili. La preparazione Recovery è uno strumento diagnostico, non una correzione della grafica.

