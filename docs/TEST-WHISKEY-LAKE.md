# Prova del profilo Intel Whiskey Lake

Questa è una prova di compatibilità preparata dopo il controllo del config.plist e dei due avvii normali `170135` e `170413`. Non è una soluzione già confermata sul dispositivo. L'hardware raccolto indica UHD 620 Whiskey Lake, PCI 8086:3EA0.

| Proprietà Intel, tipo Data di 4 byte | Config ricevuto | Prova |
|---|---|---|
| AAPL,ig-platform-id | `00009B3E` | `0900A53E` |
| device-id | `9B3E0000` | `A53E0000` |

Il manuale incluso in WhateverGreen 1.7.1 indica esplicitamente A53E0000 per il device-id UHD 620 Whiskey Lake e 0x3EA50009 come framebuffer portatile predefinito. Il profilo precedente è una baseline mobile proposta dalla guida Dortania; la differenza fra le due indicazioni motiva una prova, non dimostra da sola la causa dello schermo nero.

Il pacchetto **S540-test-WhiskeyLake.zip**, consegnato nella chat, contiene un config di prova, un backup esatto del config ricevuto e le istruzioni. Per mantenere privata l'identità della macchina, questi plist non sono presenti nel repository. Il builder mantiene le impostazioni precedenti finché il test non produce un risultato verificato.

## Applicazione e ritorno

1. Da Windows estrarre lo ZIP in una cartella normale.
2. Copiare config.plist e config.before-whiskey-lake.plist in EFI/OC sull'HDD dello stesso OpenCore usato negli ultimi avvii. Sostituire config.plist.
3. Avviare OpenCore e scegliere **Machintosh SSD** sul Samsung esterno. Se compare il benvenuto, proseguire nella configurazione iniziale.
4. Se non migliora, copiare il backup in un'altra cartella, rinominare quella copia config.plist e sostituire EFI/OC/config.plist con la copia. Conservare il backup.

Sono cambiate soltanto le due proprietà Intel. Il backup è identico byte per byte al file ricevuto. Parsing del plist, differenze semantiche e CRC dello ZIP sono verificati. IntelBTPatcher resta disattivato, VESA e modalità sicura restano assenti. Nessun altro valore, inclusa l'identità SMBIOS, è modificato.

Entrambi i profili dichiarano 58 MB di memoria stolen. La prova non cambia DVMT, non aggiunge patch di memoria o connettori e non dimostra l'accelerazione. Se l'interfaccia parte, verificare [Intel e Metal](GRAFICA-INTEL.md). Se non parte, conservare il nuovo log OpenCore e raccogliere i dati unificati dalla Recovery: i dati GUI ricevuti finora descrivono soltanto avvii VESA. La fine del log OpenCore a EXITBS:START non localizza lo stallo successivo.

## Riferimenti

- [WhateverGreen 1.7.1: manuale Intel](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/Manual/FAQ.IntelHD.en.md), sezioni CFL/CML, Recommended framebuffers e indicazione Whiskey Lake.
- [Dortania: Coffee Lake e Whiskey Lake portatili](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html#deviceproperties), indicazione della baseline UHD 620 e patch DVMT condizionale.
