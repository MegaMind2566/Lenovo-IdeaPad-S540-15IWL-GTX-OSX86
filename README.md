# Lenovo IdeaPad S540-15IWL GTX — macOS Tahoe

Progetto OpenCore per usare **macOS Tahoe 26** sul Lenovo IdeaPad S540-15IWL GTX e rendere utilizzabili i suoi componenti. Il lavoro comprende configurazione di avvio, patch mirate, strumenti diagnostici e procedure di ripristino.

**Stato al 14 ottobre 2026:** Tahoe raggiunge il desktop con accelerazione Intel. Audio, volume, rete e webcam hanno già dato esiti positivi. La correzione del microfono ha un primo riscontro positivo; la compatibilità completa e la stabilità prolungata restano da verificare.

## Hardware di riferimento

- Lenovo IdeaPad S540-15IWL GTX, famiglia **81SW**.
- Intel Core i7-8565U, 12 GB DDR4, Intel UHD 620 e NVIDIA GTX 1650 Max-Q da 4 GB.
- Display interno Full HD, audio Realtek ALC257, Wi-Fi/Bluetooth Intel AC9560 e touchpad ELAN0662.
- Tahoe sul **Samsung 960 EVO esterno USB-C**; OpenCore sull'HDD USB di avvio.
- SSD interno Samsung PM981a conservato per Windows.

Identificativi, BIOS e dettagli delle periferiche sono in [HARDWARE.md](docs/HARDWARE.md). Gli esiti riguardano questa macchina e questa configurazione.

## Stato dei componenti

«Report» indica dati acquisiti dal sistema; «prova d'uso» indica un esito riferito sul portatile. Un esito positivo copre la funzione provata, non tutte le modalità d'uso della periferica.

| Componente | Risultato attuale | Evidenza e limite |
|---|---|---|
| Avvio Tahoe | Desktop sul 960 EVO esterno | Prova d'uso; riavvii e uso prolungato da consolidare |
| Intel UHD 620 | IntelAccelerator, Metal 3, memoria condivisa fino a 1536 MB | Report acquisiti; carico Metal prolungato da provare |
| Display | 1920×1080; cursore luminosità funzionante; ritardo nero eliminato con `-igfxblr` | Report e prove d'uso; F11/F12 rinviati |
| CPU e ventole | X86PlatformPlugin attivo; riposo 45–46 °C e 0,80–0,95 W Intel stimati; ventola riferita silenziosa | Due campioni a riposo; carico e consumo totale da verificare |
| Audio e volume | Riproduzione, volume graduale e F1–F3 funzionanti | Prova d'uso con VoodooHDA e correzione volume; jack da provare |
| Microfono interno | Voce acquisita; correzione v2 con primo riscontro positivo dopo il riavvio | Report della verifica e registrazioni di confronto ancora da acquisire |
| Wi-Fi | itlwm caricato e HeliPort funzionante | Report e prova d'uso; velocità e riconnessione da provare |
| Bluetooth | Audio nelle cuffie funzionante | Prova d'uso; microfono delle cuffie e riconnessione da provare |
| Webcam | Immagine presente in Photo Booth | Prova d'uso; uso prolungato e ripresa da provare |
| Touchpad | ELAN0662 e percorso I2C identificati | Puntamento, clic, scorrimento e gesti da verificare separatamente |
| USB e SSD esterno | Mappa a 9 porte verificata; SSD rilevato e usato per Tahoe | SuperSpeed, orientazioni USB-C e disconnessioni da verificare |
| Batteria e sospensione | Batteria rilevata su alimentatore; contatori di stop presenti | Autonomia e recupero delle periferiche non verificati; prove di stop rinviate |
| NVIDIA e uscite video | Driver NVIDIA escluso; GTX 1650 senza accelerazione nella configurazione attuale | Spegnimento elettrico, HDMI e video USB-C da verificare; port Linux in ricerca |
| Lettore SD e impronte | Periferiche identificate | Supporto e funzionamento da valutare |

## Prossimo lavoro

1. Consolidare la configurazione attuale e completare le verifiche della correzione microfono.
2. Provare stabilità Intel, touchpad, velocità rete e porte USB.
3. Verificare temperature sotto carico, passaggio a batteria e autonomia.
4. Affrontare più avanti equalizzazione e tasti funzione, poi sospensione e ripresa.
5. Provare l'avvio dal solo 960 EVO dopo il trasferimento della EFI, conservando il supporto attuale.
6. Proseguire la ricerca NVIDIA e la verifica delle uscite video.

La [roadmap](docs/ROADMAP.md) contiene criteri e prove mancanti. Il port dei driver NVIDIA Linux resta un obiettivo di ricerca, senza una soluzione macOS già disponibile nel progetto. Sequoia resta un'alternativa da valutare.

## Guide, download e build

Partire dall'[indice delle guide](docs/README.md), che distingue le procedure attuali dalle prove precedenti.

- [Grafica Intel e configurazione funzionante](docs/GRAFICA-INTEL.md).
- [Installazione e ripristino audio Tahoe](docs/AUDIO-TAHOE.md).
- [Correzione microfono v2 e verifica](docs/MICROFONO-FIX.md).
- [Installazione sul disco esterno](docs/INSTALLAZIONE.md).

I pacchetti prodotti dalla CI sono disponibili negli **Artifacts** delle esecuzioni riuscite di [GitHub Actions](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/actions). Il pacchetto microfono corrente è `S540-microfono-fix-v2`; istruzioni e requisiti sono nella sua guida. **Code → Download ZIP** scarica i sorgenti della repository.

La [build EFI](archive/efi-iniziale/workflows/build-efi.yml) genera una configurazione di **prima prova**, precedente agli interventi verificati sul portatile. La [build microfono](.github/workflows/build-audio-microphone.yml) compila la variante S540 di VoodooHDA su macOS Intel e ne verifica integrità, firma e ripristino. I test CI non caricano il driver nel kernel del portatile.

Per il sistema già funzionante, seguire le procedure mirate delle guide e conservare i backup privati. La EFI reale, le identità SMBIOS, le credenziali Wi-Fi e i report originali restano fuori dalla repository.

## Struttura

| Percorso | Contenuto |
|---|---|
| [docs/](docs/README.md) | Guide attuali, stato hardware e roadmap |
| [acpi/](acpi) | Sorgenti SSDT e tabelle compilate |
| [profiles/](profiles) | Profilo hardware e versioni degli asset fissate |
| [usb/](usb) | Mappatura delle porte USB |
| [patches/](patches) | Modifiche al sorgente dei driver |
| [tools/](tools) | Builder, verifiche e strumenti di raccolta |
| [.github/workflows/](.github/workflows) | Compilazione e controlli automatici |
| [archive/](archive/README.md) | Diagnosi e procedure precedenti, conservate per consultazione |

## Riferimenti

- [Dortania: Coffee Lake e Whiskey Lake portatili](https://dortania.github.io/OpenCore-Install-Guide/config-laptop.plist/coffee-lake.html).
- [Dortania: macOS Tahoe](https://dortania.github.io/OpenCore-Install-Guide/extras/tahoe.html).
- [OpenIntelWireless](https://github.com/OpenIntelWireless/itlwm).
- [VoodooHDA](https://github.com/CloverHackyColor/VoodooHDA): la variante microfono S540 è una modifica del progetto, non una release ufficiale upstream.
