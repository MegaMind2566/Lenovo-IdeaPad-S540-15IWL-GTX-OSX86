# Lenovo IdeaPad S540-15IWL GTX — progetto Hackintosh

Obiettivo: usare macOS Tahoe 26 su Lenovo IdeaPad S540-15IWL GTX e completare le prove di tutti i componenti. La compatibilità completa è un obiettivo da verificare sul dispositivo.

**Stato al 13 ottobre 2026: Tahoe raggiunge il desktop sul Samsung 960 EVO esterno dopo la correzione della memoria framebuffer. IntelAccelerator è rilevato; il report grafico espone Metal 3, memoria condivisa dinamica fino a 1536 MB e pannello interno online a 1920×1080. IntelBTPatcher resta escluso dopo il panic Bluetooth. Stabilità prolungata e altre funzioni hardware restano da verificare.**
Sequoia 15 resta un'alternativa da valutare se le prove con Tahoe evidenziano problemi.

## Cosa fare adesso

La [verifica completa della EFI e dei config](docs/VERIFICA-EFI.md) non ha trovato file mancanti, versioni OpenCore mischiate o dipendenze incoerenti. Tutti i 55 file della consegna corrispondono al manifest; ocvalidate 1.0.8 è stato eseguito nuovamente sul config allegato e su quello della prova Whiskey Lake, senza problemi. La EFI consegnata è già compatta. I file correnti del disco restano al loro posto, inclusa l'eventuale configurazione Wi-Fi successiva alla consegna.

La correlazione degli indirizzi del panic con il dump di AppleIntelCFLGraphicsFramebuffer ha identificato l'asserzione minStolenSize <= fStolenMemorySize: il profilo richiedeva 58 MB, superiori alla memoria calcolata dal driver. La [correzione memoria Intel](docs/TEST-MEMORIA-INTEL.md) applica patch-enable, stolenmem 19 MB e fbmem 9 MB, conservando la coppia Whiskey Lake e tutte le altre impostazioni. Dopo questa correzione sono stati raggiunti la configurazione iniziale e il desktop, con Metal 3 esposto.

Il prossimo passo è salvare una copia privata dell'intera EFI funzionante, poi verificare avvii ripetuti e componenti seguendo [GRAFICA-INTEL.md](docs/GRAFICA-INTEL.md). La EFI resta invariata durante queste verifiche. **S540-memoria-Intel.zip** contiene gli strumenti già usati: TEST-MEMORIA-INTEL.cmd prepara la correzione, RECOVERY-MEMORIA-INTEL.cmd aggiunge VESA mantenendola e RIPRISTINA-MEMORIA-INTEL.cmd annulla la prova. Non occorre riapplicarli al sistema che ha già raggiunto il desktop. Le procedure precedenti di raccolta sono conservate per consultazione.

La [verifica delle patch ACPI](docs/VERIFICA-PATCH-ACPI.md) non ha trovato un errore statico nei percorsi GPU, XOSI, PNLF, EC, RTC o PLUG. Il dump della [traccia diretta](docs/TRACCIA-INTEL.md) ha fornito la nuova evidenza runtime necessaria per intervenire sulla memoria. Il test non modifica DSDT, BIOS, connettori o VRAM dichiarata.

Il dump ACPI contiene DSDT e tutte le 12 SSDT enumerate da Windows; le 20 tabelle utili hanno lunghezza, checksum e SHA-256 validi. Non occorre ripetere la raccolta. Il Samsung 960 EVO esterno è stato rilevato dopo aver reinserito l'M.2 nel box; la velocità USB 3 resta da verificare. Windows sul PM981a interno rimane al suo posto.

