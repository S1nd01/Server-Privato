# Notifiche su Telegram

Il container `ntfy-telegram` (script in `src/telegram/`) inoltra al tuo Telegram ogni messaggio che arriva su un argomento di [ntfy](ntfy.md): Uptime Kuma, Radarr, Sonarr, Diun e tutto ciò che già scrive su ntfy. L'app ntfy continua a funzionare; Telegram è un secondo canale, utile quando il telefono non ha Tailscale acceso.

```
servizi ──► ntfy ──► ntfy-telegram ──► api.telegram.org ──► il tuo Telegram
                      (solo in uscita)
```

## Cosa fa e cosa non fa

- **Solo in uscita.** Nessuna porta pubblicata, nessun socket Docker. Il ponte **non legge i messaggi che arrivano al bot**: scrivere al bot non fa fare nulla al server. Un bot con comandi (`/riavvia`, `/stato`) è stato scartato di proposito: richiederebbe un'autenticazione sul canale Telegram che oggi il pannello non ha.
- **Testo semplice.** Nessuna formattazione (`parse_mode`): un titolo o un messaggio con caratteri speciali non può rompere l'invio né iniettare markup. Priorità 4 e 5 hanno un prefisso (⚠️, 🚨); l'eventuale link `click` è accodato.
- **Non perde messaggi.** Il ponte ricorda l'ultimo messaggio inoltrato (`data/telegram/state/cursor`): dopo un riavvio, o se Telegram è irraggiungibile, riprende da lì. Al **primo** avvio inoltra solo i messaggi da quel momento in poi.
- **Limite.** Al massimo 15 messaggi al minuto (`MAX_PER_MIN`), distanziati di circa un secondo. Una raffica (per esempio un servizio che va in loop) diventa un solo messaggio «N notifiche non inoltrate»; le trovi comunque nell'app ntfy.
- **Risorse.** Immagine `python:3.12-alpine`, solo libreria standard, 64 MB di RAM, `read_only`, `cap_drop: ALL`, `no-new-privileges`. Sta solo nella rete `notify`.

## Attivazione

1. Su Telegram, con **@BotFather**: `/newbot`, scegli nome e username. Copia il token (formato `123456789:AA...`).
2. Dal tuo account, apri il bot e scrivigli `/start`.
3. Sul server, **senza `sudo`**:

   ```bash
   ./src/scripts/telegram-setup.sh
   ```

   Lo script:
   1. chiede il token (non viene mostrato) e lo verifica con Telegram;
   2. ricava il tuo chat ID dai messaggi mandati al bot e **ti chiede conferma** del nome trovato (il bot è pubblico: se un estraneo gli ha scritto prima di te, lo vedi e scegli);
   3. ti scrive un messaggio di prova;
   4. crea in ntfy l'utente `telegram` con permesso di **sola lettura** sull'argomento e ne salva il token;
   5. scrive `TELEGRAM_CHAT_ID` nel `.env` e avvia il container.
4. Prova: `docker compose exec ntfy ntfy publish -u IL_TUO_NOME homeserver "Prova"`. Il messaggio deve arrivare sia nell'app ntfy sia su Telegram.

Si può rilanciare: riusa ciò che esiste. `--da-capo` chiede di nuovo il token, rifà il chat ID e rigenera l'utente ntfy.

Il ponte ha un profilo Compose a parte: `docker compose up` da solo non lo avvia, ma `./src/scripts/start.sh` abilita il profilo negli avvii completi se trova il chat ID e i due file dei token. Dal pannello compare come «Notifiche Telegram» (gruppo utility).

## Configurazione

| Variabile `.env` | Significato |
|---|---|
| `TELEGRAM_CHAT_ID` | Il tuo chat ID (lo scrive lo script) |
| `TELEGRAM_NTFY_TOPIC` | Argomento da inoltrare, o più argomenti separati da virgola (di serie `homeserver`). Se lo cambi, rilancia `telegram-setup.sh --da-capo`: l'utente ntfy ha il permesso solo sugli argomenti di allora |
| `TELEGRAM_BRIDGE_IMAGE` | Versione fissa dell'immagine ([manutenzione.md](manutenzione.md)) |

## Sicurezza

| Cosa | Come è trattato |
|---|---|
| Token del bot | `data/telegram/telegram_bot_token`, permessi `600`, cartella `700`, montata **in sola lettura** nel container. Non sta nel `.env`, nelle variabili d'ambiente, nella riga di comando (lo script lo passa a `curl` da stdin) né nei log: il ponte lo cancella anche dai messaggi d'errore |
| Accesso a ntfy | Utente `telegram` con token e permesso **di sola lettura**: chi ottenesse quel token non potrebbe pubblicare notifiche false |
| Destinatario | Un solo chat ID, scritto dallo script solo dopo la tua conferma |
| Contenuto | **Telegram non è cifrato end-to-end** per i bot: il testo di ogni notifica passa dai server di Telegram. Per questo conviene che le notifiche dicano *cosa* è successo (un servizio è giù, c'è un aggiornamento) e non portino dati sensibili: password, indirizzi privati, nomi di file personali |
| Se il token trapela | In @BotFather: `/revoke` sul bot, poi `./src/scripts/telegram-setup.sh --da-capo` |

## Backup

`data/telegram` **non** è nel backup Restic: contiene solo segreti che si rigenerano (token del bot da @BotFather, utente ntfy da `telegram-setup.sh --da-capo`). Dopo un ripristino su una macchina nuova basta rilanciare lo script.

## Problemi

| Sintomo | Causa e rimedio |
|---|---|
| Lo script dice che il bot non ha messaggi | Scrivi `/start` al bot e rilancia |
| `permission denied` sui segreti nel log | I file sono di root (script lanciato con `sudo`): `sudo chown -R "$USER": data/telegram` e rilancia lo script |
| `ntfy ha risposto HTTP 401/403` | Il token ntfy è stato revocato o l'argomento è cambiato: `telegram-setup.sh --da-capo` |
| `Telegram ha rifiutato il messaggio (HTTP 403)` | Hai bloccato il bot, o il chat ID è sbagliato: sbloccalo, scrivi `/start`, `--da-capo` |
| Nessun messaggio ma il container è `healthy` | Il controllo di salute misura la connessione a ntfy. Per verificare anche la consegna a Telegram, usa il pulsante Test di Kuma. Controlla che il servizio mandi davvero a ntfy (argomento giusto) e `docker compose logs ntfy-telegram` |
| Container `unhealthy` | Non vede più ntfy da 3 minuti; Autoheal lo riavvia. Se persiste, `docker compose logs ntfy ntfy-telegram` |
