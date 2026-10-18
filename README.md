# Homeserver

Pannello minimale (frontend + backend/API) per gestire un home server in Docker:

| Servizio | Cosa fa | Dettagli |
|---|---|---|
| Immich | Backup e galleria foto | [docs/immich.md](docs/immich.md) |
| Vaultwarden | Password manager (compatibile Bitwarden), in HTTPS da Tailscale | [docs/vaultwarden.md](docs/vaultwarden.md) |
| Jellyfin | Film, serie e musica | [docs/jellyfin.md](docs/jellyfin.md) |
| Seerr + JellyBridge | Richieste di film e serie direttamente da Jellyfin | [docs/seerr.md](docs/seerr.md) |
| Radarr, Sonarr, Prowlarr, qBittorrent | Scaricano ciò che viene richiesto in Seerr | [docs/seerr.md](docs/seerr.md) |
| Bazarr, FlareSolverr | Sottotitoli automatici; browser per gli indexer protetti da Cloudflare | [docs/bazarr.md](docs/bazarr.md) |
| Uptime Kuma | Controlla che i servizi rispondano e ti avvisa | [docs/uptime-kuma.md](docs/uptime-kuma.md) |
| ntfy | Notifiche push sul telefono | [docs/ntfy.md](docs/ntfy.md) |
| Pi-hole | Blocco pubblicità e tracker (DNS) | [docs/pihole.md](docs/pihole.md) |
| Tailscale | Unico proxy: accesso da telefono e PC, in HTTPS, senza aprire porte sul router | [docs/tailscale.md](docs/tailscale.md) |
| Portainer | Gestione grafica di Docker (container, log, volumi) | [docs/portainer.md](docs/portainer.md) |
| Restic | Backup cifrato e automatico (AES-256) | [docs/restic.md](docs/restic.md) |

Il pannello è anche un'app installabile sul telefono: [docs/pwa.md](docs/pwa.md). Come tenere basso il consumo di RAM e CPU: [docs/ottimizzazione.md](docs/ottimizzazione.md).

```
homeserver/
├── src/
│   ├── backend/   FastAPI: servizi Docker, backup Restic, stato Tailscale
│   ├── frontend/  app web (PWA) statica servita da nginx (proxy /api -> backend)
│   └── scripts/   start.sh, sync-env.sh, gen-api-token.sh, backup-vaultwarden.sh (cifrato), install-linux.sh
├── nginx/       configurazione di nginx (serve solo il pannello: CSP e header di sicurezza)
├── tailscale/   serve.json: quali servizi sono pubblicati in HTTPS nella tua rete (l'unico proxy)
├── docs/        guide per servizio
├── data/        dati persistenti, librerie e backup (creata all'avvio)
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
in `data/` dentro il progetto. Servizi, foto, media e backup non hanno percorsi configurabili
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
di avviso. Caddy non c'e' piu': Vaultwarden si apre da `https://<nome>.ts.net:8443` (vedi `docs/vaultwarden.md`), quindi la CA
di Caddy sui dispositivi non serve piu' e la cartella `data/caddy` si puo' cancellare. Se avevi gia' Portainer in
`homeserver-data/portainer`, copia il contenuto in `data/portainer` (vedi `docs/portainer.md`).

- Pannello: http://localhost:8088
- Immich: http://localhost:2283 · Jellyfin: http://localhost:8096 · Pi-hole: http://localhost:8053/admin
- Seerr: http://localhost:5055 · Radarr: :7878 · Sonarr: :8989 · Prowlarr: :9696 · qBittorrent: :8080 · Bazarr: :6767 (configurazione in [docs/seerr.md](docs/seerr.md) e [docs/bazarr.md](docs/bazarr.md))
- Uptime Kuma: http://localhost:3001 · ntfy: http://localhost:2586
- Vaultwarden: da Tailscale `https://<nome>.ts.net:8443`; dal server, per emergenza, http://localhost:8222 (`docs/vaultwarden.md`)
- Portainer: https://localhost:9443 (certificato autofirmato) o `https://<nome>.ts.net:9443` ([docs/portainer.md](docs/portainer.md))

Avvio parziale: `docker compose up -d --build frontend backend vaultwarden`.

## API

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/health` | stato backend (sempre senza token) |
| GET | `/api/services` · `/api/services/{id}` | stato dei servizi Docker (`immich`, `jellyfin`, `seerr`, `download`, `vaultwarden`, `pihole`, `uptime-kuma`, `ntfy`, `portainer`, `tailscale`) |
| POST | `/api/services/{id}/start` · `stop` · `restart` | azione sul servizio |
| GET | `/api/stats` | uso di risorse: server (CPU, RAM, dischi, temperatura) e per servizio (CPU, RAM, tempo di attività, salute, riavvii); `setup` segnala cartelle dei dati mancanti |
| GET | `/api/tailscale/status` | stato Tailscale, indirizzo https, dispositivi |
| GET/POST | `/api/backup/status` · `/api/backup/jobs` · `/api/backup/snapshots` | backup Restic ([docs](docs/restic.md)) |

Se `API_TOKEN_HASH` è impostato, ogni chiamata (tranne health) richiede l'header `X-API-Token`.
Generalo con `./src/scripts/gen-api-token.sh`. Dettagli in [docs/security.md](docs/security.md).

## Sicurezza

- Il backend monta `/var/run/docker.sock`: chi controlla l'API controlla la macchina. La porta 8088 è
  pubblicata **solo su 127.0.0.1**, il token è obbligatorio (`gen-api-token.sh`) e non va mai esposta su Internet.
- I backup di Vaultwarden sono cifrati AES-256 (`BACKUP_PASSPHRASE_FILE`).
- Sul router **non si apre nessuna porta**: da fuori casa si entra con Tailscale. Le porte dei servizi sono su `127.0.0.1` (`BIND_ADDR`).
- Tailscale Serve e' l'unico proxy: l'elenco di cio' che e' raggiungibile dalla tua rete e' `tailscale/serve.json`. Radarr, Sonarr,
  Prowlarr e qBittorrent ci passano, quindi la loro autenticazione e' obbligatoria (vedi `docs/seerr.md`).
- Portainer, come il pannello, ha il socket Docker: la sua porta e' sempre su `127.0.0.1`, mai in LAN.

## Passaggio al Raspberry

- Tutti i dati restano in `data/` dentro il progetto sul filesystem Linux (ext4).
- Radarr, Sonarr, Prowlarr e qBittorrent occupano circa 1-1,5 GB di RAM insieme; Bazarr e FlareSolverr (limitato a 1 GB) ne aggiungono altri: dal pannello
  si spengono tutti con un solo interruttore (**Download automatici**), vedi [docs/seerr.md](docs/seerr.md) e [docs/bazarr.md](docs/bazarr.md).
- Immich consuma parecchia RAM (soprattutto `immich-machine-learning`): su un Pi con poca memoria valuta di
  disattivarlo e tieni almeno 4 GB.
