# Analisi del log OpenCore delle 02:45

**Aggiornamento successivo:** una fotografia mostra un panic USB/Bluetooth con IntelBTPatcher 2.4 nella traccia. In quella foto `-x` è assente e `-igfxvesa` è ancora presente. Per il prossimo avvio seguire la [prova Bluetooth](TEST-BLUETOOTH.md); il log analizzato qui documenta un tentativo precedente.

Log del 13 ottobre 2026, avvio iniziato alle 02:45:57. Sono riportati solo gli elementi utili alla diagnosi; il file originale e gli identificativi SMBIOS non vengono aggiunti alla repository.

## Dati confermati

| Elemento | Risultato del log | Limite della conferma |
|---|---|---|
| OpenCore | DEBUG 1.0.8; configurazione letta | Non verifica il successivo funzionamento di macOS |
| Voce selezionata | `Should boot from 4. Machintosh SSD` | Il nome non dimostra che l'installazione sia completa |
| Percorso della voce | Volume APFS su dispositivo USB esterno | Velocità del collegamento e stabilità da provare in macOS |
| Parametri diagnostici | `-igfxvesa -x` presenti in `MBA:NV` e `MBA:OUT` | Documentano questo avvio, non un eventuale tentativo dopo i ripristini |
| NVRAM boot-args | Cancellazione e impostazione: `Success` | L'esito deve essere confrontato con il log del prossimo avvio |
| Proprietà Intel | Impostazione di piattaforma e device-id: `Success` | Il log non stampa i valori e non verifica Metal |
| Lilu e WhateverGreen | Iniezione: `Success`, versioni 1.7.2 e 1.7.1 | Iniezione non equivale a inizializzazione e funzionamento nel kernel |
| AppleALC | Escluso perché il kernel è 25.6.0 | Coerente con la configurazione, che lo abilita solo su Sequoia |
| Blocco IONVMeFamily | OpenCore segnala `Success` | Il precedente rilevamento del disco interno impedisce di considerare confermata l'esclusione effettiva |
| Firmware MAT | `MAT support is 0` | Da considerare se emergono problemi del passaggio UEFI; non identifica da solo la causa degli artefatti grafici |
| Ultima riga | `EB\|LOG:EXITBS:START` alle 02:46:02 | Il log OpenCore non include WindowServer, Setup Assistant o i successivi errori di macOS |

La voce attuale è scritta **Machintosh SSD** nel menu. Nei documenti precedenti il nome era indicato come «Macintosh SSD»: va scelta la voce effettivamente presente sul disco esterno.

## Prossima prova

I due parametri erano entrambi attivi. Il percorso disponibile, con i backup creati dai test precedenti, è:

1. Da Windows, sullo stesso HDD di OpenCore, eseguire **RIPRISTINA-AVVIO.cmd**.
2. Dopo il ripristino riuscito, eseguire **RIPRISTINA-GRAFICA.cmd**.
3. Avviare nuovamente OpenCore da quell'HDD e scegliere **Machintosh SSD**.

Se è già stato applicato **TEST-INTEL.cmd**, non occorre aggiungere questa sequenza: quel test rimuove gli stessi due parametri conservando il resto della configurazione. Per annullarlo si usa il suo **RIPRISTINA-INTEL.cmd**.

Gli script di ripristino rifiutano di cancellare modifiche successive. Se un ripristino fallisce, si raccoglie il messaggio prima di procedere.

Dal prossimo avvio servono il risultato visibile e, se il problema continua, il log nuovo. Occorre verificare che `MBA:OUT` non contenga più `-x` o `-igfxvesa` prima di confrontare il comportamento della grafica normale. DVMT, framebuffer e funzionamento Metal restano da verificare.

## Immagine di sistema nel percorso di avvio

Il booter aggiunge `-bsdmgroot` da `com.apple.Boot.plist` e legge `OS.dmg.root_hash`. Nel codice XNU questo parametro è associato al tentativo di usare BaseSystem come volume radice. È un motivo ulteriore per non dedurre dal solo nome del volume che sia stato raggiunto il sistema finale. Non viene rimosso dai test: proviene dal percorso di avvio Apple, non dai due parametri diagnostici aggiunti alla EFI.

Riferimento: [Apple XNU, bsd_init.c, funzione bsdmgroot_bootable](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/bsd_init.c).

## Log successivo: 063718

È stato ricevuto `opencore-2026-10-13-063718.txt`, relativo al tentativo con la sola esclusione Bluetooth. Il file contiene 723 righe utili; il resto è spazio NUL preallocato. Il file originale e gli identificativi non vengono pubblicati.

