# Raccolta dei controlli microfono

Il microfono interno VoodooHDA è presente e registra la voce. Il report del 14 ottobre 2026 mostra due canali a 48 kHz, entrambi con valore 57 su 100 e scala dichiarata da 0 a +30 dB. Non specifica il numero di passi dell'amplificatore né il guadagno realmente applicato. La regolazione percepita passa bruscamente da troppo forte a troppo debole.

Questa raccolta confronta i mixer con il cursore ingresso circa al 30% e al 70%. Non installa driver, cambia plist o scrive la EFI. Il cursore viene spostato manualmente; annotare la posizione iniziale e ripristinarla alla fine. Non occorre riprodurre o registrare audio durante la raccolta.

## Uso

Estrarre `S540-microfono-v2.zip` in Download ed eseguire:

```sh
bash "$HOME/Downloads/S540-microfono-v2/RACCOGLI-MICROFONO.command"
```

Seguire le due indicazioni nel Terminale. Lo ZIP diagnostico viene creato sulla Scrivania. Allegarlo privatamente nella chat; non aggiungere i risultati alla repository. Non servono Xcode o Python sul portatile.

Il programma verifica VoodooHDA 3.6.8 originale oppure la variante della correzione volume V3. Quest'ultima viene riconosciuta attraverso il manifest registrato nel backup audio del disco `240 GB`: quel volume deve essere montato. Vengono confrontati i tre file del bundle, le copie conservate e il solo cambiamento previsto nel plist. La firma V3 modifica anche il binario Mach-O, quindi il suo hash completo differisce dall'originale. Prima di ogni lettura si ricontrolla l'hash della variante riconosciuta e quello della sonda.

Se un controllo o una lettura fallisce, conserva i dettagli nella cartella della raccolta e segnala il problema. Non richiede privilegi amministrativi e non ripara automaticamente i permessi. Il controllo legge il backup senza richiamare il programma di ripristino audio: il config con `-igfxblr` non viene coinvolto.

## Cosa contiene

- `AUDIO.txt`: elenco dei dispositivi audio.
- Due rilevazioni dei controlli IOAudio e dei mixer VoodooHDA.
- L'eventuale buffer di inizializzazione già presente nel driver.

La sonda legge il buffer mixer `0x3000` del driver: sono percentuali memorizzate per il canale sinistro, non misure in dB né letture dirette degli amplificatori. Il buffer `0x2000` è facoltativo: il sorgente registra durante l'inizializzazione anche con verbosità zero, ma il buffer ha capacità limitata e la completezza va verificata nel risultato. Non viene richiesta la generazione di un nuovo dump del codec. La raccolta non include EFI, identità SMBIOS, password Wi-Fi o archivi dei log di sistema.

## Sorgenti e verifica

ABI fissata a [VoodooHDA, commit 8c7e8e2](https://github.com/CloverHackyColor/VoodooHDA/blob/8c7e8e2ce6de0a917be663a3192857955288c937/tranc/Shared.h). La sorgente della sonda è in `tools/hda_mixer_snapshot.c`; compilazione Intel e verifica della firma ad hoc sono eseguite dalla workflow `build-microphone-probe.yml`. L'assenza di VoodooHDA sul runner permette di verificare l'enumerazione senza driver, non la lettura sul portatile.
