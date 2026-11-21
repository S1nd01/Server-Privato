# Reti Docker

Ogni gruppo di servizi sta in una rete propria e vede solo i suoi vicini. Prima c'era una rete unica: un container compromesso (per esempio qBittorrent, che
scarica contenuti non fidati) poteva raggiungere Vaultwarden, i database e il pannello. Ora no.

| Rete | Chi c'è | Perché | Internet |
|---|---|---|---|
| `panel` | frontend, backend, Tailscale, Uptime Kuma | il pannello e chi lo pubblica o lo controlla | sì |
| `photos` | Immich server, riconoscimento, Tailscale, Uptime Kuma | il riconoscimento scarica i modelli | sì |
| `immich_db` | Immich server, Postgres, Redis | il database non parla con nessun altro | **no** (interna) |
| `media` | Jellyfin, Seerr, Maintainerr, Radarr, Sonarr, Tailscale, Uptime Kuma | si chiamano tra loro (richieste, libreria, pulizia) | sì |
| `arr` | qBittorrent, Prowlarr, FlareSolverr, Bazarr, Recyclarr, Radarr, Sonarr, Tailscale, Uptime Kuma | i download e chi li coordina | sì |
| `vault` | Vaultwarden, Tailscale, Uptime Kuma | solo chi lo pubblica e lo controlla | sì |
| `tools` | Pi-hole, Portainer, Unmanic, Beszel, Tailscale, Uptime Kuma | interfacce di amministrazione raggiunte da Tailscale | sì |
| `notify` | ntfy, Radarr, Sonarr, Diun, Tailscale, Uptime Kuma, ntfy-telegram | chi scrive le notifiche (e il ponte Telegram, che le legge) | sì |
| `dockerproxy_ro` | Diun, `docker-proxy-ro` | Diun legge container e immagini | **no** (interna) |
| `dockerproxy_rw` | Autoheal, `docker-proxy-rw` | Autoheal riavvia i container | **no** (interna) |
| `homeserver_dns` | Pi-hole, Unbound | DNS ricorsivo (invariata) | sì |

Radarr e Sonarr sono su tre reti perché fanno da ponte: parlano con i download (`arr`), con Jellyfin e Seerr (`media`) e con ntfy (`notify`).
Tailscale e Uptime Kuma entrano in tutte le reti dei servizi che pubblicano o controllano: sono i due punti da proteggere di più.
Beszel agent usa la rete dell'host e non sta in nessuna di queste.

Cosa **non** si vede più, per esempio: qBittorrent, Prowlarr, FlareSolverr, Bazarr e Recyclarr non raggiungono Jellyfin, Vaultwarden, Immich, Pi-hole, il pannello né i proxy
del socket. Postgres e Redis di Immich li raggiunge solo il server di Immich. Vaultwarden lo raggiungono solo Tailscale e Uptime Kuma.

## Aggiungere un servizio

1. Scegli la rete del gruppo a cui appartiene, o creane una nuova in fondo a `compose.yaml` (con una subnet fissa libera in `10.89.x.0/27`).
2. Dichiara `networks:` sul servizio: senza, finisce in una rete `default` che non deve più esistere.
3. Se va pubblicato da Tailscale (`tailscale/serve.json`), aggiungi quella rete anche al servizio `tailscale`.
4. Se Uptime Kuma deve controllarlo, aggiungila anche a `uptime-kuma`.
5. Se deve scrivere su ntfy (notifiche, per esempio un bot Telegram), mettilo in `notify`.

Una porta su `127.0.0.1` non basta per essere raggiunti da un altro container: i container parlano tra loro per nome sulle reti condivise, non dalle porte pubblicate.

## Se qualcosa non si raggiunge

- Errore tipo «could not resolve host» o «connection refused» tra due servizi: controlla che abbiano **almeno una rete in comune** (`docker inspect <container> --format '{{json .NetworkSettings.Networks}}'`).
- Un monitor di Uptime Kuma sempre giù dopo aver aggiunto un servizio: manca la sua rete in `uptime-kuma`.
- Un servizio non pubblicato da Tailscale (pagina che non carica da `.ts.net`): manca la sua rete in `tailscale`.

## Controllo automatico

```bash
python3 src/scripts/check-config.py
```

Legge il compose risolto (senza avviare nulla) e verifica che reti, porte, backup, catalogo del pannello e `tailscale/serve.json` non divergano: ogni servizio pubblicato da Tailscale
raggiungibile, i monitor di Uptime Kuma raggiungibili, i download separati da Vaultwarden e Jellyfin, nessuna porta fuori da `127.0.0.1` oltre a Jellyfin, Seerr e Pi-hole, solo i container previsti
con il socket Docker, le cartelle di `sync-env.sh`, `stats.py` e `backup.py` allineate. Lanciarlo dopo ogni modifica al compose evita proprio gli errori che questa documentazione descrive.

## Indirizzi

Le subnet sono fisse (`10.89.10.0` - `10.89.19.0`) per un motivo: senza, Docker le sceglie da solo e, dopo una quindicina di reti, comincia a usare
`192.168.x.x`, cioè quella di casa. Se una coincide con una tua rete, cambia la subnet in `compose.yaml` e ricrea le reti (`docker compose down && docker compose up -d`).
`homeserver_dns` (`10.89.53.0/28`) ha indirizzi fissi per Unbound; vedi [unbound.md](unbound.md).
