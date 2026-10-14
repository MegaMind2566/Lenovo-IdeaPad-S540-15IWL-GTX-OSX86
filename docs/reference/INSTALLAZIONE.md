# Installazione sul Samsung 960 EVO esterno

La Recovery ha raggiunto la schermata grafica e sono stati riferiti funzionamento di mouse, tastiera, Wi-Fi e rilevamento del 960 EVO. Il modulo M.2 nel box era sganciato ed è stato reinserito. Per l'installazione mantieni porta e cavo con cui il disco ora viene rilevato.

Nella prova del 13 ottobre 2026 l'installer mostra **macOS Tahoe** e la destinazione **Macintosh SSD**. L'installazione è già in corso: le istruzioni di inizializzazione qui sotto servono per una nuova preparazione, non vanno ripetute durante questa prova.

## Inizializzazione e avvio dell'installazione

1. Nella schermata delle Utility verifica che la voce dell'installer indichi macOS Tahoe. Se riporta un'altra versione, raccogli il nome della versione prima di procedere.
2. Apri Utility Disco e scegli Vista → Mostra tutti i dispositivi.
3. Seleziona il dispositivo fisico esterno che contiene il 960 EVO, al livello superiore della sua gerarchia.
4. Premi Inizializza. Imposta nome **macOS**, formato **APFS** e schema **Mappa partizione GUID**. Questo passaggio cancella i dati sul 960 EVO scelto.
5. Chiudi Utility Disco, scegli **Reinstalla macOS Tahoe** e indica **macOS** come destinazione.
6. Mantieni l'alimentatore collegato e lascia collegati HDD di avvio e SSD esterno. Attendi download e installazione.

## Riavvii

L'installazione può riavviare il computer più volte. Ogni volta usa OpenCore dall'HDD di avvio già preparato. Quando compare **macOS Installer**, scegli quella voce per continuare. Al termine scegli il volume con il nome assegnato: **Macintosh SSD** nella prova attuale, **macOS** nell'esempio di preparazione. Non ripartire dalla Recovery a ogni riavvio.

Se le voci del menu sono diverse o l'installer mostra un errore, raccogli una foto leggibile prima di cambiare la configurazione. Non rimuovere i dischi durante l'installazione.

## Dopo il primo desktop

Mantieni la EFI attuale durante l'installazione. L'eventuale opzione di test `-igfxvesa` è temporanea: il raggiungimento della Recovery non conferma l'accelerazione Intel. Dopo il primo desktop segui la [verifica Intel](../guides/GRAFICA-INTEL.md), poi le prove nella [roadmap hardware](../status/ROADMAP.md). OpenCore resterà inizialmente sull'HDD di avvio; il trasferimento della EFI sull'SSD esterno verrà eseguito dopo la prova del sistema installato.

Il disco Windows interno rimane al suo posto, secondo la preferenza espressa. Il rilevamento nella Recovery non conferma l'efficacia del blocco NVMe della configurazione iniziale né la stabilità sotto carico.

## Riferimenti

- [Apple: inizializzare un dispositivo con Utility Disco](https://support.apple.com/en-gb/guide/disk-utility/dskutl14079/mac)
- [Apple: reinstallare macOS dalla Recovery](https://support.apple.com/en-ie/102655)
- [Dortania: processo di installazione con OpenCore](https://dortania.github.io/OpenCore-Install-Guide/installation/installation-process.html)
