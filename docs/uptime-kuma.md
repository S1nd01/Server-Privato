# Uptime Kuma

Controlla a intervalli regolari che i servizi rispondano e ti avvisa (con [ntfy](ntfy.md)) quando si fermano o tornano su.
Ha una pagina di stato con la cronologia e i tempi di risposta.

| Dove | Indirizzo |
|---|---|
| Dal server | http://localhost:3001 |
| Da Tailscale | `https://<nome>.ts.net:3001` |

I dati stanno in `data/kuma`. Non monta il socket Docker: controlla i servizi con richieste HTTP o TCP verso i nomi dei container,
quindi non aggiunge un secondo accesso privilegiato al server.

## Primo avvio

1. `docker compose up -d uptime-kuma`
2. **Subito** apri l'indirizzo e crea l'utente amministratore: il primo che arriva diventa amministratore.
3. Impostazioni, Notifiche, *Imposta notifica*, tipo **Ntfy**: server `http://ntfy:80`, argomento a tua scelta (per esempio `homeserver`),
   utente e password di ntfy. Spunta *Predefinito abilitato* per usarla in tutti i controlli. Vedi [ntfy.md](ntfy.md).

## Controlli consigliati

Nei campi usa sempre i nomi Docker, mai `localhost`. Tipo *HTTP(s)*, intervallo 60 secondi, o più alto per risparmiare risorse.

| Servizio | URL |
|---|---|
| Pannello | `http://hs_frontend:80/` |
| Backend del pannello | `http://backend:8000/api/health` |
| Jellyfin | `http://jellyfin:8096/health` |
| Immich | `http://immich_server:2283/api/server/ping` |
| Vaultwarden | `http://vaultwarden:80/alive` |
| Seerr | `http://seerr:5055/api/v1/status` |
| Radarr | `http://radarr:7878/ping` |
| Sonarr | `http://sonarr:8989/ping` |
| Prowlarr | `http://prowlarr:9696/ping` |
| qBittorrent | `http://qbittorrent:8080/` |
| Bazarr | `http://bazarr:6767/` |
| FlareSolverr | `http://flaresolverr:8191/health` |
| Pi-hole (web) | `http://pihole:80/admin/` |
| ntfy | `http://ntfy:80/v1/health` |
| Portainer | `https://portainer:9443/api/system/status` con *Ignora errori TLS/SSL* attivo |

Per Pi-hole aggiungi anche un controllo **DNS**: risolutore `pihole`, porta `53`, nome `example.com`. Così sai se risponde alle richieste, non solo se la pagina è su.

## Quando spegni dei servizi dal pannello

Spegnere il gruppo **Download automatici** fa scattare gli avvisi dei suoi controlli. Metti in pausa quei controlli in Kuma (o raggruppali e metti
in pausa il gruppo) prima di spegnerlo, oppure accetta l'avviso.

## Problemi comuni

- **Dall'indirizzo `.ts.net` la pagina resta in caricamento**: Kuma usa i WebSocket e confronta l'origine della richiesta. Se succede, aggiungi
  `UPTIME_KUMA_WS_ORIGIN_CHECK: bypass` tra le `environment` del servizio in `compose.yaml`.
- **Avvisi ripetuti dopo un riavvio del server**: è normale per qualche minuto, finché i servizi non sono tutti su. Imposta *Tentativi* a 2 o 3.
