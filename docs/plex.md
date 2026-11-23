# Plex

Plex è un secondo server multimediale che legge la **stessa libreria** di Jellyfin (`data/media`: Film, Serie TV). Radarr e Sonarr
continuano a scrivere come prima; Plex legge in sola lettura. È opzionale (profilo `plex`): non parte con `up` e si accende dal pannello
o con:

```bash
docker compose --profile plex up -d plex
```

## Cosa conviene sapere prima (valutazione critica)

- **Account plex.tv obbligatorio.** L'autenticazione passa dai server di Plex: se Plex è irraggiungibile o l'account ha problemi, anche
  dalla rete di casa può non essere possibile accedere. Jellyfin non ha questa dipendenza.
- **Funzioni a pagamento.** La trascodifica hardware e alcune app mobile richiedono Plex Pass. Su un Raspberry la trascodifica software è
  comunque pesante: puntate sul *direct play* (file già compatibili con i client).
- **RAM.** Jellyfin e Plex insieme sono troppi per un Raspberry da 8 GB insieme a Immich: tenete acceso uno dei due, non entrambi.
- **JellyBridge funziona solo con Jellyfin.** I segnaposto dei contenuti "da scoprire" non compaiono in Plex. Seerr si configura con un
  solo server multimediale alla volta: verificate nella sua interfaccia se potete collegarne uno diverso da Jellyfin.
- **Nessuna porta aperta.** Le funzioni "accesso remoto" integrate di Plex richiedono l'apertura di una porta sul router: non vanno
  usate. Da fuori casa si passa da Tailscale (sotto).

## Prima attivazione

1. Create la cartella dati: `./src/scripts/sync-env.sh` (aggiunge `data/plex/config`).
2. Aprite https://plex.tv/claim e copiate il token (vale pochi minuti). Mettetelo in `.env` come `PLEX_CLAIM=...`.
3. Avviate: `docker compose --profile plex up -d plex`. Controllate: `docker logs plex`.
4. Appena Plex risulta associato al vostro account, **svuotate `PLEX_CLAIM`** nel `.env`: non serve più.
5. Aprite `http://127.0.0.1:32400/web` dal server (oppure `https://<nome>.ts.net:32400` da un dispositivo con Tailscale) e aggiungete le
   librerie: **Film** → `/media/Film`, **Serie TV** → `/media/Serie TV`. Non aggiungete `/media/Discoveries` né `/media/downloads`.

## Accesso da fuori casa (Tailscale)

- Tailscale Serve pubblica Plex sulla porta 32400 in HTTPS, solo nella tailnet.
- In Plex: *Impostazioni → Rete* → "URL di accesso personalizzati" = `https://<nome>.ts.net:32400` (oppure `PLEX_ADVERTISE_IP` nel `.env`).
- *Impostazioni → Rete → Reti LAN*: aggiungete `10.89.13.0/27` (la rete `media` del compose). Il traffico che arriva da Tailscale esce dal
  proxy con un indirizzo di quella rete; senza questa voce Plex lo tratta come "remoto" e può limitare la qualità.
- Disattivate "Abilita accesso remoto": con nessuna porta aperta mostrerebbe solo un errore.

## Rete di casa (TV)

Di serie la porta è su `127.0.0.1`. Per la TV di casa mettete in `.env` `PLEX_BIND_ADDR=<IP del server>` e riavviate Plex. In LAN la
connessione è HTTP; per le password vale la stessa avvertenza di Jellyfin.

## Radarr e Sonarr

Plex vede i file nuovi con la scansione automatica (rilevamento delle modifiche sulle cartelle): di solito non serve altro. Se volete
l'aggiornamento immediato: in Radarr/Sonarr *Impostazioni → Connect → Plex Media Server*, host `plex`, porta `32400`, e accedete con il
vostro account. Radarr, Sonarr e Plex condividono la rete `media` e lo stesso percorso `/media`, quindi i percorsi coincidono.

## Sicurezza del container

- Rete `media` (insieme a Jellyfin, Seerr, Radarr, Sonarr e Tailscale). Non è raggiungibile da qBittorrent, Prowlarr e dagli altri
  servizi che trattano contenuti non fidati.
- `cap_drop: ALL`, con solo `CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE` e `FOWNER`: l'immagine ufficiale parte come root e poi passa a
  `PLEX_UID:PLEX_GID` (il vostro utente). `no-new-privileges` attivo. `read_only` non è applicato (l'immagine scrive in più punti).
- `/media` in sola lettura; `/transcode` in RAM (512 MB, contati nel limite di memoria).
- Limiti: `PLEX_CPUS` (3) e `PLEX_MEM` (2g) nel `.env`.
- Il filtro del socket Docker (docker-gate) include `plex`, quindi il pannello può accenderlo e spegnerlo.

## Backup

`data/plex/config` **non** è nel backup Restic: contiene metadati e miniature rigenerabili ma molto numerosi. Perdendolo bisogna
riassociare il server e rifare la scansione; cronologia di visione e utenti vanno persi. Se vi interessano, aggiungete la cartella in
`src/backend/app/backup.py` (valutandone la dimensione).

## Non verificato

Immagine reale, avvio con `cap_drop ALL` e le sole capacità indicate, valore esatto di `ADVERTISE_IP` quando vuoto, comportamento di
`/transcode` come tmpfs e connessione tramite Tailscale non sono stati provati (nessun Docker in funzione dove è stato scritto). Se
Plex non parte, `docker logs plex` indica se manca una capacità: in quel caso riferitemelo.
