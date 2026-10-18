# Server-Privato

**Un home server completo in Docker, con un pannello web tutto suo.** Foto, film e serie, password, backup cifrati, blocco pubblicità e monitoraggio, raggiungibili da telefono e PC in HTTPS **senza aprire nessuna porta sul router**.

![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Tailscale](https://img.shields.io/badge/accesso-Tailscale-242424?logo=tailscale&logoColor=white)
![Python](https://img.shields.io/badge/backend-FastAPI%20%C2%B7%20Python%203.12-3776AB?logo=python&logoColor=white)
![PWA](https://img.shields.io/badge/pannello-PWA-5A0FC8)

Pensato per un **Raspberry Pi** (8 GB di RAM consigliati) con un SSD esterno; funziona anche su un PC Linux o su Windows con WSL.

## Indice

- [Cosa include](#cosa-include)
- [Come è fatto](#come-è-fatto)
- [Servizi e porte](#servizi-e-porte)
- [Requisiti](#requisiti)
- [Installazione](#installazione)
- [Accesso da telefono e PC](#accesso-da-telefono-e-pc)
- [Il pannello](#il-pannello)
- [Dati e backup](#dati-e-backup)
- [Sicurezza](#sicurezza)
- [Risorse e ottimizzazione](#risorse-e-ottimizzazione)
- [Configurazione](#configurazione)
- [Comandi utili](#comandi-utili)
- [Aggiornare](#aggiornare)
- [API](#api)
- [Struttura del progetto](#struttura-del-progetto)
- [Documentazione](#documentazione)
- [Da decidere](#da-decidere)

## Cosa include

| Area | Servizi | A cosa serve |
|---|---|---|
| **Foto** | Immich | Backup e galleria foto, con riconoscimento di volti e ricerca per contenuto. Legge la tua libreria esistente in sola lettura |
| **Film e serie** | Jellyfin, Seerr, Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr, FlareSolverr | Streaming, richieste direttamente da Jellyfin, download automatico e sottotitoli |
| **Password** | Vaultwarden | Password manager compatibile con le app Bitwarden |
| **Rete** | Pi-hole, Tailscale | Blocco di pubblicità e tracker per tutta la casa; accesso da fuori e proxy HTTPS unico |
| **Controllo** | Pannello, Uptime Kuma, ntfy, Portainer | Interruttori per ogni gruppo di servizi, controllo che tutto risponda, notifiche push e gestione grafica di Docker |
| **Backup** | Restic, backup di Vaultwarden | Archivi cifrati AES-256, automatici ogni notte |

## Come è fatto

Tutto passa da **Tailscale Serve**, l'unico reverse proxy del progetto: espone ogni servizio in HTTPS con un certificato valido, solo ai dispositivi del tuo account.

```mermaid
flowchart LR
    tel["Telefono / PC<br/>con Tailscale"] -->|HTTPS| ts["Tailscale Serve<br/>unico proxy"]
    ts --> pan["Pannello<br/>nginx + FastAPI"]
    ts --> foto["Immich"]
    ts --> media["Jellyfin · Seerr"]
    ts --> arr["Radarr · Sonarr · Prowlarr<br/>qBittorrent · Bazarr"]
    ts --> vw["Vaultwarden"]
    ts --> ctl["Uptime Kuma · ntfy<br/>Portainer · Pi-hole"]
    pan -->|socket Docker| dk[("Docker")]
```

Il flusso dei contenuti multimediali:

```mermaid
flowchart LR
    J["Jellyfin<br/>+ JellyBridge"] -->|richiesta| S[Seerr]
    S --> R["Radarr / Sonarr"]
    P[Prowlarr] --> R
    F["FlareSolverr"] -.->|indexer protetti| P
    R --> Q[qBittorrent]
    Q --> M[("data/media<br/>Film · Serie TV")]
    B[Bazarr] -->|sottotitoli| M
    M --> J
```

Una cartella sola, `data/`, contiene tutto: configurazioni, foto, media e backup.

## Servizi e porte

Le porte sono pubblicate solo su `127.0.0.1`: dal telefono o da un altro PC si usa l'indirizzo Tailscale `https://<nome>.<rete>.ts.net:<porta>`.

| Servizio | Cosa fa | Porta sul server | Guida |
|---|---|---|---|
| Pannello | Gestisce tutti i servizi | 8088 (Tailscale: 443) | [pwa.md](docs/pwa.md) |
| Immich | Foto | 2283 | [immich.md](docs/immich.md) |
| Jellyfin | Film, serie, musica | 8096 | [jellyfin.md](docs/jellyfin.md) |
| Seerr | Richieste di film e serie | 5055 | [seerr.md](docs/seerr.md) |
| Radarr · Sonarr · Prowlarr | Film, serie, indexer | 7878 · 8989 · 9696 | [seerr.md](docs/seerr.md) |
| qBittorrent | Client di download | 8080 | [seerr.md](docs/seerr.md) |
| Bazarr · FlareSolverr | Sottotitoli · sfide Cloudflare | 6767 · nessuna | [bazarr.md](docs/bazarr.md) |
| Vaultwarden | Password | Tailscale 8443 (dal server 8222, solo per emergenza) | [vaultwarden.md](docs/vaultwarden.md) |
| Pi-hole | DNS e blocco pubblicità | 53 · web 8053 (`/admin`) | [pihole.md](docs/pihole.md) |
| Uptime Kuma | Controllo dei servizi | 3001 | [uptime-kuma.md](docs/uptime-kuma.md) |
| ntfy | Notifiche push | 2586 | [ntfy.md](docs/ntfy.md) |
| Portainer | Gestione di Docker | 9443 (certificato autofirmato) | [portainer.md](docs/portainer.md) |
| Tailscale | Accesso e proxy HTTPS | nessuna | [tailscale.md](docs/tailscale.md) |
| Restic | Backup (parte a richiesta) | nessuna | [restic.md](docs/restic.md) |

20 container sempre attivi, più Restic quando serve.

## Requisiti

- Un Raspberry Pi con **8 GB di RAM** (Immich consiglia almeno 4 GB), oppure un PC Linux, oppure Windows con WSL.
- Un SSD per i dati: filesystem **ext4** (Postgres e SQLite non vanno su exFAT o NTFS).
- Docker con il plugin Compose (`setup-windows.bat` e `install-linux.sh` lo installano su Ubuntu se manca).
- Un account Tailscale gratuito per l'accesso da fuori casa.

Spazio: circa 30 GB più 1,3 volte le tue foto. I film e le serie occupano quanto servono.

## Installazione

### Linux

```bash
./src/scripts/gen-api-token.sh   # token del pannello: mostrato una sola volta, copialo
./src/scripts/start.sh           # prepara .env e cartelle, poi avvia i container
```

### Windows (con WSL)

Doppio clic su `setup-windows.bat`. Installa Ubuntu e Docker se mancano, prepara tutto, imposta la RAM di WSL e lo avvia a ogni accesso. Guida completa, con lo spostamento su SSD esterno: [windows.md](docs/windows.md).

### Cosa fa il primo avvio

Non serve toccare il `.env`: lo crea `start.sh` tramite `sync-env.sh`, insieme a tutte le cartelle in `data/`.

- Genera le passphrase dei backup di Restic e di Vaultwarden e te le mostra **una sola volta**: **copiale fuori dal server**.
- Se vuoi, attiva il backup notturno di Vaultwarden.
- Se il pannello mostra un avviso su cartelle mancanti o di root, rilancia `./src/scripts/sync-env.sh`. Non lanciare mai gli script con `sudo`.

### Dopo l'avvio

1. Apri il pannello su http://localhost:8088 e inserisci il token.
2. Sezione **Backup**: *Prepara l'archivio* (una volta sola).
3. Configura Tailscale: [tailscale.md](docs/tailscale.md).
4. Crea gli amministratori dei servizi, nell'ordine che preferisci:
   - **Vaultwarden:** il tuo account, poi `VW_SIGNUPS=false` e la 2FA ([guida](docs/vaultwarden.md));
   - **Radarr, Sonarr, Prowlarr:** *Autenticazione: Obbligatoria* ([guida](docs/seerr.md));
   - **Bazarr:** autenticazione ([guida](docs/bazarr.md));
   - **Uptime Kuma e Portainer:** il primo amministratore, subito dopo l'avvio ([Kuma](docs/uptime-kuma.md), [Portainer](docs/portainer.md));
   - **ntfy:** il tuo utente ([guida](docs/ntfy.md)).

Avvio parziale: `docker compose up -d --build frontend backend vaultwarden`.

## Accesso da telefono e PC

Tailscale crea una rete privata tra i tuoi dispositivi e pubblica i servizi in HTTPS, senza aprire porte sul router e anche dietro CGNAT. Le porte pubblicate sono 14 e le elenca `tailscale/serve.json`.

1. Installa l'app Tailscale e accedi con lo stesso account.
2. Apri `https://<nome>.<rete>.ts.net` per il pannello, oppure aggiungi la porta del servizio, per esempio `:8096` per Jellyfin.
3. Dal browser installa il pannello come app ([pwa.md](docs/pwa.md)).

Per un dispositivo senza Tailscale, come una TV con Jellyfin, serve `BIND_ADDR=0.0.0.0` nel `.env` e un firewall che lasci entrare solo la rete di casa.

## Il pannello

Una PWA a tre sezioni, in HTML e JavaScript senza librerie.

- **Servizi:** una scheda per gruppo con stato, CPU, RAM, tempo di attività, salute e riavvii; interruttori di avvio, arresto e riavvio; link "Apri". Mostra anche CPU, carico, RAM, dischi, temperatura e uptime del server.
- **Backup:** prepara l'archivio, avvia il backup, pulisce le copie vecchie, controlla l'archivio e mostra log e copie esistenti.
- **Rete:** stato di Tailscale, indirizzo HTTPS, dispositivi collegati e installazione dell'app.

Gli interruttori sono il modo più semplice per risparmiare RAM: **Download automatici** (sei servizi) e **Immich, riconoscimento** si spengono quando non servono. Tailscale non si ferma dal pannello, perché perderesti l'accesso.

## Dati e backup

```
data/
├── media/          Film · Serie TV · Discoveries · downloads
├── photos/         la tua libreria foto (Immich la legge in sola lettura)
├── immich/         upload · postgres · model-cache
├── vaultwarden/    pihole/    jellyfin/    seerr/    radarr/    sonarr/
├── prowlarr/       qbittorrent/    bazarr/    kuma/    ntfy/    portainer/
├── tailscale/      panel/
└── backups/        restic · vaultwarden
```

**Restic** salva in un archivio cifrato (AES-256, deduplicato) Vaultwarden, foto e dump di Immich, Pi-hole e le configurazioni di Jellyfin, Seerr, Radarr, Sonarr, Prowlarr e qBittorrent. Parte ogni notte alle 03:30 e poi pulisce, tenendo 7 copie giornaliere, 4 settimanali e 6 mensili. Film e download non sono inclusi. Dettagli e ripristino: [restic.md](docs/restic.md).

**Backup di Vaultwarden:** archivio cifrato con GnuPG, notturno alle 03:00 se lo attivi, ultime 14 copie.

Attenzione:
- la passphrase si copia **fuori dal server**, senza i backup non si aprono;
- la copia è solo locale: una copia fuori casa non è ancora collegata;
- Bazarr, Uptime Kuma, ntfy e Portainer non sono ancora tra le fonti di Restic.

## Sicurezza

Obiettivo realistico: un server in casa, raggiungibile da fuori **solo** via Tailscale. Dettagli in [security.md](docs/security.md).

- **Nessuna porta aperta** sul router. Le porte dei servizi stanno su `127.0.0.1` (`BIND_ADDR`).
- **Pannello e Portainer** hanno il socket Docker, cioè equivalgono a root: le loro porte restano sempre locali e il pannello richiede un token.
- **Token del pannello:** 256 bit casuali, nel `.env` c'è solo l'hash SHA-256. Letto solo dall'header, confronto a tempo costante, blocco dopo 10 errori al minuto.
- **Pannello web:** CSP rigida, niente script o stili inline, `X-Frame-Options: DENY`.
- **Pannelli pubblicati da Tailscale:** Radarr, Sonarr e Prowlarr vedono le richieste come locali, quindi l'autenticazione obbligatoria va impostata in ciascuno. ntfy è in `deny-all`.
- **Cifratura:** vault AES-256 lato client, backup AES-256, traffico WireGuard più HTTPS.
- **Pi-hole:** nel `.env.example` il DNS ascolta su un IP della LAN e la pagina web su `0.0.0.0`. È l'unica eccezione al "tutto locale": controlla che sia voluta.

## Risorse e ottimizzazione

- **Limiti di RAM:** Immich ML 3 GB, qBittorrent 2 GB, FlareSolverr 1 GB (prudenti, non misurati sul tuo server).
- **Priorità CPU bassa** per i servizi in background: Radarr, Sonarr, Prowlarr, Bazarr, qBittorrent, FlareSolverr, Immich ML.
- **Protezione dall'esaurimento di RAM:** Vaultwarden e Tailscale sono gli ultimi a essere fermati da Linux.
- **Log a rotazione:** 3 file da 10 MB per container.
- **Backup Restic** a bassa priorità e con al massimo 2 core.
- **Pannello leggero:** stato ogni 5 secondi, statistiche ogni 15, nessuna attività a scheda in secondo piano.

Impostazioni da ritoccare dentro i servizi (Immich, Jellyfin, arr, qBittorrent): [ottimizzazione.md](docs/ottimizzazione.md).

## Configurazione

Il `.env` lo gestisce `sync-env.sh`. Le variabili che può avere senso cambiare:

| Variabile | Significato |
|---|---|
| `BIND_ADDR` | Dove pubblicare le porte: `127.0.0.1` (solo dal server, consigliato) o `0.0.0.0` (anche la rete di casa) |
| `TS_HOSTNAME`, `TS_AUTHKEY` | Nome del server in Tailscale e chiave per il primo accesso |
| `API_TOKEN_HASH` | Hash del token del pannello (lo scrive `gen-api-token.sh`) |
| `IMMICH_DB_PASSWORD` | Password del database di Immich: scegli lettere e numeri **prima** del primo avvio |
| `VW_DOMAIN`, `VW_SIGNUPS`, `ADMIN_TOKEN` | Indirizzo `.ts.net` di Vaultwarden, registrazioni aperte o chiuse, pannello `/admin` |
| `NTFY_BASE_URL` | Indirizzo `.ts.net` di ntfy per l'app sul telefono |
| `PIHOLE_DNS_BIND`, `PIHOLE_WEB_BIND` | Dove ascoltano il DNS e la pagina web di Pi-hole |
| `RESTIC_SCHEDULE` | Ora del backup giornaliero (`HH:MM`; vuoto = solo manuale) |
| `TZ`, `PUID`, `PGID` | Fuso orario e utente con cui girano i container |

I percorsi dei dati non si configurano: sono fissi in `data/`. `./src/scripts/sync-env.sh --percorsi` riallinea il `.env` senza spostare dati già esistenti.

## Comandi utili

```bash
docker compose ps                              # stato dei container
docker compose logs -f jellyfin                # log di un servizio
docker compose pull && docker compose up -d    # aggiorna le immagini
docker compose exec tailscale tailscale serve status    # cosa pubblica Tailscale

docker compose exec ntfy ntfy user add --role=admin IL_TUO_NOME      # utente di ntfy
docker compose --profile tools run --rm restic -r /repo snapshots    # copie di Restic
./src/scripts/backup-vaultwarden.sh            # backup cifrato di Vaultwarden, a mano
```

## Aggiornare

Estrai il nuovo codice, tieni il tuo `.env`, poi `./src/scripts/start.sh`. Lo script riallinea i percorsi a `data/`, ma **non sposta** dati che si trovano altrove: copiali a servizi fermi dopo aver letto il messaggio di avviso.

Dalle versioni precedenti:
- **Caddy** non c'è più. Vaultwarden si apre da `https://<nome>.<rete>.ts.net:8443`: imposta `VW_DOMAIN` nel `.env`; la cartella `data/caddy` si può cancellare.
- **Portainer:** se aveva i dati in `homeserver-data/portainer`, copiali in `data/portainer` ([portainer.md](docs/portainer.md)).
- **SteamCMD** è stato rimosso: se avevi giochi in `data/steam-games`, spostali o cancellali a mano.

Le immagini usano spesso `latest`: leggi le note di rilascio prima di aggiornare, soprattutto per Immich, e fai prima un backup.

## API

Il backend è FastAPI; se `API_TOKEN_HASH` è impostato ogni chiamata, tranne `health`, richiede l'header `X-API-Token`.

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/health` | stato del backend, sempre senza token |
| GET | `/api/services` · `/api/services/{id}` | stato dei gruppi di servizi (`immich`, `immich-ml`, `jellyfin`, `seerr`, `download`, `vaultwarden`, `pihole`, `uptime-kuma`, `ntfy`, `portainer`, `tailscale`) |
| POST | `/api/services/{id}/start` · `stop` · `restart` | azione su un gruppo |
| GET | `/api/stats` | server (CPU, RAM, dischi, temperatura) e per servizio (CPU, RAM, uptime, salute, riavvii); segnala cartelle mancanti |
| GET | `/api/tailscale/status` | stato Tailscale, indirizzo HTTPS, dispositivi |
| GET/POST | `/api/backup/status` · `/api/backup/jobs` · `/api/backup/snapshots` | backup Restic |

## Struttura del progetto

```
Server-Privato/
├── compose.yaml          i servizi, con limiti di risorse e log a rotazione
├── compose.override.yml  aggiunte specifiche per Immich
├── .env.example          modello del .env (lo crea sync-env.sh)
├── setup-windows.bat     installazione automatica su Windows
├── src/
│   ├── backend/          FastAPI: servizi Docker, statistiche, backup Restic, stato Tailscale
│   ├── frontend/         PWA statica (HTML, CSS, JavaScript)
│   └── scripts/          start.sh · sync-env.sh · gen-api-token.sh · backup-vaultwarden.sh · install-linux.sh
├── nginx/                serve il pannello (CSP e header di sicurezza)
├── tailscale/            serve.json: i servizi pubblicati in HTTPS
├── docs/                 una guida per servizio
└── data/                 dati persistenti (creata all'avvio, non nel repository)
```

## Documentazione

| Argomento | Guida |
|---|---|
| Foto | [immich.md](docs/immich.md) |
| Film, serie e musica | [jellyfin.md](docs/jellyfin.md) · [seerr.md](docs/seerr.md) · [bazarr.md](docs/bazarr.md) |
| Password | [vaultwarden.md](docs/vaultwarden.md) |
| Rete e accesso | [tailscale.md](docs/tailscale.md) · [pihole.md](docs/pihole.md) |
| Controllo e notifiche | [uptime-kuma.md](docs/uptime-kuma.md) · [ntfy.md](docs/ntfy.md) · [portainer.md](docs/portainer.md) |
| Backup | [restic.md](docs/restic.md) |
| Sicurezza | [security.md](docs/security.md) |
| Risorse | [ottimizzazione.md](docs/ottimizzazione.md) |
| Pannello sul telefono | [pwa.md](docs/pwa.md) |
| Windows e SSD esterno | [windows.md](docs/windows.md) |

## Da decidere

- Aggiungere ai backup Bazarr, Uptime Kuma, ntfy e Portainer.
- Modalità del pannello ("Risparmio", "Tutto acceso"), spegnimento programmato e limiti di RAM calibrati sull'uso reale.
- Navidrome per la musica e Maintainerr per la pulizia della libreria (solo con conferma manuale).
- Una copia dei backup fuori casa.
