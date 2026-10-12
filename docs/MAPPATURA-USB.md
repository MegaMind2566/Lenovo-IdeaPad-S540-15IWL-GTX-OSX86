# Mappatura USB da Windows

Questa fase identifica le porte fisiche prima di preparare l'installer. La mappa serve anche per webcam, Bluetooth e un eventuale SSD esterno.

1. Scaricare [Windows.exe dalla release ufficiale USBToolBox 0.2](https://github.com/USBToolBox/tool/releases/download/0.2/Windows.exe) e salvarlo in una cartella normale, per esempio USBToolBox sul Desktop.
2. Avviare Windows.exe. Nel menu scegliere **Discover Ports**.
3. Collegare una chiavetta o un disco USB 3 a ogni porta esterna, una porta alla volta. Attendere che compaia nell'elenco prima di passare alla porta successiva. Provare anche la USB-C se disponibile e, quando possibile, entrambi i versi del connettore.
4. Tornare al menu e scegliere **Select Ports and Build Kext**. Conservare le porte rilevate, comprese quelle interne per webcam e Bluetooth; le porte interne usano normalmente il tipo **255**.
5. Premere **K** per creare la mappa. Comprimere in uno ZIP la cartella **UTBMap.kext** generata e allegarla nella chat del progetto.

Su Windows USBToolBox rileva le porte companion: di norma un dispositivo USB 3 consente di identificare anche la porta USB 2 corrispondente. Se una coppia non viene rilevata, ripetere su quella porta con un dispositivo USB 2.

Se il programma segnala un errore o non è chiaro quali porte scegliere, fornire una schermata del menu di selezione prima di creare la mappa. Non occorre modificare il BIOS.

La mappa deve rispettare il limite di 15 porte per controller di macOS. Il limite si applica alle porte logiche, quindi una presa USB 3 può contare come due porte. La selezione verrà verificata prima dell'integrazione in OpenCore.

Fonte: [USBToolBox — documentazione ufficiale](https://github.com/USBToolBox/tool).
