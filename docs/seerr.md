# Seerr, JellyBridge e download automatici (Radarr, Sonarr, Prowlarr, qBittorrent)

Seerr (il nuovo nome di Jellyseerr/Overseerr) raccoglie le richieste di film e serie. **JellyBridge** è un plugin di
Jellyfin che mostra i contenuti "da scoprire" come se fossero una libreria: metti un cuore a un film e il plugin
lo richiede a Seerr. Seerr lo passa a Radarr (film) o Sonarr (serie), che lo scaricano con qBittorrent e lo mettono
in `Film` o `Serie TV`, dove Jellyfin lo trova.

```
Jellyfin + JellyBridge ──> Seerr ──> Radarr / Sonarr ──> qBittorrent ──> data/media/Film, Serie TV ──> Jellyfin
                                         ▲
                                      Prowlarr (indexer)
```

Servono **tutti e due**: Radarr gestisce solo i film, Sonarr solo le serie. Da soli Seerr e JellyBridge non scaricano nulla.

## Cartelle (le crea `sync-env.sh`)

In `data/media/`: `Film`, `Serie TV`, `Discoveries` (la riempie JellyBridge, non metterci file tuoi) e `downloads` (la cartella
dei download in corso). Le configurazioni sono in `data/seerr`, `data/radarr`, `data/sonarr`, `data/prowlarr`, `data/qbittorrent`
e finiscono nel backup Restic.

Radarr, Sonarr, qBittorrent e Jellyfin vedono la stessa cartella come `/media`. Non cambiare questi percorsi: se i
container non vedono lo stesso percorso, l'importazione dei file fallisce.

Jellyfin legge `/media` in sola lettura; l'unica eccezione è `/media/Discoveries`, dove JellyBridge deve scrivere.

## Avvio

```bash
./src/scripts/start.sh
```

| Servizio | Indirizzo (sul server) | Dentro Docker |
|---|---|---|
| Seerr | http://localhost:5055 | `http://seerr:5055` |
| Radarr | http://localhost:7878 | `http://radarr:7878` |
| Sonarr | http://localhost:8989 | `http://sonarr:8989` |
| Prowlarr | http://localhost:9696 | `http://prowlarr:9696` |
| qBittorrent | http://localhost:8080 | `http://qbittorrent:8080` |

Nei campi "host" o "URL" dei servizi usa sempre i nomi Docker della terza colonna, mai `localhost`.
Dal telefono, con Tailscale, si apre solo Seerr: `https://<nome>.ts.net:5055`. Radarr, Sonarr, Prowlarr e qBittorrent restano
sul server (`127.0.0.1`): sono pannelli di amministrazione, non servono fuori.

## 1. qBittorrent

1. La password temporanea compare nel registro: `docker compose logs qbittorrent | grep -i password`. Accedi con utente `admin`.
2. Opzioni, Web UI: cambia subito la password.
3. Opzioni, Download: *Percorso di salvataggio predefinito* = `/media/downloads`.

## 2. Radarr e Sonarr

In ciascuno, alla prima apertura imposta un'autenticazione (Impostazioni, Generale, Sicurezza), poi:

1. Impostazioni, Media, *Aggiungi cartella radice*: Radarr `/media/Film`, Sonarr `/media/Serie TV`.
2. Impostazioni, Client di download, *Aggiungi*, qBittorrent: host `qbittorrent`, porta `8080`, utente e password del punto 1.
   Categoria `radarr` (o `sonarr`).
3. Impostazioni, Generale: copia la **API key** (serve a Prowlarr e a Seerr).

## 3. Prowlarr

1. Aggiungi gli indexer (Indexers, *Add Indexer*).
2. Impostazioni, Apps, *Add*: Radarr con *Prowlarr Server* `http://prowlarr:9696`, *Radarr Server* `http://radarr:7878` e la sua API key.
   Poi uguale per Sonarr (`http://sonarr:8989`). Da quel momento gli indexer si copiano da soli su entrambi.

## 4. Seerr

1. Procedura guidata: scegli **Jellyfin** come server, URL `http://jellyfin:8096`, accedi con l'amministratore di Jellyfin.
2. Nelle librerie da sincronizzare attiva **solo `Film` e `Serie TV`**. **Non attivare `Discoveries`**: altrimenti le richieste
   fatte da JellyBridge risulterebbero già "Disponibili" e non partirebbe nessun download.
