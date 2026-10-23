# S540: prova di prima inizializzazione con risorse trattenute

Questo pacchetto esegue una sola richiesta manuale di prima inizializzazione RM/GSP sul Lenovo IdeaPad S540 con GPU NVIDIA 10DE:1F91, subsystem 17AA:3806, revisione A1. Richiede Intel macOS build **25G241**, Darwin **25.6.0**, e la capacità reale letta da `kern.stack_size`. Il client confronta sorgenti, policy e contratto del codice nativo con il modulo effettivamente caricato.

Estrai lo ZIP in una cartella temporanea nuova. Esegui `test-retained-first-initialization.sh` con `sudo`, l'hash di `packaging-attestation.json` pubblicato separatamente e `--ack-retained-first-initialization`. Usa una cartella nuova sul Desktop come `--output`. Il comando completo viene fornito insieme al pacchetto verificato.

La richiesta avvia una prova sperimentale; **dopo il tentativo modulo, proprietario e provider PCI restano trattenuti fino al riavvio**. Le risorse visibili al codice originale o di cui non è dimostrato l'arresto restano trattenute. È consentita solo la pulizia verificata prima dell'ingresso originale, seguendo il protocollo reale di arresto. Il client chiede un arresto reale e registra separatamente inizializzazione, cancellazione e fasi di arresto. Un errore non dimostra che l'ingresso originale non sia iniziato. Salva il report e riavvia prima di un altro tentativo; evita lo scaricamento forzato del modulo. Se il sistema si blocca, il riavvio termina la prova.

Mentre la prima richiesta è in corso, un'altra connessione amministrativa può leggere `experimental_ctl --snapshot` oppure chiedere `experimental_ctl --stop`. La lettura non consuma la richiesta e non cancella la prova. Sono ammesse al massimo 16 connessioni amministrative; il blocco di prima inizializzazione resta utilizzabile una sola volta per avvio.

Il report distingue caricamento del kernel, richiesta di inizializzazione, ritorno originale e arresto. Un caricamento riuscito non dimostra inizializzazione della GPU; un'inizializzazione riuscita non dimostra accelerazione grafica. Le riserve di stack e la capacità IRQ sono ipotesi esplicite di questa prova. Il pacchetto non certifica il limite completo di stack, l'arresto DMA, le scadenze PM o un driver pronto per l'uso ordinario.

Il payload viene copiato nel report con proprietà `root:wheel`; lo script non modifica EFI o impostazioni di sicurezza. `corresponding-source.zip` contiene i sorgenti effettivi, la ricetta, le trasformazioni e le dipendenze SDK con i relativi avvisi. La licenza NVIDIA del firmware è inclusa nelle risorse del bundle.
