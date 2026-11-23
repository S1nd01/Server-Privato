# VPN per qBittorrent (gluetun, WireGuard)

Con la VPN attiva **tutto il traffico di qBittorrent esce dal tunnel**: chi è nello sciame vede l'indirizzo del provider VPN e non il tuo. Se il tunnel cade, gluetun blocca tutto (kill switch): qBittorrent resta senza rete, non scarica con il tuo indirizzo.
Prowlarr, FlareSolverr, Radarr, Sonarr e tutto il resto **non** passano dalla VPN. Non cambia nulla altrove: gluetun prende l'alias di rete `qbittorrent`, quindi Radarr, Sonarr e Tailscale continuano a chiamare `http://qbittorrent:8080`.

È **opzionale** e spenta di serie (file `compose.vpn.yml`): senza attivarla, il progetto si comporta come prima.

## Cosa ti serve

- Un provider VPN che ti faccia scaricare un **file WireGuard** (`.conf`): Mullvad, Proton, IVPN, AirVPN, un tuo server… Il provider non è fissato nel progetto (gluetun in modalità `custom`).
- Docker Compose 2.24 o più recente (`docker compose version`).
- `/dev/net/tun` sul computer (c'è sul Raspberry).
- **Il file non deve contenere una `PresharedKey`**: questa versione non la gestisce (lo script si ferma e lo dice).

## Attivare

```bash
./src/scripts/vpn-setup.sh /percorso/wg0.conf      # legge il file e scrive tutto nel .env
docker compose config -q                            # il compose è valido?
docker compose up -d gluetun qbittorrent
./src/scripts/vpn-test.sh                           # IP diverso dal server? web raggiungibile?
./src/scripts/vpn-test.sh --kill-switch             # e senza VPN qBittorrent resta davvero isolato? (ferma i download per qualche secondo)
```

Lo script mette la chiave privata in `~/.wireguard-key` (permessi 600, **fuori** dal progetto e dal `.env`) e arriva a gluetun come segreto, non come variabile: non si legge con `docker inspect`. Fai una copia della chiave nel tuo gestore di password: non è nei backup.
Scrive anche `COMPOSE_FILE=compose.yaml:compose.override.yml:compose.vpn.yml` nel `.env`. **Non aggiungere `COMPOSE_FILE` a `.env.example`.**

Disattivare: `./src/scripts/vpn-setup.sh --disattiva` e poi `docker compose up -d` (qBittorrent torna sulla rete `arr`). Stato: `--stato`.

## Cosa cambia nell'uso

- Il web di qBittorrent è sempre su `127.0.0.1:8080` e da Tailscale come prima; la porta ora la pubblica gluetun.
- **Riavvii:** qBittorrent usa la rete di gluetun: se gluetun viene riavviato da solo (per esempio `docker restart gluetun`), qBittorrent resta attaccato a una rete che non esiste più finché non lo riavvii. Dal pannello (scheda «Download automatici») o con `docker compose up -d` i due partono nell'ordine giusto; compose li riavvia insieme (`restart: true`). Per questo gluetun **non** ha l'etichetta Autoheal.
- All'avvio del computer i due container possono partire in ordine sparso: qBittorrent riprova da solo fino a quando gluetun è su.
- Il pannello ordina gluetun per primo all'avvio e per ultimo allo spegnimento, e lo ignora se la VPN non è attiva.

## Porta inoltrata e seeding

Senza una porta aperta dal lato VPN, qBittorrent funziona ma solo in uscita: scarica, ma si connette a meno peer e con i tracker privati puoi avere problemi di ratio. Se il provider ti assegna una porta (AirVPN, ProtonVPN, PIA…), va autorizzata in gluetun (`FIREWALL_VPN_INPUT_PORTS`) e impostata in qBittorrent. Non l'ho inclusa: dipende dal provider; quando l'hai scelto, dimmelo e la aggiungo.

## Tracker privati

Molti tracker privati **vietano o segnalano le VPN** (indirizzi condivisi, cambi di IP), e un cambio di indirizzo può far sospettare un account condiviso. Con i tracker pubblici non c'è problema; per quelli privati leggi le regole del tracker prima di far passare l'account dalla VPN.
Con una sola istanza di qBittorrent, tutto passa dalla VPN o niente. Se serve separare pubblici e privati, serve una seconda istanza (dimmelo).

## Sicurezza

- **gluetun è l'unico container con `NET_ADMIN`**: gli serve per firewall e tunnel; sta solo nella rete `arr`, dove vedono già tutto ciò che è «non fidato».
- Una VPN non rende anonimo ciò che scarichi e non sostituisce le regole sul diritto d'autore del tuo paese.
- DNS: gluetun usa un suo DNS (DNS su TLS) **attraverso il tunnel**; qBittorrent non passa da Pi-hole. È voluto: così le richieste DNS non escono dal tunnel.
- `check-config.py` verifica anche la variante con la VPN (valori finti): qBittorrent senza rete propria, gluetun solo in `arr` con alias, chiave come segreto, nessun altro con `NET_ADMIN`.

## Cosa non è provato

**Non l'ho provata con un tunnel reale** (qui non ho una VPN né i container). La struttura del compose è validata con `docker compose config` e i controlli di coerenza; il comportamento di gluetun (porte, firewall, healthcheck, nomi delle variabili) segue la sua documentazione, ma verifica al primo avvio con `vpn-test.sh`.
Punti da guardare: `docker logs gluetun` (tunnel su), il test dell'IP e il kill switch, e che Radarr e Sonarr raggiungano ancora qBittorrent (il test lo controlla).
Se l'endpoint del provider è un nome, lo script lo converte in un indirizzo IP una sola volta: se il provider lo cambia, rilancia `vpn-setup.sh` con il file nuovo.
