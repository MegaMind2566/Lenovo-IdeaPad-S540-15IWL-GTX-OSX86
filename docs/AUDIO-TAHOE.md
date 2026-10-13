# Prova audio ALC257 su Tahoe

## Stato osservato il 13 ottobre 2026

Dal desktop funzionante, `system_profiler SPAudioDataType` restituisce Audio/Devices senza dispositivi. Il controllo dei kext mostra Lilu 1.7.2, ma non AppleALC o AppleHDA. La EFI conserva AppleALC 1.9.8 con MaxKernel 24.99.99, quindi lo esclude su Darwin 25. Il codec Realtek ALC257 è già confermato dal report Windows; non occorre raccoglierlo nuovamente.

Tahoe ha rimosso AppleHDA. La sola estensione del limite MaxKernel di AppleALC non ripristina la catena audio. Il percorso AppleHDA verificato nelle fonti richiede KDK e modifiche al volume di sistema. La prima prova usa invece VoodooHDA in `/Library/Extensions`, attraverso la collezione ausiliaria dei kext, mantenendo il volume di sistema sigillato.

## Correzione del controllo SIP: pacchetto v2

La prima preparazione sul portatile ha superato i controlli della EFI, del driver e di HDAS, poi si è fermata prima di scrivere il backup o il config. `csrutil status` e la lettura mirata NVRAM hanno mostrato una configurazione personalizzata: Data `ZwIAAA==`, cioè byte `67020000`, maschera `0x267`. Il config contiene invece Data `00000000`. Il controllo della prima versione presumeva erroneamente che i due valori dovessero coincidere.

Il pacchetto v2 conserva il valore NVRAM iniziale in `OriginalSip` nel backup formato 2. Durante il ripristino lo reinietta prima di tornare ai byte originali del config. OpenCore 1.0.8 non sovrascrive una variabile Add già presente: il config originale può quindi tornare a zero mentre la NVRAM conserva il `67020000` iniziale. Questo percorso richiede WriteFlash=true, LegacyOverwrite=false e assenza di csr-active-config nella lista Delete originale; il programma verifica queste condizioni per il caso non nullo. Non viene resettata la NVRAM.

Errori di lettura, tipo diverso da Data, lunghezza diversa da quattro byte e valori iniziali non verificati fermano la prova. I backup formato 1 vengono conservati senza modifiche e richiedono il programma originale per il loro ripristino. Nel tentativo ricevuto non era ancora stato creato quel backup.

## Driver e modifiche previste

Il pacchetto contiene i tre file originali del bundle VoodooHDA 3.6.8 della release stabile Release368, verificati contro SHA-256 dell'asset ufficiale e manifest dei singoli file. Il binario è x86_64 e ha firma ad hoc, senza certificato Developer ID. Non viene alterato o rifirmato dal pacchetto.

Il bundle abbina il nome HDAS. Il DSDT originale del Lenovo contiene HDAS a PCI 1F.3; il programma controlla anche la presenza del dispositivo nel sistema avviato. Il driver include pin configuration per ALC257/layout 11 e accetta `voodoo-layout-id=11` nei boot-args. Questo giustifica la scelta iniziale, ma non dimostra il funzionamento di tutte le porte sul portatile.

La preparazione modifica solo:

- `csr-active-config` nel config da Data `00000000` a `03000000`, come previsto dalla guida Tahoe per VoodooHDA. La preparazione accetta il valore NVRAM originale verificato `00000000` oppure `67020000` e lo salva separatamente come Data nel backup. Da `67020000`, la maschera della prova riduce i permessi già concessi. Non viene disabilitato authenticated root.
- La lista NVRAM/Delete per reiniettare questo valore al prossimo avvio.
- AppleALC/Enabled a false, per tenere separati i due percorsi audio.
- Il parametro `voodoo-layout-id=11`, conservando gli altri boot-args.

La coppia Whiskey Lake e le tre proprietà della correzione memoria restano invariate. Il programma conserva la EFI corrente: non ricostruisce identità, ACPI, Bluetooth o profilo Wi-Fi. Non installa pannelli preferenze o servizi aggiuntivi.

## Esito della correzione volume: 13 ottobre 2026

Dopo la prova v3 è stato riferito un esito positivo: riproduzione audio, regolazione graduale e tasti F1–F3 funzionano. Il problema della variazione udibile soltanto a zero/muto è quindi risolto nella prova sul portatile. Si conserva questa configurazione. Il nuovo output tecnico della verifica non è stato allegato; non si estende l'esito automaticamente a jack, microfono o sospensione.

## Acquisizione voce e guadagno: 14 ottobre 2026

