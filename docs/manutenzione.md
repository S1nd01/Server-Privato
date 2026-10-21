# Manutenzione: Diun e Autoheal

Nel pannello sono un'unica scheda, **Manutenzione**, nel blocco **Utility** (un interruttore per i due container). Pesano pochi MB: di solito restano accesi.

- **Diun** controlla ogni giorno (alle 8) se per le immagini che usi è uscita una versione nuova e ti manda una notifica su ntfy. **Non aggiorna nulla**:
  aggiorni tu, quando vuoi.
- **Autoheal** riavvia i container che Docker segna come *unhealthy* (cioè con il controllo di salute fallito più volte di fila).

## Diun

### Collegarlo a ntfy

ntfy è in `deny-all` (vedi [ntfy.md](ntfy.md)): Diun ha bisogno di un utente con permesso di scrittura. Se hai già creato l'utente `servizi` come in ntfy.md, usa quello.

```bash
docker compose exec ntfy ntfy user add servizi                          # se non esiste ancora
docker compose exec ntfy ntfy access servizi homeserver write-only      # l'argomento che già segui sul telefono
```

Nel `.env`:

```
DIUN_NTFY_USER=servizi
DIUN_NTFY_PASSWORD=la-password-di-servizi
```

Poi `docker compose up -d diun` e prova che la notifica arrivi sul telefono:

```bash
docker compose exec diun diun notif test
```

Le notifiche arrivano sull'argomento `homeserver` (cambialo con `DIUN_NTFY_TOPIC` nel `.env`). Al primo giro Diun memorizza le versioni attuali senza avvisare:
da quel momento segnala solo le novità.

### Aggiornare quando arriva un avviso

```bash
docker compose pull            # scarica le immagini nuove
docker compose up -d           # ricrea solo i container la cui immagine è cambiata
docker image prune -f          # toglie le immagini vecchie (libera spazio)
```

Prima di aggiornare **Immich** leggi le note di versione: a volte richiedono passaggi in più. Per **Vaultwarden** e **Immich** conviene che l'ultimo backup Restic sia recente.
Con le immagini `latest` Diun avvisa quando cambia il contenuto dell'immagine (non il numero di versione): se un servizio smette di funzionare dopo un aggiornamento,
`docker compose logs <servizio>` dice quasi sempre perché.

### Cosa viene controllato

Tutte le immagini dei container, tranne il backend del pannello (costruito in locale, ha l'etichetta `diun.enable=false`). Per escluderne un'altra aggiungi la stessa etichetta
al servizio in `compose.yaml`:

```yaml
    labels:
      - diun.enable=false
```

L'orario si cambia con `DIUN_SCHEDULE` nel `.env` (cron a 5 campi, **tra virgolette**: `DIUN_SCHEDULE="0 8 * * 1"` = ogni lunedì alle 8). Se il server è spento a quell'ora, il controllo si perde fino al giro dopo.

## Autoheal

Agisce **solo** sui container con l'etichetta `autoheal=true`. Sono quelli che hanno già un controllo di salute affidabile:

| Container | Controllo di salute |
|---|---|
| Radarr, Sonarr, Prowlarr | definito in `compose.yaml` (`/ping` ogni minuto) |
| Jellyfin, Immich (server), Vaultwarden, Pi-hole, Uptime Kuma | già nell'immagine |

Gli altri (qBittorrent, Bazarr, FlareSolverr, Seerr, Portainer, Tailscale, ntfy, Unmanic…) non hanno etichetta: se un controllo di salute sbagliato li facesse riavviare in continuazione, non te ne accorgeresti.
La scelta è volutamente prudente.

Come si comporta:

- Controlla ogni 30 secondi e aspetta 2 minuti dopo il proprio avvio.
- Un container *unhealthy* viene riavviato (con 20 secondi per spegnersi in modo pulito).
- I container **fermati** (dal pannello, per esempio il gruppo Download) non li tocca.
- Il contatore "Riavvii automatici" del pannello conta quelli decisi da Docker (`restart: unless-stopped`), non quelli di Autoheal: per questi guarda `docker compose logs autoheal`.

### Primo avvio: controlla che i controlli di salute funzionino

Il controllo di Radarr, Sonarr e Prowlarr usa `curl` dentro il container. Prima di fidarti di Autoheal:

```bash
docker compose up -d
# aspetta 5 minuti, poi:
docker compose ps
```

Nella colonna STATUS i servizi con controllo devono essere `healthy` (nel pannello: *Salute: Funziona bene*). Se vedi `unhealthy` su uno che funziona, il controllo è sbagliato e
Autoheal lo riavvierebbe di continuo: `docker compose stop autoheal` e guarda cosa risponde il controllo con
`docker inspect --format '{{json .State.Health}}' sonarr`.

Nota: `docker compose up -d` ricrea i container a cui ho aggiunto etichetta e controllo di salute (una breve interruzione, una volta sola).

### Aggiungere un altro servizio

1. Verifica che abbia un controllo di salute (`docker inspect --format '{{json .State.Health}}' nome` non deve dare `null`), oppure aggiungi un `healthcheck:` in `compose.yaml`.
2. Aggiungi l'etichetta:

   ```yaml
       labels:
         - autoheal=true
   ```

3. `docker compose up -d`.

### Con la compressione in corso

Con la CPU al massimo un servizio può rispondere troppo piano al controllo e risultare *unhealthy* senza essere rotto. Per questo [Unmanic](compressione.md) ha un tetto di CPU
(`UNMANIC_CPUS`) più basso dei core del server. Se vedi riavvii di Jellyfin durante una compressione, abbassa quel valore.

## Risorse

Diun 128 MB al massimo, Autoheal 64 MB; entrambi con priorità CPU bassa. Montano il socket Docker (Diun in sola lettura, Autoheal in scrittura, come il backend del pannello e Portainer).
