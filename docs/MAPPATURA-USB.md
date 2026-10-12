# Mappatura USB da Windows

Questa fase identifica le porte fisiche prima di preparare l'installer. La mappa serve anche per webcam, Bluetooth e per il Samsung 960 EVO esterno su USB-C.

1. Scaricare [Windows.exe dalla release ufficiale USBToolBox 0.2](https://github.com/USBToolBox/tool/releases/download/0.2/Windows.exe) e salvarlo in una cartella normale, per esempio USBToolBox sul Desktop.
2. Avviare Windows.exe. Nel menu scegliere **Discover Ports**.
3. Collegare una chiavetta o un disco USB 3 a ogni porta esterna, una porta alla volta. Attendere che compaia nell'elenco prima di passare alla porta successiva. Provare anche la USB-C se disponibile e, quando possibile, entrambi i versi del connettore.
4. Tornare al menu e scegliere **Select Ports and Build Kext**. Conservare le porte rilevate, comprese quelle interne per webcam e Bluetooth; le porte interne usano normalmente il tipo **255**.
5. Premere **K** per creare la mappa. Comprimere in uno ZIP la cartella **UTBMap.kext** generata e allegarla nella chat del progetto.

Per la USB-C, provare anche il Samsung 960 EVO nel box e con il cavo effettivamente previsti. Verificare che compaia nell'elenco in entrambi i versi del connettore. Il disco non viene inizializzato né formattato da USBToolBox.

Su Windows USBToolBox rileva le porte companion: di norma un dispositivo USB 3 consente di identificare anche la porta USB 2 corrispondente. Se una coppia non viene rilevata, ripetere su quella porta con un dispositivo USB 2.

Se il programma segnala un errore o non è chiaro quali porte scegliere, fornire una schermata del menu di selezione prima di creare la mappa. Non occorre modificare il BIOS.

La mappa deve rispettare il limite di 15 porte per controller di macOS. Il limite si applica alle porte logiche, quindi una presa USB 3 può contare come due porte. La selezione verrà verificata prima dell'integrazione in OpenCore.

Fonte: [USBToolBox — documentazione ufficiale](https://github.com/USBToolBox/tool).

## Mappa ricevuta e verificata

La `UTBMap.kext` fornita coincide con le 9 porte selezionate in `usb.json`, sul controller `XHC` PCI `8086:9DED`. Il plist originale è conservato in `usb/UTBMap.kext`; il riepilogo privo di seriali e percorsi Windows è in `usb/ports.json`. Il JSON grezzo non viene aggiunto alla repository.

| Nome nella mappa | Porta controller | Tipo | Uso |
|---|---:|---:|---|
| HS01 | 1 | 9 | USB-C USB 2 |
| HS02 | 2 | 255 | Fingerprint interno |
| HS03 | 4 | 255 | Webcam interna |
| HS04 | 6 | 3 | USB-A USB 2 |
| HS05 | 7 | 3 | USB-A USB 2 |
| HS06 | 10 | 255 | Bluetooth interno |
| SS01 | 13 | 3 | USB-A SuperSpeed |
| SS02 | 14 | 3 | USB-A SuperSpeed |
| SS03 | 15 | 9 | USB-C SuperSpeed |

`HS03` indica qui la porta fisica 4: i nomi sono etichette generate dal programma; il campo binario `port` contiene il numero effettivo. I dispositivi interni sono marcati `255`, le USB-A `3` e la USB-C `9` (con switch).

Il box RTL9210 è stato osservato a velocità USB 2 sulla porta 1. La porta SuperSpeed 15 è selezionata ma non contiene un dispositivo registrato. La mappa è utilizzabile per il primo test; velocità USB 3 e funzionamento nelle due orientazioni USB-C richiedono ancora una prova con box e cavo definitivi.