| Dato | Risultato |
|---|---|
| Voce scelta | `Machintosh SSD`, volume APFS esterno USB |
| Boot-args in entrambe le righe `MBA:OUT` | `-igfxvesa` presente; `-x` assente |
| IntelBTPatcher | Nessuna iniezione riportata nel log, coerente con la sua esclusione |
| IntelBluetoothFirmware / BlueToolFixup | Iniezione riuscita, versioni 2.4.0 e 2.7.2 |
| Lilu / WhateverGreen | Iniezione riuscita, versioni 1.7.2 e 1.7.1 |
| Proprietà Intel | Impostazione di piattaforma e device-id riuscita; valori non stampati |
| Kernel | Darwin 25.6.0 |
| Parametro BaseSystem | `-bsdmgroot` assente dai boot-args mostrati in questo tentativo |
| Termine del log | `EXITBS:START` alle 06:37:30 secondo l'orologio del booter |

L'assenza di `-bsdmgroot` è una differenza rispetto al log precedente, non una prova del completamento dell'installazione. La lettura di `OS.dmg.root_hash` da sola non identifica un avvio BaseSystem.

Il booter mostra anche l'avviso `This system was automatically rebooted after panic` prima del nuovo passaggio al kernel. Segnala un panic rilevato prima di questo passaggio; non dimostra un nuovo panic nella successiva schermata nera. È stato riferito il raggiungimento del puntatore senza finestre.

Il prossimo passo è **TEST-INTEL.cmd sulla EFI attuale**, che rimuove soltanto i flag diagnostici eventualmente presenti e conserva IntelBTPatcher escluso. Qui ci si aspetta la rimozione di `-igfxvesa`. La prova combinata e il ripristino nell'ordine inverso sono stati verificati sulla configurazione consegnata. Non usare un vecchio ripristino integrale dopo la modifica Bluetooth.

L'assenza di accelerazione è confermata dal parametro VESA. Che sia la causa della mancata interfaccia resta da verificare con il prossimo avvio. OpenCore termina prima dei log di WindowServer: non consente di localizzare il problema dell'interfaccia o provare Metal.

## Avvio normale confermato: 103339 e 103615

Entrambi i nuovi log del 13 ottobre 2026 selezionano Machintosh SSD e mostrano boot-args senza `-igfxvesa`, `-x` o `-bsdmgroot`. IntelBTPatcher non viene iniettato; firmware Intel e BlueToolFixup restano presenti. Lilu 1.7.2 e WhateverGreen 1.7.1 sono iniettati con successo, le proprietà Intel sono impostate e il kernel letto è Darwin 25.6.0. Non sono stampati i valori del framebuffer e non è provata l'accelerazione.

Il log `103615` riporta l'assenza di un log di panic e termina a `EXITBS:START` alle 10:36:25 secondo l'orologio del booter. Non contiene i successivi log dell'interfaccia. La nuova foto mostra messaggi di macOS relativi alle firme del codice, kernelmanagerd con limite indicato come non fatale, caricamento delle collezioni di estensioni e fault di IOUserDockChannelSerial. Nessuna riga identifica da sola la causa dello stallo.

Le voci Recovery registrate sono **Recovery 26.7.1** sul Samsung e la Recovery originale dell'HDD sotto **240 GB**. La [raccolta dei report offline](DIAGNOSI-INTERFACCIA.md) legge DiagnosticReports e i log disponibili dal volume Data dell'installazione. Il ripristino del test Intel, che conserva la modifica Bluetooth, ha consentito l'accesso alla Recovery e la prima raccolta; non occorre ripeterlo se è già applicato.

## Report offline del volume Data

La raccolta `DIAGNOSI-MACOS-UN5FYU.zip` contiene il precedente panic bluetoothd/IntelBTPatcher, install.log, system.log e l'inventario APFS. La copia incompleta segnalata dal collector riguarda soltanto gli attributi estesi del panic; i byte del report sono disponibili. Il problema di copia è corretto con `cp -RX` per le raccolte successive.

Install.log riporta il successo dell'installer, il termine di Template Migration e la cronologia di macOS 26.7.1. Language Chooser avvia Hello e nasconde la finestra di progresso in uno degli avvii registrati. La configurazione iniziale non risulta conclusa. Non ci sono nuovi report WindowServer/Setup Assistant nello ZIP, né dati che provino un errore DVMT. I diversi orari dei log impediscono di assegnare tutti questi eventi alla prova normale attuale. La prova con Invio non ha avuto effetto; la [diagnosi dell'interfaccia](DIAGNOSI-INTERFACCIA.md) ora include la raccolta offline di diagnostics e uuidtext. Non ci sono ancora prove di corruzione dell'installazione né una causa identificata per lo schermo nero.
