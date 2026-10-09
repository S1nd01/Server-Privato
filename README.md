# Homeserver

Pannello minimale (frontend + backend/API) per gestire un home server in Docker:

| Servizio | Cosa fa | Dettagli |
|---|---|---|
| Immich | Backup e galleria foto | [docs/immich.md](docs/immich.md) |
| Vaultwarden | Password manager (compatibile Bitwarden), dietro Caddy/HTTPS | [docs/vaultwarden.md](docs/vaultwarden.md) |
| WireGuard | VPN per l'accesso da fuori casa | [docs/wireguard.md](docs/wireguard.md) |
| SteamCMD | Download remoto di giochi Steam | [docs/steamcmd.md](docs/steamcmd.md) |

```
homeserver/
├── backend/     FastAPI: servizi Docker, download SteamCMD, stato WireGuard
├── frontend/    HTML+JS statico servito da nginx (proxy /api -> backend)
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
# (Docker crea le cartelle mancanti, ma come root: meglio crearle prima col tuo utente)
docker compose up -d --build
```

- Pannello: http://localhost:8088
- Immich: http://localhost:2283
- Vaultwarden: https://localhost:8443 (leggi prima la sezione "Fidarsi della CA" in `docs/vaultwarden.md`)

Avvio parziale: `docker compose up -d --build frontend backend caddy vaultwarden`.

## API

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/health` | stato backend (sempre senza token) |
| GET | `/api/services` · `/api/services/{id}` | stato dei servizi Docker (`immich`, `vaultwarden`, `wireguard`) |
| POST | `/api/services/{id}/start` · `stop` · `restart` | azione sul servizio |
| POST/GET/DELETE | `/api/steam/downloads…` · GET `/api/steam/library` | download SteamCMD ([docs](docs/steamcmd.md)) |
| GET | `/api/wireguard/status` · `/api/wireguard/peers` | stato VPN e peer |
| GET | `/api/wireguard/peers/{nome}/qr` · `/conf` | solo con `WG_EXPOSE_PEERS=true` |

Se `API_TOKEN_HASH` è impostato, ogni chiamata (tranne health) richiede l'header `X-API-Token`.
Generalo con `./scripts/gen-api-token.sh`. Dettagli in [docs/security.md](docs/security.md).

## Sicurezza

- Il backend monta `/var/run/docker.sock`: chi controlla l'API controlla la macchina. La porta 8088 è
  pubblicata **solo su 127.0.0.1**, il token è obbligatorio (`gen-api-token.sh`) e non va mai esposta su Internet.
- I backup di Vaultwarden sono cifrati AES-256 (`BACKUP_PASSPHRASE_FILE`).
- Sul router apri solo `51820/udp` (WireGuard).

## Passaggio al Raspberry

- `DATA_DIR` sul mount dell'SSD (ext4 per i dati dei servizi).
- SteamCMD è x86: sul Pi serve emulazione, vedi [docs/steamcmd.md](docs/steamcmd.md).
- Immich consuma parecchia RAM (soprattutto `immich-machine-learning`): su un Pi con poca memoria valuta di
  disattivarlo e tieni almeno 4 GB.