Nella prova video Photo Booth è stato riferito che la voce si sente, insieme all'immagine della webcam. Il guadagno microfono è eccessivo: la regolazione nelle impostazioni passa bruscamente da troppo alto a troppo basso. L'acquisizione audio è presente; sono da verificare ingresso selezionato e controlli IOAudio. Nel sorgente fissato, VolumeChangeFix aggiorna tutti i mixer anche quando varia l'ingresso: è una possibile causa, da distinguere dall'effettiva configurazione degli amplificatori sul portatile. Non viene applicata una nuova patch al driver; equalizzazione e tasti funzione restano rinviati.

## Equalizzazione da rivedere piu avanti

È richiesto un affinamento dell'equalizzazione, da affrontare più avanti. L'attività resta nella roadmap come prova separata della timbrica; non vengono aggiunte ora modifiche a mixer, amplificazione o driver.

## Controllo del volume: pacchetto v3

Dopo la prova v2 sono stati riferiti riproduzione audio e funzionamento dei tasti F1, F2 e F3. La variazione graduale non è ancora efficace: il suono cambia soltanto quando il volume arriva a zero/muto. Non sono stati documentati separatamente cuffie/jack e microfono.

Nel sorgente VoodooHDA 3.6.8, `VoodooHDAEnableVolumeChangeFix` abilita l'inoltro del valore al mixer PCM e agli altri controlli del mixer. Con il flag false, la variazione dell'uscita viene inoltrata al master VOLUME, che può non controllare il guadagno effettivo del codec. Il flag è letto durante l'inizializzazione del dispositivo: serve aggiornare il driver e riavviare per provarlo.

La prova v3 modifica solo `IOKitPersonalities.VoodooHDA.VoodooHDAEnableVolumeChangeFix` da false a true. HalfVolumeFix, HalfMicVolumeFix, MuteFix, Boost, PCM iniziale e altre impostazioni restano invariati. Poiché il plist è sigillato dalla firma del bundle, la copia modificata viene firmata nuovamente ad hoc e verificata sul Mac. Non viene fornito un driver alterato senza firma.

### Sul sistema che ha già audio funzionante

Estrarre **S540-audio-Tahoe-v3.zip** in Download, poi eseguire:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/VOLUME-AUDIO.command"
```

Il programma usa il backup audio formato 2 esistente, verifica il driver già installato, conserva una copia completa e prepara la variante in una cartella temporanea. La sostituzione avviene solo dopo verifica dei file e della firma. Non cambia config, SIP o impostazioni Intel. Richiede la ricostruzione AuxKC con `kmutil rebuild`: seguire l'eventuale approvazione di macOS e riavviare. Non usare unload/load a caldo per questa prova.

Dopo il riavvio eseguire:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/VERIFICA-AUDIO.command"
```

Verificare il flag esposto in IORegistry e, con lo stesso contenuto in riproduzione, confrontare volume circa 25%, 50% e 100%, poi muto. Controllare sia i tasti F2/F3 sia il cursore del volume di macOS. Il successo della scrittura del plist non dimostra ancora l'attenuazione graduale.

Per tornare al driver precedente, mantenendo l'audio installato:

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/ANNULLA-VOLUME-AUDIO.command"
```

Seguire il riavvio indicato. Per rimuovere tutto l'audio utilizzare **RIPRISTINA-AUDIO.command del pacchetto v3**: riconosce sia il driver originario sia la variante volume creata e verificata da questa prova. I comandi del vecchio pacchetto v2 controllano soltanto i file originali e si fermerebbero davanti alla variante.

## Prima installazione da macOS

Prima conservare la copia privata della EFI funzionante già descritta in [GRAFICA-INTEL.md](GRAFICA-INTEL.md). Scaricare **S540-audio-Tahoe-v3.zip** ed estrarlo in Download. Il pacchetto crea la cartella **S540-audio-Tahoe-v3**. Il volume OpenCore deve essere montato come **240 GB**; se ha un nome diverso, passare il percorso reale come unico argomento al comando.

1. Preparare la EFI:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe-v3/PREPARA-AUDIO.command"
   ```

   Attendere il messaggio di preparazione riuscita, poi riavviare dallo stesso HDD OpenCore e scegliere il Samsung con Tahoe.

2. Installare il driver dopo il riavvio:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe-v3/INSTALLA-AUDIO.command"
   ```

   Il programma verifica il SIP effettivamente attivo, il config preparato e il driver. Quando sudo chiede la password, inserirla nel Terminale; i caratteri non vengono mostrati. Il bundle viene copiato in `/Library/Extensions` e viene richiesto il caricamento con `kmutil load`. Se macOS chiede l'approvazione, aprire **Impostazioni di Sistema → Privacy e sicurezza**, approvare l'estensione e riavviare. I codici kmutil 27 e 28 significano rispettivamente approvazione o riavvio richiesti; non equivalgono a audio già funzionante.

3. Dopo il riavvio verificare:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe-v3/VERIFICA-AUDIO.command"
   ```

   Provare altoparlanti e volume, poi cuffie/jack e microfono. Conservare l'esito di ciascuna prova. Sospensione e ripresa dell'audio sono una verifica successiva.

