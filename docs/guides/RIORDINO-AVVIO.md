# Riordinare l'HDD di OpenCore

Il riordino conserva i file di avvio attuali e archivia sul Desktop di Windows le vecchie prove riconoscibili del progetto. Il controllo completo della consegna e dei config è riportato in [VERIFICA-EFI.md](../reference/VERIFICA-EFI.md). Non è una nuova prova del framebuffer e non sostituisce la EFI.

## Uso

1. Estrarre **S540-riordino-avvio.zip** nella radice dell'HDD di OpenCore, accanto a EFI e ai file Recovery. Non avviare il comando dentro lo ZIP. Accettare la sostituzione del collector unificato precedente: quello incluso è la v3, già verificata senza du.
2. Da Windows premere due volte **RIORDINA-AVVIO.cmd**. Usa Python 3, già utilizzato per la Recovery; non serve installare un altro programma né usare un Terminale.
3. Attendere le copie e i controlli. La cartella **S540-archivio-avvio-DATA-ORA-…** viene creata sul Desktop. Per ogni voce il programma confronta file, dimensioni e SHA-256 prima di rimuovere i dati verificati dall'HDD. In caso di errore conservare l'archivio e le eventuali voci rimaste.
4. Nell'archivio leggere **RAPPORTO.json** e **RIPRISTINO.txt**. Il rapporto elenca i file spostati, gli errori e ciò che resta nella radice. Allegare RAPPORTO.json per verificare anche le voci residue senza ricopiare la EFI.

Il programma accetta solo la radice del disco che contiene EFI/BOOT/BOOTx64.efi e EFI/OC/config.plist, rifiuta una radice con Windows o Users e richiede che il Desktop si trovi su un altro volume. Non richiede amministratore, non scarica nulla e non invia il rapporto automaticamente.

## File archiviati

Le regole riguardano solo le seguenti voci nella radice del disco:

- Log con nome opencore-AAAA-MM-GG-HHMMSS.txt.
- Cartelle DIAGNOSI-MACOS- e LOG-UNIFICATI- con il suffisso di sei caratteri dei raccoglitori, e gli ZIP corrispondenti.
- Vecchi pacchetti ZIP S540-test- e S540-diagnosi-, e lo ZIP della prima prova S540-81SW-Tahoe-prima-prova.zip.
- I vecchi comandi TEST-INTEL, TEST-BT, TEST-GRAFICA, AVVIO-SICURO e i relativi ripristini elencati dal programma.
- Il vecchio launcher RACCOGLI-LOG-MACOS.command.

Tutta la EFI attuale, inclusi config e backup dentro EFI/OC, resta al suo posto. Restano i file Recovery, i contenuti di tools, il launcher RACCOGLI-UNIFIED.command e la cartella diagnosi-unified. I file non riconosciuti vengono conservati ed elencati. I collegamenti e i reparse point non vengono seguiti o archiviati automaticamente.

## Ripristino

Copiare una voce archiviata dal Desktop nella radice dello stesso HDD. Se esiste già una voce con quel nome, confrontare le due copie prima di sovrascriverla. La cartella sul Desktop conserva la struttura interna delle raccolte e un manifesto di hash per ogni voce spostata con successo. In caso di una copia interrotta o di un errore successivo verificare sia il contenuto dell'archivio sia quello rimasto sull'HDD: i file già trasferiti rimangono recuperabili nell'archivio.

## Collector corrente

Il pacchetto contiene anche il collector unificato v3 già disponibile. Dal Terminale della Recovery, con il volume Data del Samsung montato, il comando è:

```bash
bash "/Volumes/240 GB/RACCOGLI-UNIFIED.command"
```

L'avvio dell'interfaccia Recovery era stato verificato con VESA temporaneo e IntelBTPatcher escluso. Il riordino non modifica questi parametri e non certifica che la Recovery si apra con il profilo attuale. I dati da analizzare per lo stallo sono quelli persistiti sul Data del Samsung, non i log della Recovery in esecuzione.

## Verifiche del programma

La procedura di spostamento viene controllata con cartelle simulate: conservazione di EFI/Recovery e file sconosciuti, archiviazione dei soli nomi previsti, hash della copia, cartelle vuote, errori di copia e collegamenti. Queste prove non sono un'esecuzione sul disco Windows del portatile: l'esito fisico sarà documentato da RAPPORTO.json.

