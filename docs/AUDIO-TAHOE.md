# Prova audio ALC257 su Tahoe

## Stato osservato il 13 ottobre 2026

Dal desktop funzionante, `system_profiler SPAudioDataType` restituisce Audio/Devices senza dispositivi. Il controllo dei kext mostra Lilu 1.7.2, ma non AppleALC o AppleHDA. La EFI conserva AppleALC 1.9.8 con MaxKernel 24.99.99, quindi lo esclude su Darwin 25. Il codec Realtek ALC257 è già confermato dal report Windows; non occorre raccoglierlo nuovamente.

Tahoe ha rimosso AppleHDA. La sola estensione del limite MaxKernel di AppleALC non ripristina la catena audio. Il percorso AppleHDA verificato nelle fonti richiede KDK e modifiche al volume di sistema. La prima prova usa invece VoodooHDA in `/Library/Extensions`, attraverso la collezione ausiliaria dei kext, mantenendo il volume di sistema sigillato.

## Driver e modifiche previste

Il pacchetto contiene i tre file originali del bundle VoodooHDA 3.6.8 della release stabile Release368, verificati contro SHA-256 dell'asset ufficiale e manifest dei singoli file. Il binario è x86_64 e ha firma ad hoc, senza certificato Developer ID. Non viene alterato o rifirmato dal pacchetto.

Il bundle abbina il nome HDAS. Il DSDT originale del Lenovo contiene HDAS a PCI 1F.3; il programma controlla anche la presenza del dispositivo nel sistema avviato. Il driver include pin configuration per ALC257/layout 11 e accetta `voodoo-layout-id=11` nei boot-args. Questo giustifica la scelta iniziale, ma non dimostra il funzionamento di tutte le porte sul portatile.

La preparazione modifica solo:

- `csr-active-config` da Data `00000000` a `03000000`, come previsto dalla guida Tahoe per VoodooHDA. SIP viene ridotto parzialmente; non viene disabilitato authenticated root.
- La lista NVRAM/Delete per reiniettare questo valore al prossimo avvio.
- AppleALC/Enabled a false, per tenere separati i due percorsi audio.
- Il parametro `voodoo-layout-id=11`, conservando gli altri boot-args.

La coppia Whiskey Lake e le tre proprietà della correzione memoria restano invariate. Il programma conserva la EFI corrente: non ricostruisce identità, ACPI, Bluetooth o profilo Wi-Fi. Non installa pannelli preferenze o servizi aggiuntivi.

## Applicazione da macOS

Prima conservare la copia privata della EFI funzionante già descritta in [GRAFICA-INTEL.md](GRAFICA-INTEL.md). Scaricare **S540-audio-Tahoe.zip** ed estrarlo in Download. Il pacchetto crea la cartella **S540-audio-Tahoe**. Il volume OpenCore deve essere montato come **240 GB**; se ha un nome diverso, passare il percorso reale come unico argomento al comando.

1. Preparare la EFI:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe/PREPARA-AUDIO.command"
   ```

   Attendere il messaggio di preparazione riuscita, poi riavviare dallo stesso HDD OpenCore e scegliere il Samsung con Tahoe.

2. Installare il driver dopo il riavvio:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe/INSTALLA-AUDIO.command"
   ```

   Il programma verifica il SIP effettivamente attivo, il config preparato e il driver. Quando sudo chiede la password, inserirla nel Terminale; i caratteri non vengono mostrati. Il bundle viene copiato in `/Library/Extensions` e viene richiesto il caricamento con `kmutil load`. Se macOS chiede l'approvazione, aprire **Impostazioni di Sistema → Privacy e sicurezza**, approvare l'estensione e riavviare. I codici kmutil 27 e 28 significano rispettivamente approvazione o riavvio richiesti; non equivalgono a audio già funzionante.

3. Dopo il riavvio verificare:

   ```sh
   bash "$HOME/Downloads/S540-audio-Tahoe/VERIFICA-AUDIO.command"
   ```

   Provare altoparlanti e volume, poi cuffie/jack e microfono. Conservare l'esito di ciascuna prova. Sospensione e ripresa dell'audio sono una verifica successiva.

Se un controllo si ferma, conservare il messaggio. Non occorre ripetere i vecchi test Intel o reinstallare Tahoe. Il programma non riavvia automaticamente il portatile.

## Ripristino

```sh
bash "$HOME/Downloads/S540-audio-Tahoe/RIPRISTINA-AUDIO.command"
```

Il programma rimuove esclusivamente il driver che questa prova ha installato, dopo averne verificato i file, e richiede la ricostruzione della collezione ausiliaria con `kmutil rebuild`. Dopo l'installazione, il ripristino procede così:

1. Sposta il driver nel backup e richiede la ricostruzione AuxKC; seguire l'eventuale approvazione e riavviare.
2. Riaprire lo stesso comando. Controlla una nuova sessione di avvio e l'assenza di VoodooHDA dalla collezione, quindi prepara il SIP originale e chiede un altro riavvio.
3. Riaprirlo una terza volta per verificare SIP e tornare ai byte originali del config. Se la prova era stata soltanto preparata, senza installare il driver, non serve la fase AuxKC.

Se config o driver sono stati modificati successivamente, il ripristino automatico si ferma per evitare di sovrascrivere altre modifiche.

Il backup privato è in `EFI/OC/backup-audio-tahoe` e va conservato. Non aggiungerlo alla repository: contiene il config reale del dispositivo. La prova non cancella la precedente copia completa della EFI e non modifica il disco Windows.

## Limiti della verifica

Sintassi Bash, autenticità dell'asset e dei singoli file, integrità ZIP e fixture delle modifiche previste sono stati controllati in Linux. I config preparato e di ritorno al SIP originale passano ocvalidate 1.0.8; le fixture conservano identità, ACPI, Booter, grafica Intel e altre voci dei kext. Una revisione separata ha verificato gestione della copia temporanea, journal, ripresa dopo interruzioni e controllo dell'AuxKC prima del ripristino SIP. Le utility native macOS, l'approvazione dell'estensione e l'avvio fisico devono essere verificati sul portatile. Il codec supportato e il nome HDAS coerente non certificano automaticamente qualità audio, volume, jack, microfono o ripresa dalla sospensione.

AppleHDA resta una strategia successiva se questa prova non soddisfa i requisiti. La ricerca NVIDIA rimane nella [roadmap](ROADMAP.md).

## Fonti primarie

- [Dortania Tahoe: audio analogico e VoodooHDA](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html#analog-audio).
- [VoodooHDA Release368](https://github.com/CloverHackyColor/VoodooHDA/releases/tag/Release368).
- [VoodooHDA: scelta layout](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/VoodooHDADevice.cpp).
- [VoodooHDA: tabella ALC257](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/AppleALCPinConfigs.cpp).
- [AppleALC: rimozione AppleHDA in macOS 26](https://github.com/acidanthera/AppleALC/blob/master/README.md).
- [Manuale Apple di kmutil](https://keith.github.io/xcode-man-pages/kmutil.8.html): collezione ausiliaria, approvazione, caricamento e rimozione.
- [OCLP: ripristino AppleHDA nel volume di sistema](https://github.com/dortania/OpenCore-Legacy-Patcher/blob/8da38565fa1551a8e5ce8613ea835d04dd97e089/opencore_legacy_patcher/sys_patch/patchsets/hardware/misc/modern_audio.py).
