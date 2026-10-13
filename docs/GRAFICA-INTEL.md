# Verifica della grafica Intel dopo l'installazione

La UHD 620 è il primo obiettivo dopo il desktop. La EFI contiene già Lilu, WhateverGreen e le proprietà iniziali `AAPL,ig-platform-id=00009B3E` e `device-id=9B3E0000`. Il test `-igfxvesa` disabilita l'accelerazione Intel. Il [log delle 02:45](ANALISI-LOG-AVVIO.md) conferma che in quel tentativo erano attivi `-igfxvesa` e `-x`. Lo stato di un eventuale avvio successivo ai ripristini resta da verificare.

Una fotografia successiva documenta un panic USB/Bluetooth con `bluetoothd` e IntelBTPatcher 2.4 nella traccia, senza `-x` e con `-igfxvesa` ancora presente. Con il patcher escluso è stato poi superato il panic, ma rimane lo schermo nero con il puntatore. I boot-args di questo nuovo tentativo non sono stati raccolti. Usa **TEST-INTEL.cmd** sulla EFI attuale: controlla e rimuove solo i due flag diagnostici, preservando l'esclusione Bluetooth. Se sono già assenti, raccogli il messaggio e il log nuovo. La causa della mancata interfaccia non è ancora identificata.

Completa prima l'installazione sul 960 EVO. Mantieni OpenCore sull'HDD di avvio finché il sistema non è stato verificato.

## 1. Leggi lo stato dal primo desktop

Apri Terminale in macOS ed esegui questi due comandi. Leggono informazioni; non modificano la EFI.

```sh
sysctl -n kern.bootargs
system_profiler SPDisplaysDataType
```

Raccogli soltanto questi risultati. Non occorre inviare l'intera EFI, gli identificativi SMBIOS o il plist di itlwm che contiene il profilo Wi-Fi.

In alternativa, per il report grafico apri **Impostazioni di Sistema → Generali → Info → Resoconto di sistema → Grafica/Monitor**. La presenza del desktop o un valore di memoria video, da soli, non dimostrano l'accelerazione. Servono il supporto Metal indicato nel report e una prova del suo funzionamento.

## 2. Se è presente `-igfxvesa`

Dopo aver raccolto lo stato, si può provare la configurazione accelerata già preparata:

1. Avvia Windows dal menu Lenovo.
2. Se sono stati applicati entrambi i test, avvia prima **RIPRISTINA-AVVIO.cmd** e poi **RIPRISTINA-GRAFICA.cmd** sullo stesso HDD di OpenCore. Se è presente solo il test grafico, usa il secondo. I file devono stare accanto a `EFI`, con i rispettivi script nella cartella `tools`. Se **TEST-INTEL.cmd** ha già rimosso i due parametri, questa sequenza non serve.
3. Attendi il messaggio di ripristino riuscito. Lo script usa `EFI/OC/config.before-graphics-test.plist` e conserva gli identificativi della configurazione originale.
4. Riavvia dallo stesso OpenCore e scegli il volume esterno di macOS, indicato come **Machintosh SSD** nel log ricevuto. La comparsa del nome non certifica il completamento dell'installazione.
5. Rileggi i due comandi e verifica Metal.

Se manca il backup o lo script segnala ulteriori modifiche, raccogli il messaggio prima di procedere. Non sostituire il plist con quello di una nuova build: gli identificativi generati potrebbero essere diversi.

Se l'avvio accelerato si blocca, torna a Windows e riapplica **TEST-GRAFICA.cmd** sullo stesso HDD. Dopo il ritorno al desktop raccogli la foto del blocco e i dati del tentativo. Si analizzano poi DVMT, framebuffer e proprietà della UHD 620 in base all'errore osservato.

## 3. Se `-igfxvesa` è già assente

Non eseguire il ripristino solo perché l'interfaccia sembra lenta. Il report determina se Metal viene esposto. Se manca, si verificano il caricamento di Lilu/WhateverGreen, le proprietà grafiche applicate e i log. Non si aggiungono correzioni della memoria framebuffer senza dati sul problema.

## Criteri per completare questa fase

- Supporto Metal rilevato sul dispositivo Intel e verificato con un carico grafico che lo usa.
- Avvio ripetibile con accelerazione, alla risoluzione nativa del pannello.
- Nessun blocco o artefatto durante le prove del desktop e del carico grafico.
- Regolazione della luminosità e ripresa del display dopo la sospensione, da verificare nelle prove hardware successive.

Questa fase non conferma automaticamente decodifica video hardware, uscita HDMI o funzionamento della NVIDIA. Sono prove distinte nella [roadmap](ROADMAP.md).

## Riferimenti

- [WhateverGreen 1.7.1: opzioni Intel, incluso -igfxvesa](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics)
- [Apple: Resoconto di sistema su Tahoe](https://support.apple.com/guide/system-information/welcome/11.0/mac/26)
- [Dortania: grafica Intel sui portatili Coffee Lake / Whiskey Lake](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties)
