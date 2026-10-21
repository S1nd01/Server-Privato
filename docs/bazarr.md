# Bazarr e FlareSolverr

Fanno parte del gruppo **Download automatici** del pannello (un solo interruttore con Radarr, Sonarr, Prowlarr e qBittorrent).

- **Bazarr** cerca e scarica i sottotitoli per i film e le serie che Radarr e Sonarr hanno già in libreria, e li salva come `.srt` accanto al video.
  Jellyfin li legge da solo, senza altre impostazioni.
- **FlareSolverr** è un browser senza finestra che Prowlarr usa per superare le sfide anti-bot di Cloudflare, quando un indexer le richiede.
  Non ha interfaccia e non pubblica nessuna porta: lo chiama solo Prowlarr, dentro Docker.

| Servizio | Indirizzo (sul server) | Dentro Docker |
|---|---|---|
| Bazarr | http://localhost:6767 | `http://bazarr:6767` |
| FlareSolverr | nessuno | `http://flaresolverr:8191` |

Da Tailscale Bazarr è su `https://<nome>.ts.net:6767`.

## Avvio

```bash
docker compose up -d bazarr flaresolverr
```

## 1. Bazarr

1. **Subito** Impostazioni, Generale, Sicurezza: *Autenticazione* = Form (o Basic), con utente e password. L'impostazione predefinita è nessuna
   autenticazione, e da Tailscale la porta sarebbe aperta a tutta la tua rete.
2. Impostazioni, Sonarr: attiva, host `sonarr`, porta `8989`, la API key di Sonarr (Impostazioni, Generale). *Test* e salva.
3. Impostazioni, Radarr: attiva, host `radarr`, porta `7878`, la API key di Radarr.
4. Impostazioni, Lingue: aggiungi *Italiano* (e *Inglese* se vuoi un ripiego) a *Languages Filter*, poi crea un **profilo di lingue**
   (per esempio Italiano, con Inglese come seconda scelta) e impostalo come predefinito per serie e film.
5. Impostazioni, Provider: aggiungi almeno un provider (OpenSubtitles.com, Podnapisi, Subdl e altri). Alcuni richiedono un account gratuito.
6. Non servono mappature dei percorsi: Bazarr vede i video su `/media`, come Radarr e Sonarr.

I sottotitoli si cercano da soli ai nuovi arrivi; per quelli già in libreria usa *Serie* o *Film* in Bazarr, *Cerca sottotitoli mancanti*.

## 2. FlareSolverr in Prowlarr

1. Prowlarr, Impostazioni, Indicizzatori, *Aggiungi* (+), **FlareSolverr**.
2. *Host* `http://flaresolverr:8191/`, *Tag* `flaresolverr`. Test e salva.
3. Aggiungi il tag `flaresolverr` solo agli indexer che lo richiedono (nell'elenco degli indexer, modifica, campo *Tag*). Gli altri non lo usano e non
   consumano risorse.

FlareSolverr funziona finché riesce a stare al passo con le protezioni di Cloudflare: se un indexer smette di rispondere, per prima cosa aggiornalo
(`docker compose pull flaresolverr && docker compose up -d flaresolverr`).

## Risorse

Bazarr occupa poche centinaia di MB. FlareSolverr a riposo poco, ma mentre risolve una sfida avvia Chromium e può arrivare a diverse centinaia di MB:
il compose non gli mette limiti (se la RAM finisce, Linux lo ferma per primo). Se non hai indexer che lo richiedono, tienilo spento (si ferma insieme al gruppo dal pannello).
