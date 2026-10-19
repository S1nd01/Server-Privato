# Setup di Pi-hole: dispositivi in casa e fuori casa

Guida completa alla configurazione di Pi-hole come DNS per tutti i tuoi dispositivi, a casa e da fuori con Tailscale. Per l'installazione base vedi [pihole.md](pihole.md).

## Cosa fa e cosa non fa

Pi-hole è un server DNS: quando un dispositivo chiede "qual è l'indirizzo di questo sito?", Pi-hole rifiuta i nomi di pubblicità, tracker e siti dannosi.

- **Blocca:** domini di pubblicità, tracker, telemetria, malware (a seconda delle liste).
- **Non blocca:** pubblicità servite dallo stesso dominio del contenuto (per esempio gli annunci di YouTube), né i pop-up che il sito apre da sé. Per quelli serve un blocco nel browser (vedi [Pop-up](#pop-up-e-pubblicità-che-passano-comunque)).

## Schema

```
Telefono/PC ──(Tailscale)──▶ container tailscale ──▶ Pi-hole (IP del server, porta 53)
Dispositivi di casa ───────(DHCP/DNS del router)───▶ Pi-hole
```

Solo le richieste DNS passano dal server: le pagine le scarica il dispositivo direttamente dalla sua connessione.

## 1. Prerequisiti

- Pi-hole attivo (`docker compose up -d pihole`) e interfaccia su `http://<IP server>:8053/admin`.
- Il server ha un **IP fisso** sulla LAN (prenotazione DHCP nel router: *Rete domestica → Rete → il dispositivo → "Assegna sempre lo stesso indirizzo IPv4"*).
- Nel `.env`:
  ```
  PIHOLE_DNS_BIND=192.168.178.36    # l'IP del server, non 127.0.0.1
  PIHOLE_WEB_BIND=0.0.0.0           # oppure l'IP del server / 127.0.0.1 se non serve in LAN
  ```
- Prova locale:
  ```bash
  dig @192.168.178.36 doubleclick.net +short    # deve rispondere 0.0.0.0
  ```

Su Ubuntu/Linux Mint la porta 53 su `0.0.0.0` va in conflitto con il resolver di sistema (127.0.0.53): per questo si usa l'IP della LAN.

## 2. Dispositivi in casa

Imposta il DNS dal router, così tutti i dispositivi usano Pi-hole senza configurarli uno a uno.

Fritz!Box → *Rete domestica → Rete → Impostazioni di rete → Impostazioni IPv4* → **Server DNS locale** = IP del server → Applica. I dispositivi prendono il nuovo DNS al prossimo rinnovo (riconnetti il Wi-Fi).

Se il server è spento, la rete di casa non risolve i nomi. Un secondo DNS nel router attenua il problema, ma alcuni dispositivi lo useranno anche a Pi-hole acceso, saltando il blocco.

## 3. Fuori casa, con Tailscale

Il container Tailscale gira in modalità "userspace". Per far arrivare le richieste DNS a Pi-hole pubblica l'IP del server come *subnet router*.

1. Nel `.env`:
   ```
   TS_ROUTES=192.168.178.36/32
   ```
   In `compose.yaml`, tra le variabili del servizio `tailscale`, deve esserci `TS_ROUTES: ${TS_ROUTES:-}`.
2. Applica (serve ricreare il container per leggere la variabile):
   ```bash
   docker compose up -d pihole
   docker compose up -d --force-recreate tailscale
   sleep 15
   docker exec tailscale tailscale debug prefs | grep -A2 AdvertiseRoutes
   ```
   Deve comparire `192.168.178.36/32`.
3. Console Tailscale (login.tailscale.com):
   - **Machines** → il server → `⋯` → **Edit route settings** → spunta la route → Salva.
   - **DNS** → **Nameservers** → **Add nameserver** → **Custom** → IP del server → Salva.
   - Attiva **Override DNS servers**. Senza l'override i dispositivi usano il loro DNS locale e Pi-hole non viene usato.
4. Sul dispositivo: app Tailscale accesa, stesso account del server.

### Se il server è spento

Con l'override attivo e Pi-hole come solo nameserver, i dispositivi non risolvono i nomi finché il server è spento. Soluzioni:

- **Android:** nell'app Tailscale → *Impostazioni → DNS* → disattiva **Use Tailscale DNS settings**. Tailscale resta acceso e raggiungi comunque i servizi, ma usi il DNS normale.
- **PC:** disattiva Tailscale o, nelle impostazioni dell'app, l'uso dei DNS della rete.
- **Non aggiungere un secondo nameserver pensando che faccia da ripiego.** Secondo la documentazione Tailscale, quando fa da proxy interroga tutti i nameserver in parallelo e usa la risposta più veloce, senza garantire l'ordine né un failover: il blocco diventerebbe incostante.

## 4. Test

Esci dalla rete di casa: dati mobili sul telefono, oppure PC collegato all'hotspot.

**Samsung / Android**
1. Tailscale acceso. *Wi-Fi spento.*
2. *Impostazioni → Connessioni → Altre impostazioni di connessione → DNS privato* → **Automatico** o **Disattivato**.
3. Chrome → *Impostazioni → Privacy e sicurezza → Usa DNS sicuro* → disattivato.
4. Apri `http://doubleclick.net`: non deve caricarsi.
5. Pagina di prova: `d3ward.github.io/toolz/adblock.html`.

**PC Windows**
1. Tailscale acceso, PC sull'hotspot.
2. `nslookup doubleclick.net` → deve rispondere `0.0.0.0` (il server mostrato può essere `100.100.100.100`: è il resolver interno di Tailscale).
3. Disattiva Tailscale e rifai il comando: ora risponde un IP reale.
4. Nel browser, disattiva il DNS sicuro (DoH), che salta Pi-hole.

**Verifica in Pi-hole**: `http://<IP server>:8053/admin` → *Query Log*. Le richieste arrivate da Tailscale compaiono tutte con lo stesso client (l'indirizzo della rete Docker): riconosci il dispositivo dal dominio, non dall'IP.

**Connessione diretta o relay** (con il telefono collegato):
```bash
docker exec tailscale tailscale ping <nome-dispositivo>
```
`via <IP>:<porta>` = diretta; `via DERP(...)` = passa da un relay (più lenta).

## 5. Liste di blocco

Pi-hole parte con una lista base. Per bloccare di più, aggiungi liste nell'interfaccia: *Lists* (in Pi-hole 6) → incolla l'indirizzo → *Add*, poi *Tools → Update Gravity*.

Esempi di liste (HaGeZi, adblock format accettato da Pi-hole 6):

| Lista | Indirizzo | Note |
|---|---|---|
| Pro (consigliata) | `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/pro.txt` | Equilibrata, rischio di blocchi sbagliati basso-moderato |
| Pop-Up Ads | `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/adblock/popupads.txt` | Domini usati da pop-up e redirect pubblicitari |

Più liste = più blocco e più rischio che qualche sito o app smetta di funzionare. Se succede, nel *Query Log* trovi il dominio bloccato e lo sblocchi con *Allow*. Evita le liste "aggressive" (come Pro++) se non vuoi correggere a mano i falsi positivi.

## Pop-up e pubblicità che passano comunque

Pi-hole lavora a livello di DNS e non vede le finestre che un sito apre. Nessuna sua opzione blocca "ogni finestra che non sia quella aperta". Per quello servono:

- il **blocco pop-up del browser** (attivo di default in Chrome e Firefox);
- un'estensione come **uBlock Origin** (Firefox, anche su Android; Chrome ne ha versioni limitate dalla sua politica sulle estensioni);
- la lista *Pop-Up Ads* qui sopra, che ne riduce parecchi a livello di DNS.

Le pubblicità servite dallo stesso dominio del contenuto (YouTube, alcuni siti di notizie) non si bloccano con il DNS.

## Problemi osservati

- **Pagine lente fuori casa, con la connessione del server lenta.** Ogni pagina fa decine di richieste DNS: se il server sta su un Wi-Fi debole (latenze di secondi) le pagine sembrano "non caricarsi". Sistema con un collegamento via cavo (Ethernet o powerline) e controlla con `dig @<IP> prova$RANDOM.org | grep 'Query time'` (sotto 100 ms va bene).
- **qBittorrent che satura la linea** alza la latenza per tutti, DNS compreso. Metti limiti di velocità in qBittorrent (circa 70-80% della banda, soprattutto in upload) e tienilo spento quando non serve.
- **Messaggi `netstack: UDP session ... timed out` nel log di Tailscale** (`docker logs tailscale`): le richieste DNS dal container verso Pi-hole non ricevono risposta. Verifica il percorso con `docker exec tailscale nslookup wikipedia$RANDOM.org <IP server>`. In modalità userspace il traffico UDP verso la rete è gestito da Tailscale in software; se il problema persiste, la strada è far girare Tailscale in modalità normale (con `/dev/net/tun` e privilegi di rete) o sul sistema ospite invece che nel container.
- **Nome duplicato `homeserver-2`:** nella console Tailscale esiste una voce vecchia `homeserver`, offline. Eliminala da *Machines*.
- **Impostazioni che saltano Pi-hole:** DNS privato di Android su un nome host, DNS sicuro (DoH) del browser, VPN di terze parti.
