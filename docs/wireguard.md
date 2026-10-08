# WireGuard

VPN per raggiungere pannello, Immich e Vaultwarden da fuori casa **senza aprire nessuna di quelle porte** sul router.
L'unica porta esposta a Internet è `51820/udp`.

```
telefono/portatile ──UDP 51820──▶ router ──inoltro──▶ server (container wireguard, subnet VPN 10.13.13.0/24)
                                                        └─▶ LAN di casa + servizi del server
```

Il container `linuxserver/wireguard` genera chiavi e configurazioni in `$DATA_DIR/wireguard`: una cartella per peer
(`peer_<nome>/` con `.conf`, QR `.png` e chiave pubblica). Il server è `10.13.13.1`, i peer prendono `10.13.13.2…`.

## Cosa serve prima

1. **IP fisso del server in LAN** (prenotazione DHCP sul router).
2. **Inoltro porta** UDP 51820 → IP del server.
3. **Raggiungibilità da Internet**: `WG_HOST` deve essere l'IP pubblico o, meglio, un nome DDNS (DuckDNS, No-IP,
   o quello del router). Controlla che l'IP "WAN" mostrato dal router coincida con quello che vedi su un sito
   tipo "qual è il mio IP": se è diverso sei dietro **CGNAT** e l'inoltro porta non può funzionare.
4. Se prendi un FRITZ!Box: i FRITZ!OS recenti hanno WireGuard integrato e DDNS (MyFRITZ!). È un'alternativa
   valida, ma qui teniamo la VPN sul server così il progetto è autonomo.

## Configurazione in `.env`

| Variabile | Significato |
|---|---|
| `WG_HOST` | Indirizzo che i client useranno per collegarsi (DDNS/IP pubblico) |
| `WG_PEERS` | Nomi dei dispositivi separati da virgola: `telefono,portatile` |
| `WG_ALLOWEDIPS` | Cosa passa nel tunnel (vedi sotto) |
| `WG_EXPOSE_PEERS` | `true` mostra QR/.conf nel pannello (contengono chiavi **private**); tienilo `false` a regime |

**Split tunnel (default)** `10.13.13.0/24,192.168.1.0/24`: nel tunnel passa solo la VPN e la LAN di casa; il resto
di Internet esce dalla connessione normale del dispositivo. **Cambia `192.168.1.0/24` con la tua LAN reale**
(`ip route | grep src` sul server).
**Full tunnel** `0.0.0.0/0`: tutto il traffico passa da casa (utile su Wi-Fi pubblici, più lento).

## Aggiungere un dispositivo

1. Aggiungi il nome a `WG_PEERS` e `docker compose up -d wireguard`. I peer già esistenti mantengono le chiavi.
2. Mostra il QR nel terminale: `docker compose exec wireguard /app/show-peer telefono`
3. **Telefono**: app WireGuard → "+" → scansiona il QR.
   **Portatile Linux**: copia `$DATA_DIR/wireguard/peer_portatile/peer_portatile.conf` in
   `/etc/wireguard/wg0.conf` e `sudo wg-quick up wg0`.
4. Se cambi `WG_ALLOWEDIPS`/`WG_HOST`, le conf vanno rigenerate: cancella la cartella `peer_<nome>` e
   `docker compose up -d wireguard`, poi riscansiona.

Il pannello (sezione WireGuard) mostra ogni peer con ultimo handshake, endpoint e traffico: **online** = handshake
negli ultimi 3 minuti.

## Revocare un dispositivo (telefono perso)

Togli il nome da `WG_PEERS`, cancella `$DATA_DIR/wireguard/peer_<nome>` e `docker compose up -d wireguard`:
il peer sparisce dalla configurazione del server e non può più collegarsi.

## Cosa raggiungi dalla VPN

Con il tunnel attivo, dal telefono: pannello `http://<IP_SERVER>:8088`, Immich `http://<IP_SERVER>:2283`,
Vaultwarden `https://<VW_HOST>:8443`, più qualsiasi dispositivo della LAN. Il traffico esce dal container con NAT
verso la rete del server, quindi non servono rotte aggiuntive sul router.

## Test senza router (sul PC, prima di comprare il Raspberry)

1. `WG_HOST=<IP LAN del PC>` e avvia i container.
2. Con il telefono sul **Wi-Fi di casa** importa il QR e attiva il tunnel.
3. Nel pannello il peer deve passare a *online*. Se sì, la parte WireGuard funziona: per l'uso da fuori manca solo
   l'inoltro porta/DDNS.

## Sicurezza

- Apri **solo** `51820/udp`. Mai 8088, 2283 o 8443.
- Il pannello comanda Docker (equivale a root): imposta `API_TOKEN` e raggiungilo solo da LAN/VPN.
- Le `.conf` e i QR contengono la chiave privata del client: non mandarli per chat/mail, cancellali dopo l'uso.
- `LOG_CONFS=false` evita di stampare i QR nei log del container.

## Problemi comuni

| Sintomo | Cosa controllare |
|---|---|
| Nessun handshake | Porta 51820/udp inoltrata? `WG_HOST` corretto? CGNAT? Firewall del server (`ufw allow 51820/udp`) |
| Handshake ok, ma non raggiungo nulla | `WG_ALLOWEDIPS` non include la tua LAN reale; il peer non è stato rigenerato dopo la modifica |
| I siti non si aprono ma gli IP sì | DNS: imposta `PEERDNS=1.1.1.1` in `compose.yaml` e rigenera i peer |
| Il container si riavvia in loop | Manca il modulo kernel WireGuard (su Raspberry OS recente c'è già); guarda `docker logs wireguard` |
| Raggiungo la LAN ma non il pannello sul server stesso | Controlla che la porta sia pubblicata (`docker ps`) e che il firewall del server permetta il traffico dal tunnel |