3. Impostazioni, Servizi: aggiungi **Radarr** (host `radarr`, porta `7878`, API key, cartella radice `/media/Film`, profilo qualità) e
   **Sonarr** (host `sonarr`, porta `8989`, API key, cartella radice `/media/Serie TV`). Segna ciascuno come predefinito.
4. Impostazioni, Utenti, *Importa utenti da Jellyfin*.
5. Impostazioni, Generale: copia la **API key** (serve a JellyBridge).

## 5. JellyBridge (dentro Jellyfin)

1. Dashboard, Plugin, Repository, *Nuovo repository*: nome `JellyBridge`, URL
   `https://raw.githubusercontent.com/kinggeorges12/JellyBridge/refs/heads/main/manifest.json`.
2. Plugin, Catalogo (Jellyfin 11: *Disponibili*), cerca JellyBridge (sezione "Other") e installalo. Scegli la versione giusta
   per il tuo Jellyfin: da 10.11.9 in poi quella che finisce in `.11.9`; da 10.11.0 a 10.11.8 quella `.11.0`; con 10.10.x quella `.10.7`.
3. Riavvia Jellyfin (Dashboard, *Riavvia*).
4. Apri le impostazioni del plugin e inserisci:
   - **Jellyseerr URL**: `http://seerr:5055`
   - **API Key**: quella di Seerr
   - **Library Directory**: `/media/Discoveries` (il percorso *dentro* il container)
5. *Test connection*, poi *Create Discover Library* e infine *Import Discover Content*.
6. Nelle opzioni del plugin attiva *Responsive Favorite Requests* se vuoi che la richiesta parta appena metti il cuore.
7. Per vedere i contenuti in ordine casuale, nella libreria JellyBridge ordina per *Numero di riproduzioni* (crescente).

Se le richieste create da JellyBridge restano "in attesa di approvazione" in Seerr, approvale a mano oppure dai all'utente il
permesso *Approvazione automatica* (Seerr, Utenti). Il progetto JellyBridge segnala un problema noto sull'approvazione
(issue 17 del suo repository): controlla lì se persiste. Il plugin è testato con Seerr 3.x.

## Accesso da fuori casa

Con Tailscale (vedi `tailscale.md`) Seerr è su `https://<nome>.ts.net:5055`. Gli altri quattro non sono pubblicati in
Tailscale di proposito: restano raggiungibili dal server stesso.

## Risorse

Su un Raspberry con 8 GB i quattro strumenti di download occupano circa 1-1,5 GB di RAM. Nel pannello compaiono come
**Download automatici** (un solo interruttore per tutti e quattro): spegnili quando non servono. Seerr e JellyBridge
continuano a funzionare, ma le richieste restano in coda finché non riaccendi.

## Problemi comuni

- **Errore di permessi** su una cartella: l'ha creata Docker come root. Lancia `./src/scripts/sync-env.sh`, ti propone il comando `chown` giusto.
- **Seerr scrive `EACCES: permission denied, mkdir '/app/config/logs'` (o Jellyfin `Access to the path '/config/log' is denied`)**: la cartella
  `data/seerr` o `data/jellyfin` (o una sua sottocartella) appartiene a root, perché l'ha creata Docker in un avvio precedente. Seerr gira ora col tuo utente
  (`PUID:PGID`), come Jellyfin. Ferma i servizi, lancia `./src/scripts/sync-env.sh` (controlla tutto l'albero e ti propone il `chown -R` giusto),
  poi `docker compose up -d`. Non lanciare mai gli script con `sudo`.
- **Radarr/Sonarr scaricano ma non importano**: controlla che il percorso nel client di download sia `/media/downloads` e che la
  cartella radice sia sotto `/media`. Nessuna "mappatura dei percorsi remoti" serve se i percorsi sono questi.
- **qBittorrent lento**: la porta dei peer non è pubblicata (nessuna porta aperta sul router, come per tutto il progetto). Funziona
  comunque in uscita; aprire una porta è una scelta tua e fuori da questo progetto.
- **JellyBridge non vede la cartella**: il percorso va scritto come lo vede Jellyfin (`/media/Discoveries`), non come sta sul disco.
- **Dopo un aggiornamento di Jellyfin il plugin non carica**: reinstalla la versione giusta del plugin (punto 5.2) e svuota la cache del browser.
