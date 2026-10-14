# Traccia diretta dell'avvio Intel

Il controllo delle patch e della DSDT non ha individuato una correzione dimostrata. I nuovi avvii non hanno eventi unificati persistiti. Questo pacchetto abilita una traccia diretta di Lilu/WhateverGreen, conservando le proprietà grafiche della EFI attuale: non ripete le precedenti prove cambiando il framebuffer.

## Uso

1. Da Windows estrarre **S540-traccia-Intel.zip** nella radice dell'HDD OpenCore, accanto alla cartella EFI. Non copiarlo sul Samsung o sul disco Windows. Accettare la sostituzione del collector se esiste già.
2. Eseguire **TRACCIA-INTEL.cmd** e verificare il messaggio di attivazione. Il programma salva il config e i due kext attuali in `EFI/OC/backup-traccia-intel`.
3. Avviare dallo stesso OpenCore e scegliere **Machintosh SSD**, il sistema installato. Lasciare il tentativo in esecuzione almeno **due minuti**, anche se il testo o il puntatore sembrano fermi: Lilu tenta di salvare il proprio buffer dopo 60 secondi.
4. Se l'interfaccia non parte, tornare in Windows ed eseguire **RECOVERY-TRACCIA-INTEL.cmd**. Questo prepara VESA per la Recovery e disattiva i dump automatici in quella modalità.
5. Avviare la Recovery. Montare il volume **Machintosh SSD - Data** in Utility Disco e aprire Terminale. Eseguire:

```bash
bash "/Volumes/240 GB/RACCOGLI-INTEL.command"
```

Se il nome dell'HDD è diverso, sostituire soltanto `240 GB`. Se il volume Data ha un altro nome, passarlo come unico argomento aggiuntivo, racchiuso fra virgolette.

6. Tornare in Windows e allegare lo ZIP DIAGNOSI-MACOS indicato dal comando. Contiene dati privati della configurazione: condividerlo nella chat, senza pubblicarlo nella repository.
7. Per tornare esattamente ai file precedenti alla traccia, eseguire **RIPRISTINA-TRACCIA-INTEL.cmd**. Non cancellare il backup prima del ripristino. Il programma rifiuta il ripristino automatico se nel frattempo rileva altre modifiche ai file interessati.

## Modifiche temporanee e dati raccolti

Lilu 1.7.2 e WhateverGreen 1.7.1 vengono sostituiti con le rispettive build ufficiali DEBUG. I boot-args della prova includono `-liludbgall -wegdbg liludump=60 -igfxdump`; VESA e modalità sicura vengono rimossi dalla prova normale. Gli altri valori del config restano uguali, compresa la coppia Intel corrente. IntelBTPatcher deve essere già disabilitato. Il programma non cambia SSDT, mappa USB, Wi-Fi, identità SMBIOS o disco Windows.

Il collector legge dal Data installato i file `private/var/log/Lilu_*.txt` e `AppleIntelFramebuffer_*`, i report disponibili e il backup con i config esatti della traccia. Non ricopia diagnostics/uuidtext. Il riepilogo registra anche l'assenza dei file: se il kernel o il filesystem non arrivano al punto di scrittura, il dump potrebbe non esistere. Una traccia vuota non certifica il funzionamento della GPU.

Il file Lilu può riportare proprietà e inizializzazione del driver; il dump framebuffer permette di verificare la tabella effettivamente caricata. Non è garantito che ogni errore o il DVMT del firmware venga stampato. Le build DEBUG possono rallentare l'avvio: vengono usate soltanto per la diagnosi.

I due ZIP ufficiali sono verificati con SHA-256, e il payload applicato ha un manifest per ogni file. Le licenze sono incluse. Il builder riproducibile è `tools/build_intel_trace.py`; non include config o dati personali nello ZIP distribuito.

Il controller è stato verificato con nove gruppi di prove su backup, alterazioni, ripristino e guasti durante la sostituzione. Una prova separata sulla copia della EFI effettivamente consegnata e del config Whiskey Lake ha ripristinato byte per byte tutti i 55 file iniziali; i config normale e Recovery della traccia superano ocvalidate 1.0.8. Il collector conserva esattamente i file di prova e registra la loro assenza. Le prove sono state eseguite in Linux: i launcher Windows e l'avvio fisico con le build DEBUG restano da eseguire sul portatile.

## Fonti

- [Lilu 1.7.2, flag di debug e liludump](https://github.com/acidanthera/Lilu/blob/1.7.2/README.md).
- [WhateverGreen 1.7.1, wegdbg e igfxdump](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md).
- [Verifica delle patch ACPI](../../../docs/VERIFICA-PATCH-ACPI.md).
