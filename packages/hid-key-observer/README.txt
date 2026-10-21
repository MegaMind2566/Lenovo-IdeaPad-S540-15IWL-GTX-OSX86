S540 HID Keys: observer 1.0.1

Questo pacchetto osserva i valori HID pubblicati da macOS dopo l'elaborazione
del driver. Non cambia EFI, kext, mappature, Wi-Fi, Bluetooth o webcam.
Non richiede sudo, password amministratore o strumenti sviluppatore sul Lenovo.

ESECUZIONE
Estrai il pacchetto completo in Download e avvia COLLECT-HID-KEYS.command.
Il comando verifica SHA256SUMS, formato Mach-O Intel e firma del binario.
La cartella sorgente da sola non è un pacchetto installabile.

MONITORAGGIO INPUT
Se macOS richiede Monitoraggio input, consenti la voce che indica nella sezione
Privacy e sicurezza di Impostazioni di Sistema. Il programma si interrompe
prima delle prove. Chiudi e riapri Terminale, quindi riesegui lo stesso comando.
Non servono modifiche alla SIP o disabilitazione della sicurezza.
Il programma non rimuove automaticamente quarantena o altri attributi.

PROVE
Prima di ogni finestra premi soltanto Invio, attendi VIA, quindi premi e rilascia
una volta il tasto richiesto. La finestra dura tre secondi. Durante VIA non
digitare testo o password. Le azioni attuali dei tasti restano attive.
Durante i tre secondi il programma sospende soltanto l'eco e la lettura a righe
del Terminale: un tasto funzione può produrre anche una sequenza escape che,
altrimenti, contaminerebbe la richiesta di Invio successiva. Questi byte vengono
scartati prima e dopo la finestra; gli eventi HID restano osservati normalmente.
Gli attributi originali del Terminale vengono ripristinati al termine della
finestra e nell'uscita controllata con Ctrl-C. Occorre un Terminale interattivo.

1. Controllo positivo: Fn+F5. Deve essere osservato esattamente un F5 premuto
   e rilasciato dallo stesso dispositivo e dallo stesso elemento HID.
   Pressioni ripetute, eventi duplicati, rilascio mancante o sorgenti diverse
   rendono il controllo inconclusivo e impediscono tutte le prove successive.
2. Solo dopo il controllo valido: F4, F7, F8, F9 senza Fn.
3. Infine la normale combinazione Comando+L per il confronto con F9.

Un errore nell'apertura di un dispositivo rilevante, un cambiamento dell'elenco
dispositivi, errori di callback o troppi eventi interrompono la raccolta.
Ogni finestra usa un nuovo IOHIDManager passivo. Gli eventi antecedenti o
successivi alla finestra vengono esclusi usando il timestamp HID monotono.
Sono inclusi anche gli input Telephony, System Control, consumer e vendor:
la pagina HID di un tasto non viene presunta prima di osservarlo.
Movimenti X/Y e rotella del mouse non sono dati della diagnosi tastiera.

RISULTATO
Il comando salva sul Desktop una cartella privata S540-HID-Keys.XXXXXX e il
relativo ZIP da allegare. Il JSON contiene inventario HID limitato a registry ID,
classe, prodotto, transport e usi primari; non legge seriali o indirizzi MAC.
Gli eventi numerici sono conservati soltanto nelle finestre richieste.
L'unico file persistente di controllo è un lock sotto
~/Library/Application Support/S540HIDKeys/; impedisce raccolte simultanee.

CAPTURED significa solo che il controllo positivo e tutte le finestre sono
completati. Non significa che F4/F7/F8 siano stati implementati o risolti.
INCONCLUSIVE significa che manca un prerequisito: non dedurre nuovi scancode.
Una finestra vuota NON prova assenza del segnale fisico o firmware.
Questa osservazione non vede byte PS/2 grezzi, notifiche ACPI/VPC non convertite
in HID, o eventi già scartati dal driver.

PER CHI COMPILA
Il sorgente Objective-C richiede Foundation e IOKit, Intel x86_64, macOS 10.15+.
--self-test esegue soltanto verifiche offline della logica: nessun accesso HID,
nessuna richiesta permessi, nessuna scrittura sul disco.
Include una regressione su uno pseudo-terminale isolato: immette una sequenza
escape F5 senza leggerla, ripristina gli attributi originali e controlla che
la successiva richiesta di Invio riceva soltanto la nuova riga.
L'esecuzione nativa sul Lenovo resta un passaggio distinto dalla compilazione
e dal self-test. Non dichiarare verifiche native senza il relativo risultato.
