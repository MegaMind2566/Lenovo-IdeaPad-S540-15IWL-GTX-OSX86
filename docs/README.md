# Guide del progetto

Lo stato corrente è nel [README principale](../README.md). Questo indice distingue le procedure ancora utili dalla ricostruzione delle diagnosi precedenti.

## Stato e procedure attuali

| Guida | Scopo |
|---|---|
| [Hardware](HARDWARE.md) | Identificativi ed esiti sul portatile, con limiti delle prove |
| [Roadmap](ROADMAP.md) | Componenti aperti, priorità e criteri di verifica |
| [Grafica Intel](GRAFICA-INTEL.md) | Accelerazione Intel e prove di stabilità |
| [Avvio e rete](AVVIO-RETE.md) | Correzione `-igfxblr`, Wi-Fi con HeliPort e Bluetooth |
| [Audio Tahoe](AUDIO-TAHOE.md) | Preparazione iniziale, volume e ripristino VoodooHDA |
| [Microfono v2](MICROFONO-FIX.md) | Variante S540 3.6.9, verifica dopo riavvio e ripristino del driver precedente |
| [Mappatura USB](MAPPATURA-USB.md) | Porte rilevate e prove mancanti |
| [Batteria e sospensione](BATTERIA-SOSPENSIONE.md) | Campioni archiviati e verifiche rinviate |
| [Riordino del supporto di avvio](RIORDINO-AVVIO.md) | Manutenzione separata del disco; il riordino della repository non modifica il supporto |

## Basi tecniche e prima installazione

- [Analisi ACPI](ANALISI-ACPI.md), [verifica patch ACPI](VERIFICA-PATCH-ACPI.md) e [verifica della consegna EFI iniziale](VERIFICA-EFI.md).
- [Installazione sul disco esterno](INSTALLAZIONE.md) e [istruzioni della EFI iniziale](PRIMO-AVVIO.md): descrivono la fase iniziale, precedente alla configurazione funzionante.
- [Raccolta microfono](MICROFONO.md): procedura per VoodooHDA 3.6.8 precedente alla correzione. Il controllo del driver rifiuta la variante 3.6.9; non è la verifica della v2.

## Diagnosi precedenti

Le vecchie prove grafiche, le tracce Intel e le raccolte Recovery sono nell'[archivio](../archive/README.md), insieme a sorgenti, licenze e spiegazione delle dipendenze. Gli esiti utili restano collegati allo stato hardware corrente.