La [roadmap hardware](docs/ROADMAP.md) mantiene aperto il port NVIDIA dopo la stabilizzazione Intel. Desktop e Metal 3 esposto sono confermati; carico grafico prolungato, audio, Bluetooth, touchpad, autonomia e sospensione richiedono ancora prove sul portatile. I sorgenti ACPI sono in acpi/source, le versioni compilate in acpi/compiled; [l'analisi](docs/ANALISI-ACPI.md) descrive il loro scopo.

### Per una nuova raccolta

1. Su GitHub premi **Code → Download ZIP**.
2. Estrai tutto lo ZIP in una cartella normale. Non avviare i file dentro lo ZIP.
3. Premi due volte **RACCOGLI-DATI.cmd**. Accetta la richiesta di amministratore di Windows.
4. Attendi la raccolta. Alla fine troverai sul Desktop **Lenovo-Hackintosh-dati-DATA-ORA.zip**.
5. Allega quel file ZIP nella chat del progetto. Se il programma segnala una raccolta parziale, allegalo comunque.

Serve Internet per scaricare un piccolo strumento ACPI ufficiale. Il suo SHA-256 viene verificato prima dell'esecuzione. La raccolta usa Windows PowerShell 5.1, già presente in Windows 11; non richiede Python.

Se compare un errore prima della raccolta, allega **errore-avvio.txt**, creato nella cartella estratta. Se il file non viene creato, copia il messaggio della finestra.

## Che cosa fa il programma

- Legge modello, BIOS, CPU, RAM e modelli dei dischi.
- Legge gli identificativi hardware di grafica, audio, rete, tastiera e touchpad.
- Esporta le tabelle ACPI utili e controlla lunghezza e checksum.
- Confronta il numero di SSDT esportate con quello enumerato da Windows.
- Salva JSON, CSV, tabelle AML e un riepilogo nello ZIP.

Il programma scrive soltanto i propri file di raccolta e una copia temporanea dello strumento ACPI. Non modifica BIOS, partizioni, bootloader, cifratura o impostazioni permanenti di PowerShell. Non invia automaticamente i dati a servizi esterni. Le tabelle MSDM e SLIC, i numeri di serie dei dischi, il nome del computer e gli indirizzi MAC non vengono aggiunti allo ZIP.

Se lo strumento ACPI non è scaricabile o non funziona, usa le API di Windows come ripiego. Queste API restituiscono soltanto la prima tabella per ogni firma: lo stato **parziale** viene indicato esplicitamente. Non si disattivano protezioni di Windows per completare la raccolta.

## Prima dell'installazione

Il disco indicato per macOS è un Samsung 960 EVO su USB-C. La prima EFI contiene un tentativo di blocco del driver NVMe nativo per escludere il PM981a interno. Il disco interno è comunque comparso nella Recovery: l'esclusione non è confermata. Rimane al suo posto per Windows. Se il 960 EVO verrà montato internamente, la configurazione NVMe dovrà essere riesaminata prima dell'avvio.

Per questa prova OpenCore e Recovery sono sull'HDD USB già preparato. Il programma di raccolta non prepara il supporto e non esegue l'installazione.

## Percorso di lavoro

1. Raccolta e verifica ACPI, codec audio e touchpad.
2. Scelta del disco di prova e mappatura USB.
3. Configurazione OpenCore per UHD 620, gestione CPU, batteria e disabilitazione del driver NVIDIA. Spegnimento elettrico della dGPU da provare separatamente.
4. Avvio dell'installer ufficiale Apple e primo avvio di macOS.
5. Prove di grafica, audio, Wi-Fi, Bluetooth, USB, batteria, luminosità e sospensione.

La GTX 1650 non dispone di un driver macOS utilizzabile nella EFI attuale. Il port dei driver Linux resta nella [roadmap](docs/ROADMAP.md#ricerca-nvidia). Anche l'uscita HDMI richiede una prova e la verifica del percorso hardware: il precedente progetto per questo modello la indica non funzionante.

Il riepilogo dei componenti verificati è in [docs/HARDWARE.md](docs/HARDWARE.md).

## Riferimenti

- [Dortania: Coffee Lake e Whiskey Lake portatili](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html)
- [Dortania: Tahoe](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html)
- [OpenIntelWireless: dispositivi supportati](https://openintelwireless.github.io/itlwm/Compat.html)
- [Acidanthera: NVMeFix](https://github.com/acidanthera/NVMeFix)
- [Progetto precedente S540-15IWL di lucatek](https://github.com/lucatek/Lenovo-Ideapad-S540-15IWL-Hackintosh)
- [SSDTTime di CorpNewt](https://github.com/CorpNewt/SSDTTime)
- [ACPICA: release usata per la raccolta](https://github.com/open-acpica/acpica/releases/tag/20251212)
- [Microsoft: limiti di GetSystemFirmwareTable](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemfirmwaretable)

Il progetto precedente è un riferimento hardware per Catalina/Clover. La sua EFI non viene redistribuita o usata come configurazione pronta per Tahoe.
