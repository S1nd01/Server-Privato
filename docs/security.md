# Sicurezza

Obiettivo realistico: un server in casa, raggiungibile da fuori **solo** via Tailscale. Nessuna misura qui è
"a prova di tutto": sono protezioni concrete contro gli errori e gli attacchi più probabili.

## Token del pannello

Il pannello comanda Docker (equivale a root sul sistema), quindi ogni chiamata `/api` richiede un token.

```bash
./src/scripts/gen-api-token.sh          # genera 256 bit casuali, mostra il token UNA volta
docker compose up -d backend
```

In `.env` finisce solo `API_TOKEN_HASH=sha256:<hash>`. Per ruotare il token rilancia lo script.

**Perché hash e non cifratura AES.** Il token non si deve mai poter recuperare: al server basta verificarlo.
Se lo cifrassi con AES, la chiave per decifrarlo starebbe accanto al file cifrato (stesso `.env`, stesso
disco), e chi ruba uno ruba l'altro: complessità senza protezione. Un hash invece non è reversibile. Il token è
casuale a 256 bit, quindi SHA-256 basta: lo "stretching" (scrypt/argon2) serve per password scelte da
persone, e qui renderebbe solo costoso ogni tentativo sbagliato.

Dove la cifratura AES ha senso, c'è: i **backup** di Vaultwarden (vedi `vaultwarden.md`), e il vault stesso,
che Bitwarden/Vaultwarden cifrano già in AES-256 lato client con la tua password master.

### Cosa fa il backend per resistere a injection e abusi

