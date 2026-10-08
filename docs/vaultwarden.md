# Vaultwarden

Password manager self-hosted, compatibile con le app e le estensioni Bitwarden.

```
browser / app ──HTTPS──▶ Caddy (porta host 8443 → 443 nel container) ──HTTP──▶ vaultwarden:80
                                                                               └─ dati: $DATA_DIR/vaultwarden
```

Vaultwarden **non pubblica nessuna porta**: si arriva solo passando da Caddy, quindi solo in HTTPS.

## Perché HTTPS è obbligatorio

Il web vault usa le API crittografiche del browser, che funzionano solo in un "secure context"
(HTTPS oppure `localhost`). Su una LAN senza HTTPS il vault si carica ma login e cifratura falliscono.
Per questo c'è Caddy, con `tls internal`: genera una **CA locale** e firma il certificato per il nome in `VW_HOST`.

## Primo avvio

1. In `.env` imposta `VW_HOST` con il nome/IP con cui raggiungerai il server:
   - test sul PC: `localhost`
   - uso reale: l'IP LAN del server (meglio con prenotazione DHCP sul router) o un nome in DNS.
   Il certificato vale **solo** per quel nome: se lo cambi, `docker compose up -d caddy`.
2. `docker compose up -d --build`
3. Apri `https://<VW_HOST>:8443`. Vedrai un avviso di certificato: è normale finché non ti fidi della CA.

### Fidarsi della CA di Caddy

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

- **Linux (sistema + Chrome/Chromium)**:
  `sudo cp caddy-root.crt /usr/local/share/ca-certificates/caddy-root.crt && sudo update-ca-certificates`
- **Firefox**: Impostazioni → Privacy e sicurezza → Certificati → Mostra certificati → Autorità → Importa.
- **Windows**: doppio clic sul file → Installa → "Autorità di certificazione radice attendibili".
- **Telefono**: installa il file come certificato CA dalle impostazioni di sicurezza.
  Attenzione: alcune app Android non si fidano dei certificati CA installati dall'utente. Non l'ho verificato
  per l'app Bitwarden: se non si collega, l'alternativa solida è un dominio vero con certificato Let's Encrypt
  (togli `tls internal` dal `caddy/Caddyfile`, usa il tuo dominio in `VW_HOST` e pubblica 80/443).

Non committare `caddy-root.crt` e non cancellare il volume `caddy-data`: contiene la CA, e perderla significa
rifare la fiducia su ogni dispositivo.

## Creare l'account e chiudere le registrazioni

1. Con `VW_SIGNUPS=true` crea il **tuo** account (password master lunga e unica: non è recuperabile).
2. Imposta `VW_SIGNUPS=false` in `.env` e applica: `docker compose up -d vaultwarden`.
3. Da quel momento nessun altro può registrarsi. Se serve un secondo utente: riabilita temporaneamente.

## Autenticazione a due fattori

Impostazioni → Sicurezza → Verifica in due passaggi → **App di autenticazione**. Scansiona il QR con la tua
app TOTP (Authy va bene, come qualsiasi altra). **Salva subito il codice di recupero** su carta o fuori dal server.

## Pannello /admin (opzionale)

Serve per vedere utenti, cambiare impostazioni, fare diagnostica. Disattivo finché `ADMIN_TOKEN` è vuoto.

```bash
docker run --rm -it vaultwarden/server /vaultwarden hash
```

Inserisci una password lunga, copia l'hash `$argon2id$...` e mettilo in `.env` **tra apici singoli**
(contiene dei `$`, che Compose altrimenti interpreta):

```
ADMIN_TOKEN='$argon2id$v=19$m=65540,t=3,p=4$...'
```

Poi `docker compose up -d vaultwarden` e apri `https://<VW_HOST>:8443/admin`.

## Migrare dal Bitwarden cloud

1. Dal cloud: Strumenti → Esporta cassaforte → formato **.json (protetto da password)**.
2. Sul tuo server: Strumenti → Importa dati → "Bitwarden (json)" e scegli il file (ti chiederà la password dell'export).
3. Controlla che il numero di elementi corrisponda, **poi cancella il file esportato**.
4. Sulle app/estensioni: Impostazioni → Server self-hosted → URL `https://<VW_HOST>:8443` e rifai il login.
5. Tieni il vault cloud fino a quando non hai verificato backup e ripristino (vedi sotto).

## Backup (non saltarlo)

`scripts/backup-vaultwarden.sh` crea un archivio `vaultwarden-AAAAMMGG-hhmmss.tar.gz` con DB, allegati e chiavi RSA,
ed elimina le copie oltre le ultime 14. Prima prova il backup online di Vaultwarden; se non è disponibile ferma
il container per qualche secondo.

```bash
BACKUP_DIR=/mnt/ssd/backups ./scripts/backup-vaultwarden.sh
# ogni notte alle 03:00:  crontab -e
0 3 * * * cd /percorso/homeserver && BACKUP_DIR=/mnt/ssd/backups ./scripts/backup-vaultwarden.sh
```

Regola 3-2-1: una copia sullo stesso disco non basta. Porta periodicamente l'archivio **fuori dal server**
(altro disco o PC). Il contenuto è cifrato dalla tua password master, ma contiene anche le chiavi del server.

**Ripristino**:

```bash
docker compose stop vaultwarden
rm -rf "$DATA_DIR/vaultwarden"/*            # solo se vuoi sostituire tutto
tar -xzf vaultwarden-XXXX.tar.gz -C "$DATA_DIR/vaultwarden"
docker compose start vaultwarden
```

Fai una prova di ripristino su un'altra cartella prima di fidarti del backup.

## Aggiornamenti

```bash
./scripts/backup-vaultwarden.sh
docker compose pull vaultwarden caddy && docker compose up -d vaultwarden caddy
```

L'immagine usa `latest`: per più controllo fissa una versione (es. `vaultwarden/server:1.xx.x`) in `compose.yaml`.

## Accesso da fuori casa

**Non aprire 8443 sul router.** Entra con WireGuard (vedi `wireguard.md`): con lo split tunnel di default la LAN
è raggiungibile, quindi se `VW_HOST` è l'IP LAN del server lo stesso indirizzo funziona dentro e fuori casa.

## Problemi comuni

| Sintomo | Causa probabile |
|---|---|
| "Connessione non sicura" | CA di Caddy non installata sul dispositivo/browser |
| Login/creazione account fallisce, pagina strana | Stai usando `http://` o un nome diverso da `VW_HOST` |
| Il vault non si apre dall'app | URL del server sbagliato (manca `https://` o la porta `:8443`) |
| `/admin` risponde 404 | `ADMIN_TOKEN` vuoto, o apici mancanti nel `.env` (hash tagliato) |
| Dopo `down -v` i dispositivi non si fidano più | Hai cancellato `caddy-data`: nuova CA, reinstallala |