Se un controllo si ferma, conservare il messaggio. Non occorre ripetere i vecchi test Intel o reinstallare Tahoe. Il programma non riavvia automaticamente il portatile.

## Ripristino

```sh
bash "$HOME/Downloads/S540-audio-Tahoe-v3/RIPRISTINA-AUDIO.command"
```

Il programma rimuove esclusivamente il driver che questa prova ha installato, dopo averne verificato i file, e richiede la ricostruzione della collezione ausiliaria con `kmutil rebuild`. Dopo l'installazione, il ripristino procede così:

1. Sposta il driver nel backup e richiede la ricostruzione AuxKC; seguire l'eventuale approvazione e riavviare.
2. Riaprire lo stesso comando. Controlla una nuova sessione di avvio e l'assenza di VoodooHDA dalla collezione, quindi prepara il SIP originale e chiede un altro riavvio.
3. Riaprirlo una terza volta per verificare SIP e tornare ai byte originali del config. Se la prova era stata soltanto preparata, senza installare il driver, non serve la fase AuxKC.

Se config o driver sono stati modificati successivamente, il ripristino automatico si ferma per evitare di sovrascrivere altre modifiche.

Il backup privato è in `EFI/OC/backup-audio-tahoe` e va conservato. Gli snapshot della prova volume e il relativo manifest sono conservati al suo interno. Non aggiungerlo alla repository: contiene il config reale del dispositivo. La prova non cancella la precedente copia completa della EFI e non modifica il disco Windows.

## Limiti della verifica

Sintassi Bash, autenticità dell'asset e dei singoli file, integrità ZIP e fixture delle modifiche previste sono stati controllati in Linux. I config preparato e di ritorno al SIP originale passano ocvalidate 1.0.8; le fixture conservano identità, ACPI, Booter, grafica Intel e altre voci dei kext. Una revisione separata ha verificato gestione della copia temporanea, journal, ripresa dopo interruzioni e controllo dell'AuxKC prima del ripristino SIP. La prima esecuzione sul portatile ha verificato payload, firma, proprietà della EFI e HDAS prima del blocco SIP. La lettura corretta e il ripristino dei casi iniziali zero e 0x267 sono stati controllati con fixture; dopo la versione v2 è stata riferita la riproduzione audio funzionante con i tasti F1–F3.

Per la prova volume v3, una fixture verifica l'unico Bool modificato e la conservazione delle altre proprietà del mixer. Le funzioni hash effettive del programma riconoscono il payload originale e la variante registrata nella fixture, e rifiutano un binario alterato. La firma e la ricostruzione AuxKC non sono state eseguite direttamente nell'ambiente Linux. Dopo la prova sul Mac è stato riferito un esito positivo della riproduzione e dell'attenuazione graduale; non è stato allegato un nuovo report tecnico. Il codec supportato e il nome HDAS coerente non certificano automaticamente qualità audio, jack, microfono o ripresa dalla sospensione.

AppleHDA resta una strategia successiva se questa prova non soddisfa i requisiti. La ricerca NVIDIA rimane nella [roadmap](ROADMAP.md).

## Fonti primarie

- [Dortania Tahoe: audio analogico e VoodooHDA](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html#analog-audio).
- [VoodooHDA Release368](https://github.com/CloverHackyColor/VoodooHDA/releases/tag/Release368).
- [VoodooHDA: gestione del volume](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/VoodooHDAEngine.cpp#L1027).
- [VoodooHDA: lettura dei flag e curva del mixer](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/VoodooHDADevice.cpp#L237).
- [Manuale Apple di codesign](https://keith.github.io/xcode-man-pages/codesign.1.html): sostituzione e verifica della firma ad hoc.
- [VoodooHDA: scelta layout](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/VoodooHDADevice.cpp).
- [VoodooHDA: tabella ALC257](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/AppleALCPinConfigs.cpp).
- [AppleALC: rimozione AppleHDA in macOS 26](https://github.com/acidanthera/AppleALC/blob/master/README.md).
- [OpenCore 1.0.8: aggiunta NVRAM senza sovrascrittura](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcMainLib/OpenCoreNvram.c#L193) e [gestione della variabile esistente](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Library/OcVariableLib/LegacyNvramSupport.c#L134).
- [Manuale Apple di kmutil](https://keith.github.io/xcode-man-pages/kmutil.8.html): collezione ausiliaria, approvazione, caricamento e rimozione.
- [OCLP: ripristino AppleHDA nel volume di sistema](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/8da38565fa1551a8e5ce8613ea835d04dd97e089/opencore_legacy_patcher/sys_patch/patchsets/hardware/misc/modern_audio.py).
