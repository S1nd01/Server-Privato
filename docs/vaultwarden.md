# Vaultwarden

Password manager self-hosted, compatibile con le app e le estensioni Bitwarden.

```
telefono / PC ──HTTPS (Tailscale, porta 8443)──▶ vaultwarden:80
                                                  └─ dati: $DATA_DIR/vaultwarden
```

Il proxy HTTPS è Tailscale Serve (`tailscale/serve.json`, vedi `tailscale.md`): non c'è più Caddy. L'unica porta pubblicata da
Vaultwarden è `127.0.0.1:8222` in HTTP, un'uscita di emergenza che si apre solo dal server stesso.

## Perché HTTPS è obbligatorio

Il web vault usa le API crittografiche del browser, che funzionano solo in un "secure context"
(HTTPS oppure `localhost`). Su una LAN senza HTTPS il vault si carica ma login e cifratura falliscono.
Tailscale dà un certificato valido per `<nome>.ts.net`: niente CA da installare sui dispositivi.

## Primo avvio

1. Configura Tailscale (`tailscale.md`) e abilita *HTTPS Certificates* nel suo pannello.
2. Nel `.env` metti `VW_DOMAIN=https://<nome>.<rete>.ts.net:8443` (l'indirizzo esatto lo vedi nel pannello, sezione Rete).
3. `docker compose up -d --build`
4. Apri `https://<nome>.<rete>.ts.net:8443` da un dispositivo con Tailscale acceso.

Da Windows o Linux nello stesso server puoi usare anche `http://localhost:8222`: serve se Tailscale non funziona (chiave
scaduta, rete in errore). Passkey e WebAuthn funzionano solo dall'indirizzo `.ts.net`, perché sono legati a `VW_DOMAIN`.

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

Poi `docker compose up -d vaultwarden` e apri `https://<nome>.<rete>.ts.net:8443/admin`.

## Migrare dal Bitwarden cloud

1. Dal cloud: Strumenti → Esporta cassaforte → formato **.json (protetto da password)**.
2. Sul tuo server: Strumenti → Importa dati → "Bitwarden (json)" e scegli il file (ti chiederà la password dell'export).
3. Controlla che il numero di elementi corrisponda, **poi cancella il file esportato**.
4. Sulle app/estensioni: Impostazioni → Server self-hosted → URL `https://<nome>.<rete>.ts.net:8443` e rifai il login.
5. Tieni il vault cloud fino a quando non hai verificato backup e ripristino (vedi sotto).

## Backup (non saltarlo)

`src/scripts/backup-vaultwarden.sh` crea un archivio **cifrato AES-256** `vaultwarden-AAAAMMGG-hhmmss.tar.gz.gpg`
con DB, allegati e chiavi RSA, ed elimina le copie oltre le ultime 14. Prima prova il backup online di
Vaultwarden; se non è disponibile ferma il container per qualche secondo. Dopo averlo scritto verifica che
si possa decifrare e leggere.

La passphrase sta in un file (non nella riga di comando, dove si vedrebbe con `ps`). **Non serve crearla a mano**:
l'installazione (`setup-windows.bat`, `start.sh` o `./src/scripts/sync-env.sh`) la genera in `~/.vw-backup-pass`
(permessi 600), imposta `BACKUP_PASSPHRASE_FILE` e `BACKUP_DIR` nel `.env` (`data/backups/vaultwarden`, accanto
all'archivio Restic), te la mostra una volta sola e, se vuoi, attiva il backup notturno (vedi sotto).

**Copia la passphrase anche fuori dal server** (es. nel tuo password manager *cloud*, non in questo Vaultwarden):
senza di lei i backup non si aprono più. Lo script si rifiuta di creare backup in chiaro, di usare una passphrase
sotto i 20 caratteri o un file con permessi diversi da 600.

```bash
./src/scripts/backup-vaultwarden.sh      # a mano: salva in data/backups/vaultwarden
```

Se all'installazione hai risposto sì alla domanda sul backup automatico, ogni notte alle 03:00 parte da solo
(riga nel `crontab` dell'utente, con l'esito in `data/backups/vaultwarden/backup.log`). Per attivarlo dopo:
`HS_VW_CRON=1 ./src/scripts/sync-env.sh --percorsi`, oppure a mano con `crontab -e`:
`0 3 * * * cd /percorso/homeserver && ./src/scripts/backup-vaultwarden.sh`.

Regola 3-2-1: una copia sullo stesso disco non basta. Porta periodicamente l'archivio **fuori dal server**
(altro disco o PC).

**Ripristino**:

```bash
docker compose stop vaultwarden
rm -rf "$DATA_DIR/vaultwarden"/*            # solo se vuoi sostituire tutto
gpg --batch --pinentry-mode loopback --passphrase-file ~/.vw-backup-pass -d vaultwarden-XXXX.tar.gz.gpg \
  | tar -xz -C "$DATA_DIR/vaultwarden"
docker compose start vaultwarden
```

Fai una prova di ripristino su un'altra cartella prima di fidarti del backup.

## Aggiornamenti

```bash
./src/scripts/backup-vaultwarden.sh
docker compose pull vaultwarden && docker compose up -d vaultwarden
```

L'immagine usa `latest`: per più controllo fissa una versione (es. `vaultwarden/server:1.xx.x`) in `compose.yaml`.

## Accesso da fuori casa

**Non aprire 8443 sul router.** Tailscale (vedi `tailscale.md`) lo pubblica già in HTTPS nella tua rete privata, da casa e da fuori:
nell'app Bitwarden il server è `https://<nome>.<rete>.ts.net:8443`, con Tailscale acceso sul telefono.

## Problemi comuni

| Sintomo | Causa probabile |
|---|---|
| Il sito non si apre | Tailscale spento sul dispositivo, o *HTTPS Certificates* non attivo nel pannello Tailscale |
| Login/creazione account fallisce, pagina strana | Stai usando `http://` o un indirizzo diverso da `https://<nome>.<rete>.ts.net:8443` |
| Il vault non si apre dall'app | URL del server sbagliato (manca `https://` o la porta `:8443`) |
| `/admin` risponde 404 | `ADMIN_TOKEN` vuoto, o apici mancanti nel `.env` (hash tagliato) |
| Tailscale non parte e ti serve il vault | Dal server apri `http://localhost:8222` |
