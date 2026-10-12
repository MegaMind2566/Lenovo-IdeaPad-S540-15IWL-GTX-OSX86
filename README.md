# Lenovo IdeaPad S540-15IWL GTX — progetto Hackintosh

Obiettivo: preparare OpenCore per macOS Tahoe 26 su Lenovo IdeaPad S540-15IWL GTX.

**Stato: prima EFI validata; i primi tentativi su HDD USB hanno avviato il kernel e i servizi della Recovery, ma non hanno mostrato l'interfaccia grafica. Diagnostica in corso.**
Sequoia 15 resta un'alternativa da valutare se le prove con Tahoe evidenziano problemi.

## Cosa fare adesso

Il dump disponibile contiene una DSDT e tutte le 12 SSDT enumerate da Windows. Le 20 tabelle ACPI utili raccolte hanno lunghezza, checksum e SHA-256 validi. Non occorre ripetere la raccolta.

Il prossimo passo per il blocco riscontrato è il [test grafico reversibile](docs/TEST-GRAFICA.md). Le istruzioni generali restano in [primo avvio](docs/PRIMO-AVVIO.md). Scarica il pacchetto da **Actions → EFI per la prima prova → ultima esecuzione riuscita → Artifacts**. Il **Samsung 960 EVO** sarà esterno su **USB-C**. La mappa fornita contiene 9 porte; la velocità USB 3 del box resta da verificare con il cavo definitivo.

Le patch sono descritte in [docs/ANALISI-ACPI.md](docs/ANALISI-ACPI.md). I sorgenti sono in `acpi/source`, le versioni compilate in `acpi/compiled`. Compilazione e checksum non sostituiscono un avvio sul portatile.

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

Il disco indicato per macOS è un Samsung 960 EVO su USB-C. La prima EFI blocca il driver NVMe nativo in macOS per escludere il PM981a interno. Il blocco riguarda tutti gli NVMe interni: deve essere rimosso se in futuro il 960 EVO verrà montato internamente.

Servirà inoltre una chiavetta USB vuota per l'installer. Preparazione della chiavetta e installazione saranno passaggi successivi; questo programma non li esegue.

## Percorso di lavoro

1. Raccolta e verifica ACPI, codec audio e touchpad.
2. Scelta del disco di prova e mappatura USB.
3. Configurazione OpenCore per UHD 620, gestione CPU, batteria e disabilitazione del driver NVIDIA. Spegnimento elettrico della dGPU da provare separatamente.
4. Avvio dell'installer ufficiale Apple e primo avvio di macOS.
5. Prove di grafica, audio, Wi-Fi, Bluetooth, USB, batteria, luminosità e sospensione.

La GTX 1650 non dispone di driver per macOS. Anche l'uscita HDMI potrebbe restare inutilizzabile: il precedente progetto per questo modello la indica non funzionante.

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
