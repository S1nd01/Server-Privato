# Tailscale (accesso da fuori casa)

Sostituisce WireGuard: crea una rete privata tra i tuoi dispositivi **senza aprire porte sul router**, senza DDNS e
funziona anche se il provider usa il CGNAT. In più dà un indirizzo HTTPS con certificato valido, indispensabile per
installare il pannello come app sul telefono.

## Preparazione (una volta sola)

1. Crea un account gratuito su https://login.tailscale.com.
2. **Settings, DNS**: attiva *MagicDNS* e, più in basso, *HTTPS Certificates*. Senza questo non c'è HTTPS.
3. **Settings, Keys, Generate auth key**: lascia le opzioni di default (puoi spuntare *Reusable* se pensi di rifare il setup). Copia la chiave.
4. Nel `.env` del server: `TS_AUTHKEY=<la chiave>` (e, se vuoi, `TS_HOSTNAME=homeserver`).
5. `docker compose up -d --build --remove-orphans`
6. Nell'elenco **Machines** del pannello Tailscale, per `homeserver` scegli *Disable key expiry*, altrimenti dopo 180 giorni il server si scollega.
7. Togli `TS_AUTHKEY` dal `.env`: serve solo al primo avvio.

Senza chiave: apri il pannello (http://localhost:8088, sezione Rete) e usa il pulsante *Accedi a Tailscale*.

## Sul telefono

1. Installa l'app **Tailscale** e accedi con lo stesso account.
2. Apri nel browser l'indirizzo `https://homeserver.<tuarete>.ts.net` (lo vedi nel pannello, sezione Rete, con il pulsante Copia).
3. Installa il pannello come app: vedi `pwa.md`.

| Indirizzo | Servizio |
|---|---|
| `https://<nome>.ts.net` | Pannello |
| `https://<nome>.ts.net:2283` | Immich |
| `https://<nome>.ts.net:8096` | Jellyfin |
| `https://<nome>.ts.net:8443` | Vaultwarden |
| `https://<nome>.ts.net:8053/admin` | Pi-hole |
| `https://<nome>.ts.net:5055` | Seerr (richieste di film e serie) |

L'elenco è nel file `tailscale/serve.json`.

## Da sapere

- Il pannello è raggiungibile da qualunque tuo dispositivo nella rete Tailscale: resta protetto dal token.
- Se `docker compose exec tailscale tailscale serve status` non elenca le 6 porte, il file `serve.json` non è stato letto: controlla `docker compose logs tailscale`.
- Il nome `.ts.net` compare nei registri pubblici dei certificati (si vede che esiste, non cosa contiene).
- Il container usa la modalità "userspace": non serve `NET_ADMIN`, ma il server stesso non vede gli altri dispositivi (basta per questo uso).
- Per usare il server come uscita (exit node) o raggiungere la LAN di casa servono impostazioni in più: non sono attivate.
