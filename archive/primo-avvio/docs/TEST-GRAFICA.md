# Test grafico per il blocco della Recovery

Nei primi due tentativi la Recovery ha caricato il kernel ed eseguito servizi utente, ma non ha mostrato la schermata grafica. Le foto riportano `IOG flags 0x3 (0x51)` e messaggi di launchd. Non mostrano un kernel panic né identificano una causa unica. Il disco di avvio è un HDD USB; è stata riferita assenza di attività e ventola al massimo.

Questa prova aggiunge **solo `-igfxvesa`** ai boot-args. WhateverGreen usa questa opzione per disabilitare l'accelerazione grafica Intel. Serve a verificare se la Recovery riesce a mostrare la propria interfaccia in modalità di base. Non è la configurazione finale per l'uso di macOS.

## Come applicare il test da Windows

1. Avvia Windows dal menu Lenovo.
2. Estrai `S540-test-grafica.zip` **nella radice dell'HDD usato per avviare la Recovery**, dove sono già presenti `EFI` e `com.apple.recovery.boot`.
3. Deve risultare `TEST-GRAFICA.cmd` accanto alla cartella `EFI`, e `tools/test_graphics.py` nella cartella `tools` dello stesso disco.
4. Premi due volte **TEST-GRAFICA.cmd**. Serve lo stesso Python 3 usato per scaricare la Recovery. Attendi il messaggio **Test grafica attivato**.
5. Riavvia OpenCore e seleziona di nuovo la Recovery. Se raggiungi le Utility macOS, segnala l'esito e fermati prima di inizializzare il disco di destinazione.

Lo script modifica il `config.plist` già presente sul disco, preservando gli identificativi SMBIOS e tutte le altre impostazioni. Il profilo Wi-Fi resta nel proprio kext. Il backup è `EFI/OC/config.before-graphics-test.plist`.

Per tornare alla configurazione precedente, avvia **RIPRISTINA-GRAFICA.cmd**. Il ripristino rifiuta di sovrascrivere una configurazione che contiene ulteriori modifiche.

## Come leggere il risultato

- Se compare l'interfaccia grafica, il risultato restringe l'indagine al percorso della grafica accelerata. DVMT, piattaforma framebuffer e proprietà della UHD 620 saranno verificati nel passo successivo.
- Se si ferma ancora, invia una foto delle ultime righe e il log `opencore-*.txt` dalla radice del disco di avvio. Quel log riguarda OpenCore e le estensioni iniettate; non sostituisce il log completo di macOS.
- Il test non deve formattare il disco o scaricare di nuovo la Recovery. Le prestazioni grafiche possono essere basse perché l'accelerazione è temporaneamente disabilitata.

Riferimento: [WhateverGreen 1.7.1, opzioni per Intel](https://github.com/acidanthera/WhateverGreen/blob/1.7.1/README.md#intel-hd-graphics).
