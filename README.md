# Homeserver

Pannello minimale (frontend + backend/API) per gestire un home server in Docker:

| Servizio | Cosa fa | Dettagli |
|---|---|---|
| Immich | Backup e galleria foto | [docs/immich.md](docs/immich.md) |
| Vaultwarden | Password manager (compatibile Bitwarden), dietro Caddy/HTTPS | [docs/vaultwarden.md](docs/vaultwarden.md) |
| Jellyfin | Film, serie e musica | [docs/jellyfin.md](docs/jellyfin.md) |
| Pi-hole | Blocco pubblicità e tracker (DNS) | [docs/pihole.md](docs/pihole.md) |
| Tailscale | Accesso da fuori casa, in HTTPS, senza aprire porte sul router | [docs/tailscale.md](docs/tailscale.md) |
| Restic | Backup cifrato e automatico (AES-256) | [docs/restic.md](docs/restic.md) |
| SteamCMD | Download remoto di giochi Steam | [docs/steamcmd.md](docs/steamcmd.md) |

Il pannello è anche un'app installabile sul telefono: [docs/pwa.md](docs/pwa.md).

```
homeserver/
├── backend/     FastAPI: servizi Docker, download SteamCMD, backup Restic, stato Tailscale
├── frontend/    app web (PWA) statica servita da nginx (proxy /api -> backend)
├── nginx/       configurazione di nginx (CSP e header di sicurezza)
├── tailscale/   serve.json: quali servizi sono pubblicati in HTTPS nella tua rete
├── caddy/       Caddyfile (HTTPS per Vaultwarden)
├── scripts/     gen-api-token.sh, backup-vaultwarden.sh (cifrato)
├── docs/        guide per servizio
├── compose.yaml
└── .env.example
```

## Avvio su PC Linux (branch `pc-linux`)

```bash
cp .env.example .env
# modifica .env: DATA_DIR e STEAM_GAMES_DIR (percorsi ASSOLUTI), IMMICH_DB_PASSWORD, VW_HOST...
./scripts/sync-env.sh        # completa il .env, genera la password di Pi-hole, crea le cartelle dei dati
./scripts/gen-api-token.sh   # token del pannello
docker compose up -d --build --remove-orphans
```

**Aggiornare da una versione precedente:** estrai il nuovo zip, copia dentro il tuo `.env`, poi
`./scripts/sync-env.sh` e `docker compose up -d --build --remove-orphans` (`--remove-orphans` toglie il vecchio WireGuard).

- Pannello: http://localhost:8088
- Immich: http://localhost:2283 · Jellyfin: http://localhost:8096 · Pi-hole: http://localhost:8053/admin
- Vaultwarden: https://localhost:8443 (leggi prima la sezione "Fidarsi della CA" in `docs/vaultwarden.md`)

Avvio parziale: `docker compose up -d --build frontend backend caddy vaultwarden`.

## API

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/health` | stato backend (sempre senza token) |
| GET | `/api/services` · `/api/services/{id}` | stato dei servizi Docker (`immich`, `jellyfin`, `vaultwarden`, `pihole`, `tailscale`) |
| POST | `/api/services/{id}/start` · `stop` · `restart` | azione sul servizio |
| POST/GET/DELETE | `/api/steam/downloads…` · GET `/api/steam/library` | download SteamCMD ([docs](docs/steamcmd.md)) |
| GET | `/api/tailscale/status` | stato Tailscale, indirizzo https, dispositivi |
| GET/POST | `/api/backup/status` · `/api/backup/jobs` · `/api/backup/snapshots` | backup Restic ([docs](docs/restic.md)) |

Se `API_TOKEN_HASH` è impostato, ogni chiamata (tranne health) richiede l'header `X-API-Token`.
Generalo con `./scripts/gen-api-token.sh`. Dettagli in [docs/security.md](docs/security.md).

## Sicurezza

- Il backend monta `/var/run/docker.sock`: chi controlla l'API controlla la macchina. La porta 8088 è
  pubblicata **solo su 127.0.0.1**, il token è obbligatorio (`gen-api-token.sh`) e non va mai esposta su Internet.
- I backup di Vaultwarden sono cifrati AES-256 (`BACKUP_PASSPHRASE_FILE`).
- Sul router **non si apre nessuna porta**: da fuori casa si entra con Tailscale. Le porte dei servizi sono su `127.0.0.1` (`BIND_ADDR`).

## Passaggio al Raspberry

- `DATA_DIR` sul mount dell'SSD (ext4 per i dati dei servizi).
- SteamCMD è x86: sul Pi serve emulazione, vedi [docs/steamcmd.md](docs/steamcmd.md).
- Immich consuma parecchia RAM (soprattutto `immich-machine-learning`): su un Pi con poca memoria valuta di
  disattivarlo e tieni almeno 4 GB.
