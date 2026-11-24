# Passaggio al Raspberry

Elenco di controlli per spostare il server dal computer al Raspberry (8 GB di RAM consigliati). Niente qui è stato provato su un Raspberry:
dove un punto dipende dal tuo sistema c'è scritto cosa verificare e con quale comando.

## 1. Prima di spostare (dal computer attuale)

```bash
./src/scripts/check-arm64.sh
```

Interroga il registro e dice, per ogni immagine, se esiste per `arm64`. **MANCA** = quel servizio non gira sul Raspberry. **?** = non verificabile
(registro irraggiungibile, o immagine a una sola architettura): guarda la pagina del progetto. Serve Internet; non scarica nulla.

Da sapere già ora:
- **Unmanic** (compressione video) usa x265 sulla CPU: sul Raspberry è lentissimo e porta il server al limite ([compressione.md](compressione.md)). Tienilo spento, o comprimi sul PC e sposta i file.
- **Immich, riconoscimento** (`immich_machine_learning`, fino a 3 GB di RAM): tienilo spento fuori dai caricamenti di foto (interruttore nel pannello) e riduci la concorrenza dei job ([ottimizzazione.md](ottimizzazione.md)).

## 2. Il sistema sul Raspberry

- **Dati su SSD, non su scheda SD.** Postgres e i database SQLite scrivono di continuo e consumano la SD. Formatta l'SSD in **ext4** e, meglio ancora, avvia da SSD.
- **Docker sull'SSD.** Sposta anche `/var/lib/docker` (immagini, log, volumi) con `"data-root": "/mnt/ssd/docker"` in `/etc/docker/daemon.json`, poi riavvia Docker.
- **Limiti di memoria attivi?** Il compose usa `mem_limit` (Immich ML, Unmanic, Beszel...). Se il sistema non ha il controllo della memoria attivo, Docker li ignora senza dirlo.
  Controlla con `docker info`: non deve comparire «No memory limit support». Se compare, su Raspberry Pi OS di solito si attiva aggiungendo
  `cgroup_enable=memory cgroup_memory=1` alla riga (una sola) di `/boot/firmware/cmdline.txt` e riavviando: verifica sulla guida del tuo sistema, il percorso e le opzioni cambiano tra versioni.
- **zram al posto dello swap su SD.** Con Immich e Postgres su 8 GB conviene uno swap compresso in RAM (`zram-tools`, o `systemd-zram-generator` a seconda del sistema).
- **La prima build compila il frontend.** `docker compose build` scarica `node:22-alpine` e i pacchetti npm della schermata iniziale ([schermata-iniziale.md](schermata-iniziale.md)): serve rete e qualche minuto in più, una volta. Con le immagini in cache le build successive sono rapide.
- **Indirizzo fisso** per il Raspberry (prenotazione DHCP sul router): Pi-hole e `TS_ROUTES` si basano su quell'IP.

## 3. Tailscale in modalità kernel (facoltativo)

Di serie Tailscale gira in modalità *userspace*: funziona ovunque ma ogni pacchetto passa da un processo, e su un Raspberry limita lo streaming da fuori casa.
`compose.tailscale-kernel.yml` passa alla modalità kernel (interfaccia `tailscale0`). **Non è provato**: attivalo solo dopo aver verificato che tutto funzioni in modalità normale.

```bash
echo 'COMPOSE_FILE=compose.yaml:compose.override.yml:compose.tailscale-kernel.yml' >> .env
docker compose up -d tailscale
```

Se usi `TS_ROUTES` per Pi-hole fuori casa, prova subito il DNS dal telefono sul 4G ([setup-pihole.md](setup-pihole.md)). Per tornare indietro: togli la riga dal `.env` e rilancia `docker compose up -d tailscale`.

## 4. Spostare i dati

1. Sul vecchio server: `docker compose down`.
2. Copia l'intera cartella del progetto, `data/` e `.env` compresi, con `rsync -aHAX` (conserva permessi e proprietari) o con un disco.
3. Sul Raspberry: `./src/scripts/start.sh`. Lo script sistema i percorsi e i permessi di `data/` (`sync-env.sh`).
4. **Tailscale: un solo server alla volta.** `data/tailscale` contiene l'identità del server: se vecchio e nuovo girano insieme con la stessa identità si contendono il nodo e l'accesso salta.
   Tieni spento il vecchio, oppure togli `data/tailscale` dal nuovo e fai un nuovo accesso (cambia l'indirizzo `.ts.net`, e con lui `VW_DOMAIN` di Vaultwarden e gli URL salvati nelle app).
5. Aggiorna `TS_ROUTES` e `PIHOLE_DNS_BIND` con il nuovo indirizzo del Raspberry, e il DNS sul router o sui dispositivi se usavi Pi-hole in casa.

## 5. Dopo il passaggio

```bash
docker compose ps                       # nessun servizio "unhealthy" o in riavvio continuo
docker stats --no-stream                # la RAM reale di ogni servizio: se un limite e' troppo basso, il servizio si riavvia da solo
python3 src/scripts/check-config.py     # la configurazione e' ancora coerente
```

Poi, dal pannello, riapplica le modalità che usi (Risparmio, Normale). I servizi che avevi spento dal pannello restano spenti: `start.sh` li rimette come erano ([risparmio.md](risparmio.md)).
