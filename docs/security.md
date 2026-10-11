# Sicurezza

Obiettivo realistico: un server in casa, raggiungibile da fuori **solo** via Tailscale. Nessuna misura qui è
"a prova di tutto": sono protezioni concrete contro gli errori e gli attacchi più probabili.

## Token del pannello

Il pannello comanda Docker (equivale a root sul sistema), quindi ogni chiamata `/api` richiede un token.

```bash
./scripts/gen-api-token.sh          # genera 256 bit casuali, mostra il token UNA volta
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
| Configurazione sbagliata | Hash malformato ⇒ `503` (si chiude, non si apre); nessun token ⇒ auth disattivata (solo per prove) |
| XSS nel pannello | Il frontend scrive i dati con `textContent`, mai `innerHTML`; CSP rigida: solo file dello stesso sito, niente script o stili inline |
| Click-jacking, sniffing del tipo di file | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` sulle API |

Limiti da conoscere: il token sta nel `sessionStorage` del browser (sparisce chiudendo la scheda) oppure, se spunti "Ricorda su questo dispositivo",
nel `localStorage` (resta finché non esci dall'app: usalo solo su un telefono tuo e con blocco schermo). Uno script iniettato potrebbe leggerlo: per questo la CSP; e se qualcuno ottiene accesso al socket Docker o al tuo utente
sul server, il token non serve più. Il limite dei tentativi è per client visto da nginx.

## Rete

- Il pannello è pubblicato solo su `127.0.0.1:8088`: dalla LAN non si raggiunge, nemmeno con il token.
- Sul router non si apre **nessuna** porta. Tailscale fa uscire il server verso la tua rete privata: da fuori
  ci si entra solo con un dispositivo che hai approvato nel tuo account Tailscale.
- Tutte le porte dei servizi sono pubblicate su `127.0.0.1` (`BIND_ADDR=127.0.0.1`): nemmeno la rete di casa le vede.
  Metti `BIND_ADDR=0.0.0.0` solo se serve (es. TV con Jellyfin) e limita le porte con il firewall.
- Il DNS di Pi-hole ascolta su `127.0.0.1` finché non decidi diversamente (`PIHOLE_DNS_BIND`).
- Il container Tailscale non si ferma né si riavvia dal pannello: se ti colleghi tramite lui, perderesti l'accesso.
- Sulla WSL con rete "mirrored": non usare `-DefaultInboundAction Allow`; con `BIND_ADDR=127.0.0.1` non serve aprire nulla.
- Gli indirizzi `.ts.net` finiscono nei registri pubblici dei certificati (Certificate Transparency): il nome è visibile,
  i contenuti no. Non metterci nomi che non vuoi rendere pubblici.

## Cifratura nei vari punti

| Cosa | Come |
|---|---|
| Vault delle password | AES-256 lato client (Bitwarden), Vaultwarden vede solo dati cifrati |
| Backup di Vaultwarden | AES-256 (GnuPG simmetrico) con passphrase da file, integrità verificata |
| Connessione a Vaultwarden | TLS (Caddy, CA locale) |
| Accesso da fuori | Tailscale: tunnel WireGuard cifrato (ChaCha20-Poly1305) + HTTPS con certificato valido |
| Backup Restic | AES-256 (CTR) con autenticazione Poly1305-AES; la passphrase sta in un file a parte |
| Immich | HTTP in LAN; da fuori casa passa da Tailscale in HTTPS |

## Promemoria

- Aggiorna le immagini (`docker compose pull`) e Windows/Ubuntu: la maggior parte dei buchi reali sono lì.
- Nel pannello di Tailscale disattiva la scadenza della chiave del server (altrimenti dopo 180 giorni si scollega).
- Salva la passphrase di Restic anche fuori dal server: senza, i backup sono illeggibili.
- Account Vaultwarden creato ⇒ `VW_SIGNUPS=false`. Master password lunga e unica, con 2FA.
