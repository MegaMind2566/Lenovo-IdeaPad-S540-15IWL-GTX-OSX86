# Batteria e contatori di sospensione

Risultati ricevuti dal desktop Tahoe il 13 ottobre 2026. Il sistema è installato sul Samsung 960 EVO esterno USB; la EFI è sull'HDD OpenCore. Questa pagina conserva i dati, senza modificare le impostazioni.

## Lettura batteria

`pmset -g batt` riporta alimentazione **AC Power**, batteria interna presente, **100%** e stato **charged**. Il tempo riportato è `0:00 remaining`. Non è stato fornito un campione con alimentazione Battery Power: il passaggio a batteria, la scarica e l'autonomia non sono ancora verificati.

## Contatori del sistema

| Contatore di pmset -g stats | Valore |
|---|---|
| Sleep Count | 1 |
| Dark Wake Count | 0 |
| User Wake Count | 1 |

Sono contatori dall'avvio corrente. Documentano un evento di stop e uno di risveglio utente registrati dal sistema; non identificano l'ora della prova e non certificano da soli il recupero di pannello, dischi USB, rete e audio. L'ibernazione e lo stop prolungato restano da verificare.

## Impostazioni lette

| Impostazione | Battery Power | AC Power |
|---|---:|---:|
| standbydelayhigh | 86400 | 86400 |
| standbydelaylow | 10800 | 10800 |
| standby | 1 | 1 |
| lowpowermode | 0 | 0 |
| proximitywake | 0 | 1 |
| hibernatemode | 3 | 3 |
| powernap | 0 | 1 |
| gpuswitch | 2 | 2 |
| ttyskeepawake | 1 | 1 |
| highstandbythreshold | 50 | 50 |
| displaysleep | 2 | 10 |
| sleep | 1 | 1 |
| lessbright | 1 | non riportato |
| halfdim | 1 | 1 |
| tcpkeepalive | 1 | 1 |
| disksleep | 10 | 10 |
| womp | non riportato | 1 |
| networkoversleep | non riportato | 0 |

`hibernatefile` è `/var/vm/sleepimage` per entrambe le fonti. Le impostazioni non sono state cambiate. Il lavoro sulla sospensione è rinviato: hanno priorità il pannello spento per circa due minuti durante l'avvio, il Bluetooth e la gestione Wi-Fi.

## Riferimento

- [Manuale Apple di pmset](https://keith.github.io/xcode-man-pages/pmset.1.html): significato di letture, contatori e impostazioni.
