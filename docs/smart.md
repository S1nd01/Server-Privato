# Controllo dei dischi (SMART)

I dischi avvisano prima di rompersi, se qualcuno li ascolta. `./src/scripts/smart-check.sh` legge i dati SMART e ti manda un avviso su ntfy (e quindi su Telegram, se l'hai collegato) quando c'è qualcosa da guardare.

Gira **sul computer, non in un container**: Scrutiny (l'alternativa più nota) è comoda ma porta un database, un servizio in più in RAM e un container con accesso diretto ai dischi; per un solo server basta lo script.

## Installazione

```bash
sudo apt install smartmontools
# col tuo utente, senza password per smartctl (visudo -f /etc/sudoers.d/smartctl):
#   TUOUTENTE ALL=(root) NOPASSWD: /usr/sbin/smartctl
./src/scripts/smart-check.sh --stampa     # prova senza mandare nulla
./src/scripts/smart-check.sh --test       # avviso di prova su ntfy
```

Gli avvisi usano lo stesso utente e la stessa password di Diun (`DIUN_NTFY_USER` / `DIUN_NTFY_PASSWORD` nel `.env`) e l'argomento `SMART_NTFY_TOPIC`. Pianificalo ogni giorno (cron col tuo utente):
```
30 6 * * *  cd /percorso/del/progetto && ./src/scripts/smart-check.sh >> /tmp/smart-check.log 2>&1
```

## Cosa segnala

| Livello | Quando |
|---|---|
| **GUASTO** (priorità alta) | esito SMART non «PASSED»; guasto imminente o attributo sotto soglia; settori in attesa o non correggibili; NVMe con avviso critico o riserva esaurita |
| **ATTENZIONE** | settori riallocati (il disco si consuma: grave se il numero cresce); errori nel registro o nei test; temperatura oltre `SMART_TEMP_WARN` (55 °C); usura NVMe al 90% |
| **ERRORE** | non riesce a leggere un disco (permessi, disco assente, ponte USB senza SMART) |

L'avviso identico non si ripete per 7 giorni (`--forza` per rimandarlo). Uscita: 0 tutto bene, 1 qualcosa da guardare, 2 errore dello script.
`SMART_DEVICES` nel `.env` limita i dischi controllati (per esempio `/dev/sda`); vuoto = tutti quelli che trova `smartctl --scan`.

## Limiti

- **La scheda SD del Raspberry non ha SMART**: se il sistema sta su SD, questo script non la vede. Per le SD conviene tenere poche scritture (log in RAM) e un'immagine di riserva, oppure far partire il sistema da SSD.
- Alcuni adattatori **USB** non passano i comandi SMART: lo script riprova con `-d sat`; se nemmeno così risponde, quel disco non è controllabile da qui (lo vedrai come ERRORE, non come «tutto bene»).
- SMART non prevede tutto: molti dischi si rompono senza segnali. Non sostituisce il backup (e quello fuori sede: [backup-remoto.md](backup-remoto.md)).

## Cosa non è provato

Ho provato la logica con un `smartctl` simulato (SATA sano, SATA con settori in attesa e temperatura alta, disco in guasto, NVMe con avviso critico, disco assente, nessun `smartctl`, deduplica degli avvisi). Non l'ho provato su dischi veri: alla prima esecuzione confronta l'uscita con `sudo smartctl -a /dev/sdX`.
