# Homeserver

Pannello minimale (frontend + backend/API) per gestire un home server in Docker:

| Servizio | Cosa fa | Dettagli |
|---|---|---|
| Immich | Backup e galleria foto | [docs/immich.md](docs/immich.md) |
| Vaultwarden | Password manager (compatibile Bitwarden), dietro Caddy/HTTPS | [docs/vaultwarden.md](docs/vaultwarden.md) |
| Jellyfin | Film, serie e musica | [docs/jellyfin.md](docs/jellyfin.md) |
| Seerr + JellyBridge | Richieste di film e serie direttamente da Jellyfin | [docs/seerr.md](docs/seerr.md) |
| Radarr, Sonarr, Prowlarr, qBittorrent | Scaricano ciò che viene richiesto in Seerr | [docs/seerr.md](docs/seerr.md) |
| Pi-hole | Blocco pubblicità e tracker (DNS) | [docs/pihole.md](docs/pihole.md) |
| Tailscale | Accesso da fuori casa, in HTTPS, senza aprire porte sul router | [docs/tailscale.md](docs/tailscale.md) |
| Restic | Backup cifrato e automatico (AES-256) | [docs/restic.md](docs/restic.md) |
| SteamCMD | Download remoto di giochi Steam | [docs/steamcmd.md](docs/steamcmd.md) |

Il pannello è anche un'app installabile sul telefono: [docs/pwa.md](docs/pwa.md).

```
homeserver/
├── src/
│   ├── backend/   FastAPI: servizi Docker, download SteamCMD, backup Restic, stato Tailscale
│   ├── frontend/  app web (PWA) statica servita da nginx (proxy /api -> backend)
│   └── scripts/   start.sh, sync-env.sh, gen-api-token.sh, backup-vaultwarden.sh (cifrato), install-linux.sh
├── nginx/       configurazione di nginx (CSP e header di sicurezza)
├── tailscale/   serve.json: quali servizi sono pubblicati in HTTPS nella tua rete
├── caddy/       Caddyfile (HTTPS per Vaultwarden)
├── docs/        guide per servizio
├── data/        dati persistenti, librerie, giochi Steam e backup (creata all'avvio)
├── compose.yaml
└── .env.example
```

## Windows (installazione automatica)

Doppio clic su `setup-windows.bat` (guida: [docs/windows.md](docs/windows.md), con anche lo spostamento su SSD esterno e la RAM).

## Avvio su PC Linux (branch `pc-linux`)

```bash
./src/scripts/gen-api-token.sh   # token del pannello (una volta sola)
./src/scripts/start.sh           # prepara tutto e avvia i container
```

Non serve toccare il `.env`: la prima volta `start.sh` (tramite `sync-env.sh`) lo crea e prepara tutte le directory
in `data/` dentro il progetto. Servizi, foto, media, giochi Steam e backup non hanno percorsi configurabili
dall'utente.

- La prima volta imposta anche i **backup** in `data/backups/`, genera le passphrase di Restic e di Vaultwarden
  (le mostra **una volta sola**: copiale fuori dal server) e, se vuoi, attiva il backup notturno di Vaultwarden.
  Dopo, nel pannello, sezione Backup, premi *Prepara l'archivio*. Vedi [docs/restic.md](docs/restic.md).
- `./src/scripts/sync-env.sh --percorsi` riallinea il `.env` ai percorsi fissi in `data/`; non sposta dati già esistenti
  e lascia invariate le passphrase già create.
- Se le cartelle dei dati mancano o non sono tue (di solito perché hai lanciato `docker compose up` a mano), il pannello
  mostra un avviso e basta rilanciare `./src/scripts/sync-env.sh`. Con i percorsi non ancora scelti, `docker compose`
  si ferma con lo stesso consiglio.

**Aggiornare da una versione precedente:** estrai il nuovo zip, copia dentro il tuo `.env`, poi `./src/scripts/start.sh`
(`--remove-orphans` toglie il vecchio WireGuard). Lo script riallinea i percorsi a `data/`, ma **non sposta**
automaticamente dati o archivi che si trovano altrove: copia i dati a servizi fermi dopo aver verificato il messaggio
di avviso. La CA locale di Caddy usata dalle versioni precedenti nei volumi Docker non viene trasferita; dopo
l'aggiornamento potrebbe essere necessario fidarsi nuovamente della CA sui dispositivi.

- Pannello: http://localhost:8088
- Immich: http://localhost:2283 · Jellyfin: http://localhost:8096 · Pi-hole: http://localhost:8053/admin
- Seerr: http://localhost:5055 · Radarr: :7878 · Sonarr: :8989 · Prowlarr: :9696 · qBittorrent: :8080 (configurazione in [docs/seerr.md](docs/seerr.md))
- Vaultwarden: https://localhost:8443 (leggi prima la sezione "Fidarsi della CA" in `docs/vaultwarden.md`)

Avvio parziale: `docker compose up -d --build frontend backend caddy vaultwarden`.

## API

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/health` | stato backend (sempre senza token) |
| GET | `/api/services` · `/api/services/{id}` | stato dei servizi Docker (`immich`, `jellyfin`, `seerr`, `download`, `vaultwarden`, `pihole`, `tailscale`) |
| POST | `/api/services/{id}/start` · `stop` · `restart` | azione sul servizio |
| GET | `/api/stats` | uso di risorse: server (CPU, RAM, dischi, temperatura) e per servizio (CPU, RAM, tempo di attività, salute, riavvii); `setup` segnala cartelle dei dati mancanti |
| POST/GET/DELETE | `/api/steam/downloads…` · GET `/api/steam/library` | download SteamCMD ([docs](docs/steamcmd.md)) |
| GET | `/api/tailscale/status` | stato Tailscale, indirizzo https, dispositivi |
| GET/POST | `/api/backup/status` · `/api/backup/jobs` · `/api/backup/snapshots` | backup Restic ([docs](docs/restic.md)) |

Se `API_TOKEN_HASH` è impostato, ogni chiamata (tranne health) richiede l'header `X-API-Token`.
Generalo con `./src/scripts/gen-api-token.sh`. Dettagli in [docs/security.md](docs/security.md).

## Sicurezza

- Il backend monta `/var/run/docker.sock`: chi controlla l'API controlla la macchina. La porta 8088 è
  pubblicata **solo su 127.0.0.1**, il token è obbligatorio (`gen-api-token.sh`) e non va mai esposta su Internet.
- I backup di Vaultwarden sono cifrati AES-256 (`BACKUP_PASSPHRASE_FILE`).
- Sul router **non si apre nessuna porta**: da fuori casa si entra con Tailscale. Le porte dei servizi sono su `127.0.0.1` (`BIND_ADDR`).

## Passaggio al Raspberry

- Tutti i dati restano in `data/` dentro il progetto sul filesystem Linux (ext4).
- SteamCMD è x86: sul Pi serve emulazione, vedi [docs/steamcmd.md](docs/steamcmd.md).
- Radarr, Sonarr, Prowlarr e qBittorrent occupano circa 1-1,5 GB di RAM insieme: dal pannello si spengono con un solo
  interruttore (**Download automatici**), vedi [docs/seerr.md](docs/seerr.md).
- Immich consuma parecchia RAM (soprattutto `immich-machine-learning`): su un Pi con poca memoria valuta di
  disattivarlo e tieni almeno 4 GB.
