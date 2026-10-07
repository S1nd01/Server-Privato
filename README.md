# Homeserver

Pannello minimale (frontend + backend/API) per gestire Immich, Vaultwarden, WireGuard e Steam via Docker.

```
homeserver/
├── backend/    FastAPI: legge/avvia/ferma i container tramite il socket Docker
├── frontend/   HTML+JS statico servito da nginx (proxy /api -> backend)
├── compose.yaml
└── .env.example
```

## Avvio su PC Linux (branch `pc-linux`)

```bash
cp .env.example .env      # cambia almeno IMMICH_DB_PASSWORD e WG_HOST
mkdir -p data
docker compose up -d --build
```

- Pannello: http://localhost:8088
- Immich: http://localhost:2283
- Vaultwarden: http://localhost:8080
- Steam (web UI): http://localhost:3000

Avvio parziale (es. solo pannello + Vaultwarden):

```bash
docker compose up -d --build frontend backend vaultwarden
```

## API

| Metodo | Path | Descrizione |
|---|---|---|
| GET | /api/health | stato backend |
| GET | /api/services | elenco servizi + stato |
| GET | /api/services/{id} | dettaglio servizio |
| POST | /api/services/{id}/start \| stop \| restart | azione sul servizio |

`id`: `immich`, `vaultwarden`, `wireguard`, `steam`. Documentazione interattiva (solo backend esposto): `/docs`.

## Note per il passaggio a Raspberry

- `linuxserver/steam` e' solo x86_64: sul Pi non gira. Sul Pi vedi alternativa SteamCMD.
- Imposta `DATA_DIR` sul mount dell'SSD.
- Il backend monta `/var/run/docker.sock`: equivale ad accesso root, non esporre il pannello su Internet senza autenticazione/VPN.
- Vaultwarden fuori da localhost richiede HTTPS (reverse proxy) per funzionare nel browser.
