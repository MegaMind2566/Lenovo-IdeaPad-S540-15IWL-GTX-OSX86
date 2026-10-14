# Archivio delle prove precedenti

Questo archivio conserva i sorgenti delle prove usate prima del desktop funzionante. I file sono stati spostati, senza duplicare pacchetti o cancellare diagnosi. La [documentazione corrente](../docs/README.md) indica le procedure ancora utili.

| Gruppo | Contenuto | Esito e percorso attuale |
|---|---|---|
| [EFI iniziale](efi-iniziale/) | Builder e workflow della prima configurazione OpenCore | Modello di riferimento precedente alle correzioni Intel, audio e pannello; non riproduce la EFI privata funzionante |
| [Primo avvio](primo-avvio/) | Prove VESA, avvio sicuro, Whiskey Lake, memoria Intel, tracce e raccolte Recovery | Il desktop è stato raggiunto dopo la correzione della memoria; la configurazione corrente è descritta in [Grafica Intel](../docs/GRAFICA-INTEL.md) |
| [Licenze delle tracce](primo-avvio/licenses/intel-trace/) | Licenze dei componenti usati dalle build diagnostiche | Conservate insieme a builder e lock degli asset |

## Consultare la diagnosi

- [Correzione memoria Intel](primo-avvio/docs/TEST-MEMORIA-INTEL.md).
- [Traccia Intel](primo-avvio/docs/TRACCIA-INTEL.md).
- [Analisi dei log di avvio](primo-avvio/docs/ANALISI-LOG-AVVIO.md).
- [Analisi dei log unificati](primo-avvio/docs/ANALISI-LOG-UNIFICATI.md).
- [Raccolta dalla Recovery](primo-avvio/docs/DIAGNOSI-INTERFACCIA.md).

Le altre guide e i launcher originali sono nel gruppo `primo-avvio`. Sono procedure storiche: il loro contesto, i nomi dei pacchetti e i controlli del driver riflettono quella fase del lavoro.

## Dipendenze e ripristino dei sorgenti

Le prove memoria e traccia condividono `tools/trace_intel.py`. I builder diagnostici conservano la struttura interna `tools`, `docs`, `profiles` e `licenses`, così i pacchetti generati mantengono i propri percorsi. Il builder EFI iniziale usa ancora ACPI, USB e profilo hardware condivisi alla radice della repository.

I workflow qui conservati non vengono eseguiti automaticamente da GitHub Actions. Alcuni launcher sono sorgenti copiati alla radice dei vecchi pacchetti e non vanno eseguiti direttamente dalla loro cartella `tools`. La raccolta unificata originale dipende inoltre dal layout del vecchio pacchetto `diagnosi-unified`; resta come riferimento, non come procedura corrente.

Il [manifest degli spostamenti](manifest.json) registra il percorso precedente, quello nuovo, le impronte SHA-256 e il commit d'origine. La cronologia Git conserva le versioni anteriori al riordino. La EFI reale e i backup presenti sul portatile non vengono modificati da questo archivio.
