# Prova della regolazione microfono

Il report a ingresso 30% e 70% conferma che il driver attuale cambia tutti i mixer, compresi quelli di uscita, mentre macOS continua a mostrare il volume altoparlanti a 100. Il codec ALC257 ha un boost microfono con quattro livelli da 0 a 30 dB e un amplificatore ADC con 64 livelli, da -17,25 a +30 dB, in passi da 0,75 dB. La combinazione dei controlli produce i salti percepiti.

Questa prova usa VoodooHDA **3.6.9, variante S540**, compilato dal sorgente 3.6.8 fissato. Non è una release ufficiale upstream. Il cursore ingresso usa l'ADC; il boost dei pin microfono interno e jack resta a 0 dB. La correzione PCM del volume altoparlanti resta attiva e i due cursori sono separati. Equalizzazione, tasti funzione e sospensione restano lavori successivi.

La correzione è attiva solo con controller Intel 8086:9dc8, codec Realtek 10ec:0257 e i controlli osservati sul portatile. Se il grafo differisce, il driver conserva l'algoritmo originale e la verifica segnala che la prova non è attiva. La registrazione dal jack resta da provare sul portatile.

## Installazione dal desktop Tahoe

La versione v2 controlla l'intestazione Intel del driver con utility di sistema. Non richiede Xcode o Command Line Tools; mantiene i controlli di integrità e firma della v1.

Estrarre **S540-microfono-fix-v2.zip** in Download. Tenere il disco **240 GB** collegato e montato. Conservare anche una copia dell'intera cartella `S540-microfono-fix-v2` sul disco 240 GB, per avere il comando di ripristino disponibile dalla Recovery.

```sh
bash "$HOME/Downloads/S540-microfono-fix-v2/INSTALLA-MICROFONO.command"
```

Il comando controlla la variante V3 attuale, il nuovo driver e i simboli disponibili nel kernel Tahoe. Poi salva il driver funzionante byte per byte, sostituisce il bundle e richiede la ricostruzione della collezione ausiliaria. Chiede la password amministratore nel Terminale. Se macOS richiede l'approvazione, seguire il messaggio in Privacy e sicurezza e ripetere il comando quando indicato. Riavviare soltanto quando il comando lo richiede.

Il backup privato è sul volume Data, in `/Library/Application Support/S540-microfono`, con proprietà root e permessi 700. Conservarlo. Non vengono modificati config, SIP, NVRAM, AMFI o volume di sistema sigillato. Il parametro `-igfxblr` resta nel config.

## Verifica dopo il riavvio

```sh
bash "$HOME/Downloads/S540-microfono-fix-v2/VERIFICA-MICROFONO.command"
```

La verifica richiede versione 3.6.9 caricata, `S540InputGainFixActive=true` e due controlli di ingresso con scala esatta -17,25/+30 dB. Questi controlli dimostrano che la variante è attiva, non ancora la qualità della registrazione.

Se passa, scegliere il microfono interno in Suono/Ingresso. Partire dal 50%, registrare la stessa frase e regolare poco alla volta. Controllare anche volume e muto degli altoparlanti e dei tasti F1-F3. Riferire se il guadagno cambia in modo graduale e se compaiono distorsione o rumore.

## Annullamento dal desktop

```sh
bash "$HOME/Downloads/S540-microfono-fix-v2/ANNULLA-MICROFONO.command"
```

Il comando riconosce il driver della prova, ripristina esattamente la V3 salvata e richiede la ricostruzione AuxKC. Seguono il riavvio e lo stesso comando VERIFICA. Il ripristino non dipende dall'hash del config corrente e preserva anche successive modifiche alla EFI. Per annullare questa prova usare questo pacchetto: il vecchio programma audio non riconosce il nuovo binario 3.6.9.

## Ripristino dalla Recovery

Se il desktop non si avvia, avviare la Recovery con la configurazione che già funziona. In Utility Disco montare i volumi System e Data del Samsung. Se i nomi coincidono con quelli qui indicati e la cartella del pacchetto è stata copiata sul 240 GB:

```sh
bash "/Volumes/240 GB/S540-microfono-fix-v2/ANNULLA-MICROFONO.command" --recovery-data "/Volumes/Macintosh SSD - Data" --recovery-system "/Volumes/Macintosh SSD"
```

Il comando controlla l'UUID Data registrato nel backup. Se il sistema espone anche il gruppo APFS comune ai due volumi, tenta la ricostruzione AuxKC sul System corrispondente. Se questa prova manca, oppure serve un'approvazione indisponibile dalla Recovery, ripristina i file ma lascia `restorepending`: la ricostruzione non è completata e va verificata prima del riavvio. Non forza la ricostruzione delle collezioni Boot/System e non cancella le approvazioni degli altri kext.

La procedura Recovery non è stata eseguita sul portatile. Errori di utility mancanti o volumi non riconosciuti vengono segnalati; conservare il messaggio.

## Verifiche del pacchetto

La CI applica la patch al sorgente fissato e compila per Intel con MacKernelSDK fissato. Verifica formato MH_KEXT_BUNDLE, architettura, firma ad hoc, versione e manifest dei tre file. I test eseguono le funzioni effettive della patch con sanitizzatori e controllano scala, 64 livelli, mute, separazione ingresso/uscita, ripristino dei mixer e fallback. Le fixture dell'installer verificano anche il lettore nativo dell'intestazione, rifiutando binari ARM, universali, di altro tipo e intestazioni tronche; simulano interruzioni dei rename, manifest e permessi errati, ripristino V3 e indipendenza dal config. La CI non carica il driver nel kernel; il funzionamento hardware resta da verificare con la prova descritta sopra.

## Sorgenti

- [VoodooHDA fissato](https://github.com/CloverHackyColor/VoodooHDA/tree/8c7e8e2ce6de0a917be663a3192857955288c937).
- [MacKernelSDK fissato](https://github.com/joevt/MacKernelSDK/tree/bfbfbe4cf35979f33ded6c7a8761eb1df091fb39).
- [Manuale Apple di kmutil](https://keith.github.io/xcode-man-pages/kmutil.8.html).