| Rischio | Contromisura |
|---|---|
| Token in chiaro rubato dal `.env` o dai backup | Nel `.env` c'è solo l'hash; `.env` ha permessi 600 |
| Token che finisce in log/cronologia | Letto solo dall'header `X-API-Token`, mai da URL/query; non viene mai riportato negli errori |
| Header injection / payload strani (`CRLF`, SQL, UTF-8, spazi) | Formato rigido `[A-Za-z0-9_-]{32,128}`: tutto il resto è respinto prima di essere elaborato |
| Timing attack | Confronto degli hash a tempo costante (`hmac.compare_digest`) |
| Tentativi ripetuti | Dopo 10 token sbagliati in un minuto dallo stesso client: `429` con `Retry-After`. Un token valido passa comunque (indovinarlo è impossibile), così non ti chiudi fuori da solo |
| Configurazione sbagliata | Hash malformato ⇒ `503` (si chiude, non si apre); nessun token ⇒ API protette con risposta `503` fino alla configurazione |
| XSS nel pannello | Il frontend scrive i dati con `textContent`, mai `innerHTML`; CSP rigida: solo file dello stesso sito, niente script o stili inline |
| Click-jacking, sniffing del tipo di file | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` sulle API |

Limiti da conoscere: il token sta nel `sessionStorage` del browser (sparisce chiudendo la scheda) oppure, se spunti "Ricorda su questo dispositivo",
nel `localStorage` (resta finché non esci dall'app: usalo solo su un telefono tuo e con blocco schermo). Uno script iniettato potrebbe leggerlo: per questo la CSP; e se qualcuno ottiene accesso al socket Docker o al tuo utente
sul server, il token non serve più. Il limite dei tentativi è per client visto da nginx.

## Rete

- Il pannello è pubblicato solo su `127.0.0.1:8088`: dalla LAN non si raggiunge, nemmeno con il token.
- Sul router non si apre **nessuna** porta. Tailscale fa uscire il server verso la tua rete privata: da fuori
  ci si entra solo con un dispositivo che hai approvato nel tuo account Tailscale.
- Tutte le porte dei servizi sono pubblicate su `127.0.0.1`: nemmeno la rete di casa le vede. Fanno eccezione solo Jellyfin e Seerr, che seguono
  `LAN_BIND_ADDR`: mettilo all'IP del server (meglio di `0.0.0.0`) solo se serve (es. TV, un familiare) e limita le porte con il firewall.
  Prima c'era un unico `BIND_ADDR` per tutti: con `0.0.0.0` apriva in LAN anche Unmanic e Maintainerr (senza password), qBittorrent e gli arr.
- Il DNS di Pi-hole ascolta su `127.0.0.1` finché non decidi diversamente (`PIHOLE_DNS_BIND`).
- Radarr, Sonarr, Prowlarr e qBittorrent non sono pubblicati in Tailscale (solo Seerr lo è): sono pannelli di amministrazione.
  Imposta in ciascuno un utente e una password al primo accesso (docs/seerr.md). Il Seerr raggiungibile da Tailscale usa gli utenti di Jellyfin.
- Unmanic e Maintainerr non chiedono password di serie: stanno su `127.0.0.1` e si raggiungono solo da Tailscale. Beszel e il suo agente non pubblicano nulla in più
  (socket condiviso); l'agente monta il socket Docker (vedi *Socket Docker* sotto: il `:ro` non lo rende innocuo).
- Unbound sta su una rete Docker privata (`10.89.53.0/28`) condivisa solo con Pi-hole e non pubblica porte.
- Il container Tailscale non si ferma né si riavvia dal pannello: se ti colleghi tramite lui, perderesti l'accesso.
- Sulla WSL con rete "mirrored": non usare `-DefaultInboundAction Allow`; con `LAN_BIND_ADDR=127.0.0.1` non serve aprire nulla.
- Gli indirizzi `.ts.net` finiscono nei registri pubblici dei certificati (Certificate Transparency): il nome è visibile,
  i contenuti no. Non metterci nomi che non vuoi rendere pubblici.

## Reti Docker

Ogni gruppo di servizi sta in una rete propria (mappa e motivi in [reti.md](reti.md)). Un container compromesso vede solo i vicini del suo gruppo: qBittorrent,
Prowlarr e FlareSolverr, che trattano contenuti non fidati, non raggiungono Vaultwarden, Jellyfin, i database né il pannello. Postgres e Redis di Immich
stanno su una rete interna, senza Internet. Tailscale e Uptime Kuma sono gli unici a entrare in più reti (uno pubblica, l'altro controlla): sono i punti da proteggere di più.

## Socket Docker

Chi parla con `/var/run/docker.sock` controlla la macchina: può creare un container che monta `/` e leggere o scrivere qualsiasi file. Il flag `:ro` sul volume **non**
cambia nulla: limita il file del socket, non le richieste che ci passano sopra.

| Container | Accesso | Come |
|---|---|---|
| Backend del pannello | limitato, per regole | tramite `docker-gate`: avvia/ferma i container del pannello, due `exec` fissi, il job di backup |
| Portainer | completo | solo su richiesta (`docker compose --profile admin-tools up -d portainer`) |
| Beszel agent | completo (il `:ro` è di facciata) | eccezione, vedi sotto |
| Diun | lettura di container e immagini | tramite `docker-proxy-ro` |
| Autoheal | elenco e riavvio dei container | tramite `docker-proxy-rw` |

**`docker-gate`** (`src/docker-gate/gate.py`, solo libreria standard) sostituisce il socket per il backend. Un proxy che filtra solo per percorso non basterebbe: il backend
deve poter creare il container dei backup, e chi può creare *un* container qualsiasi può montare `/` e diventare root. Il filtro guarda quindi anche il **corpo** delle richieste:

- avvio, arresto, riavvio, statistiche e log: solo sui container di `GATE_CONTAINERS` (che `check-config.py` obbliga a coincidere con `services.py`) e sul job di backup;
- creazione di container: solo l'immagine di Restic, solo i montaggi previsti (percorsi presi dalle variabili d'ambiente, con il loro modo `ro`/`rw`), nessun privilegio, nessuna rete diversa da quella di serie, solo comandi Restic su `/repo`; ogni container creato riceve l'etichetta `hs.gate=1`, con cui il filtro riconosce i propri;
- `exec`: solo `/vaultwarden backup` in Vaultwarden e `tailscale status --json` in Tailscale; anche l'avvio di un exec già creato si verifica interrogando Docker;
- tutto il resto (immagini, volumi, reti, eventi, build, copia di file, rimozione di altri container) riceve `403`.

Sta su una rete interna (`dockerproxy_api`) con il solo backend, `read_only`, `cap_drop: ALL`. Le regole sono provate contro un Docker vero con lo stesso SDK del backend:
`python3 -m pytest src/docker-gate/test_gate.py` (le prove con Docker si saltano se non c'è un demone). I rifiuti compaiono nei log: `docker logs docker-gate`.

I due proxy (`tecnativa/docker-socket-proxy`) per Diun e Autoheal stanno su reti interne, senza Internet e raggiungibili solo da Diun e da Autoheal rispettivamente. Lasciano passare solo le
chiamate elencate in `compose.yaml` e rifiutano il resto: creare container, `exec`, volumi, reti, immagini.

Limiti da conoscere:
- **`docker-gate` non riscrive le risposte:** con `GET /containers/<nome>/json` chi controlla il backend legge anche le variabili d'ambiente dei container del pannello (password passate così comprese). Non può però crearne, entrarci a piacere o toccare il resto di Docker.
- **Non provato su un Raspberry** (provato su un demone Docker x86 con l'SDK del backend). Le regole sono quelle dell'API Docker di oggi: un cambio di SDK o di versione che aggiunga campi al corpo di creazione viene **rifiutato** (fallisce in modo sicuro) e si vede nei log; la correzione è in `CREATE_KNOWN` o `HOSTCONFIG_KNOWN`.
- Un proxy per Diun e Autoheal toglie la scrittura, **non la lettura**: con `CONTAINERS=1` si leggono i dettagli di ogni container, comprese le variabili d'ambiente (e quindi le password passate così).
- `ALLOW_RESTARTS` consente anche `stop` e `kill` di qualsiasi container: un Autoheal compromesso può fermare i servizi, non prenderne il controllo.
- **Beszel agent resta sul socket.** Sta in rete host, quindi non entra nelle reti interne dei proxy e servirebbe pubblicare una porta sul computer; inoltre per i proxy
  per socket sono segnalati scollegamenti dopo qualche ora (issue 11notes/docker-socket-proxy #10: proxy diverso, non verificato con questo). Se vuoi toglierlo dal socket,
  prova `docker-proxy-ro` e tieni d'occhio i log dell'agente per un paio di giorni.
- Un servizio compromesso con il socket completo (Portainer, Beszel agent) resta root sul server: per questo il pannello richiede un token e le porte sono locali.

## Servizi aggiunti: scambio file, sincronizzazione, convertitore, VPN, copia fuori sede

- **Copyparty** ([scambio-file.md](scambio-file.md)): condivide solo `data/scambio`; un solo account, nessun accesso anonimo; configurazione in sola lettura e obbligatoria per partire; `read_only`, nessuna capacità, utente non root. Sulla LAN (se abiliti `COPYPARTY_BIND_ADDR`) il traffico è HTTP.
- **Syncthing** ([syncthing.md](syncthing.md)): scoperta globale, relay, UPnP e scoperta in LAN spenti; la porta 22000 non è pubblicata sul computer (la inoltra Tailscale); utente e password impostati da `syncthing-setup.sh`.
- **ConvertX** ([convertx.md](convertx.md)): elabora file non fidati, quindi rete interna senza Internet, nessuna porta, tetti di CPU/RAM/processi, file cancellati dopo 24 ore, spento di serie.
- **gluetun** ([vpn.md](vpn.md)): è l'**unico container con `NET_ADMIN`** (firewall e tunnel). Sta solo in `arr`; la chiave WireGuard è un segreto in un file con permessi 600, non una variabile; `check-config.py` impedisce che altri container ottengano `NET_ADMIN` o privilegi.
- **rclone** ([backup-remoto.md](backup-remoto.md)): l'archivio è montato in sola lettura; gira come root con la sola capacità `DAC_OVERRIDE` (per leggere i file di Restic, che sono di root); vive nella rete `backup_out`, senza altri container. La sua configurazione (credenziali del servizio remoto) sta in `data/rclone`, fuori dal backup. Limite: se il server è compromesso, il remoto segue il locale: servono versioni o blocco degli oggetti sul servizio remoto.
- **Controllo dischi** ([smart.md](smart.md)): è uno script sul computer, non un container: nessun accesso ai dischi in più per un servizio.

## Altri indurimenti dei container

`no-new-privileges` (il processo non può ottenere più privilegi di quelli con cui parte) è attivo su frontend, backend, Diun, Autoheal, `docker-gate` e i due proxy del socket. Nginx risolve il backend a ogni richiesta
e il backend ha un controllo di salute con riavvio automatico (Autoheal), come il frontend.

Il ponte Telegram (`ntfy-telegram`, [telegram.md](telegram.md)) nasce già con `read_only`, `cap_drop: ALL` e `no-new-privileges`, utente non root, nessuna porta e una sola rete (`notify`); i suoi token stanno in `data/telegram` (permessi 600, montata in sola lettura) e quello di ntfy è di sola lettura.

Cose che ho **scelto di non fare**, con il motivo:
- **Backend senza root.** Ha comunque il socket Docker, cioè è già root sulla macchina: cambiare utente non toglierebbe nulla di sostanziale e richiederebbe il GID del gruppo `docker` dell'host e i permessi di `data/panel`.
- **`read_only`, `cap_drop: ALL` e `no-new-privileges` su tutto il resto.** Per le immagini `linuxserver`, Pi-hole e Postgres dipendono da come l'immagine cambia utente e da dove scrive (`/run`, `/tmp`, `/etc`):
  senza provarli uno per uno rischiano di rompere un servizio che oggi funziona, a fronte di un guadagno piccolo (le porte sono già locali e le reti separate). Si possono introdurre un servizio alla volta, con una prova a casa.

## Schermata iniziale e video esterno

La schermata iniziale ([schermata-iniziale.md](schermata-iniziale.md)) riproduce un video HLS da Mux. Conseguenze, da sapere:

- **La CSP si apre, ma solo per questo:** `media-src` e `connect-src` ammettono `blob:` (il video HLS passa da un MediaSource) e `https://*.mux.com`. Restano `'self'` `script-src`, `style-src` e `worker-src`, e non c'è `unsafe-inline`. `connect-src` vale per tutto il pannello, non solo per la schermata iniziale: finché la regola c'è, uno script iniettato potrebbe contattare `*.mux.com`, che però non è un canale utile a chi non lo controlla.
- **Privacy:** a ogni apertura della schermata iniziale il browser contatta Mux, che vede IP e orario. Chi è già autenticato non la vede e non fa la richiesta.
- **Disponibilità:** se Mux non risponde, lo sfondo resta nero. Non blocca l'accesso.
- **Non verificato:** da qui non potevo raggiungere Mux, quindi `https://*.mux.com` è la forma larga che copre manifest e segmenti ma non è stata confermata sui nomi reali degli host. Se il video non parte a casa, guarda la console del browser: una violazione CSP indica l'host da aggiungere.
- Per eliminare del tutto la dipendenza: video locale, vedi [schermata-iniziale.md](schermata-iniziale.md#il-video).

## Credenziali dimenticate

Il recupero passa **solo dal terminale del server** (`./src/scripts/recupera-credenziali.sh`, guida in [credenziali.md](credenziali.md)). La scheda **Accessi** del pannello mostra dove sta
ogni credenziale e il comando da lanciare, ma non rivela e non reimposta nulla: se potesse, chi ottiene il token del pannello (che equivale a root sul server) avrebbe in più anche tutte le altre password.
Le uniche password in chiaro sul server sono quelle che i servizi richiedono così: `PIHOLE_PASSWORD` e `IMMICH_DB_PASSWORD` nel `.env` (permessi 600) e i due file delle passphrase dei backup nella tua home.
Il token del pannello e quello di `/admin` di Vaultwarden sono solo hash, e la password master di Vaultwarden non esiste sul server.

## Cifratura nei vari punti

| Cosa | Come |
|---|---|
| Vault delle password | AES-256 lato client (Bitwarden), Vaultwarden vede solo dati cifrati |
| Backup di Vaultwarden | AES-256 (GnuPG simmetrico) con passphrase da file, integrità verificata |
| Connessione a Vaultwarden | HTTPS di Tailscale (certificato valido); dal server stesso solo `localhost` |
| Accesso da fuori | Tailscale: tunnel WireGuard cifrato (ChaCha20-Poly1305) + HTTPS con certificato valido |
| Backup Restic | AES-256 (CTR) con autenticazione Poly1305-AES; la passphrase sta in un file a parte |
| Immich | HTTP in LAN; da fuori casa passa da Tailscale in HTTPS |

## Promemoria

- Aggiorna le immagini (`docker compose pull`) e Windows/Ubuntu: la maggior parte dei buchi reali sono lì.
- Nel pannello di Tailscale disattiva la scadenza della chiave del server (altrimenti dopo 180 giorni si scollega).
- Salva la passphrase di Restic anche fuori dal server: senza, i backup sono illeggibili.
- Il backup Restic parte solo dall'amministratore e il disco esterno va scollegato a lavoro finito: collegato di continuo non protegge da ransomware o scariche (docs/restic.md).
- Account Vaultwarden creato ⇒ `VW_SIGNUPS=false`. Master password lunga e unica, con 2FA.

## Plex (opzionale)

Profilo `plex`, di solito spento ([plex.md](plex.md)). Rete `media`, nessuna rete con contenuti non fidati. L'immagine ufficiale parte come
root e passa al vostro utente: capacità limitate a `CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE` e `FOWNER`, `no-new-privileges`, libreria in
sola lettura. Dipende da plex.tv per l'accesso. L'accesso remoto integrato di Plex (porta aperta sul router) non va usato: da fuori casa
solo Tailscale. `check-config.py` verifica profilo, capacità, montaggi e porta.

## RomM (opzionale)

Profilo `romm`, di solito spento ([romm.md](romm.md)). Due container: RomM (reti `romm` con Internet e `romm_db`) e MariaDB (solo `romm_db`,
interna). Nessuna porta sul computer, accesso solo da Tailscale. Streamyfin ([streamyfin.md](streamyfin.md)) è solo un'app client e non
aggiunge nulla al server. `check-config.py` verifica profili, reti, montaggi (solo `data/romm`) e assenza di porte.
