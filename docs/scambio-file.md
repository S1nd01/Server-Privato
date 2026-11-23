# Scambio file (Copyparty)

Una pagina web per passare file tra i tuoi dispositivi: carichi dal telefono, scarichi dal PC. Funziona anche come disco di rete via WebDAV.
Condivide **una sola cartella**, `data/scambio` sul server (dentro il container è `/w`): non vede `/media`, le foto né altro.

È una cartella **di passaggio**, non un archivio: non entra nel backup. Quello che deve restare va spostato altrove.

## Primo avvio

```bash
./src/scripts/copyparty-setup.sh     # crea l'account e la configurazione (mostra la password una volta sola)
docker compose up -d copyparty
```

Lo script va lanciato **prima**: se manca `data/copyparty/cfg/copyparty.conf` il container non parte, ed è voluto (la configurazione di serie di Copyparty lascia la cartella a chiunque).
Un solo account (di serie il tuo utente di sistema, `--utente NOME` per un altro), nessun accesso anonimo. Password persa: `./src/scripts/copyparty-setup.sh --reimposta` (riavvia da solo il container).

## Come ci si arriva

| Da dove | Indirizzo | Note |
|---|---|---|
| Fuori casa o dentro, con Tailscale | `https://<nome>.<rete>.ts.net:3923` | HTTPS, è il modo consigliato |
| Dal server stesso | `http://127.0.0.1:3923` | |
| Da un dispositivo di casa **senza** Tailscale | `http://<IP del server>:3923` | solo se imposti `COPYPARTY_BIND_ADDR` nel `.env` (IP del server o `0.0.0.0`) e rilanci `docker compose up -d copyparty` |

**In LAN il traffico è HTTP**: password e file passano in chiaro sul Wi-Fi di casa. Va bene su una rete di cui ti fidi, non con ospiti sul Wi-Fi; nel dubbio usa Tailscale anche in casa.

## Disco di rete (WebDAV)

Windows: «Connetti unità di rete» con l'indirizzo HTTPS di Tailscale; Android e iOS: qualsiasi app di file con supporto WebDAV; Linux: `davfs2` o il gestore file. Utente e password sono quelli dello script.
Il client WebDAV di Windows è lento e con i file grandi è meglio la pagina web.

## Perché questa soluzione

Samba si monta nativamente su ogni sistema ma ha una superficie d'attacco ampia e va legato con cura alla LAN; Nextcloud farebbe tutto ma è pesante (database, Redis) e si sovrappone a Immich e Syncthing.
Copyparty è un solo processo Python, con protocolli spenti di serie (FTP, SMB e il resto non sono attivi), in un container `read_only`, senza privilegi e con un utente non root.

## Cosa non è provato

Non l'ho potuto avviare con l'immagine reale (qui non si scarica da Docker Hub). Da verificare al primo avvio:
- **`read_only: true`**: se `docker logs copyparty` lamenta una scrittura fuori da `/hist`, `/w` o `/tmp`, togli quella riga dal compose e dimmelo.
- **Indirizzo dei client**: dietro Tailscale Serve nei log compaiono tutti con l'indirizzo del container Tailscale (`rproxy` non è impostato). Non cambia la sicurezza, solo cosa vedi nei log.
- **L'immagine `copyparty/ac`** è una delle varianti ufficiali (con audio e copertine). Se vuoi la più piccola, cambia `COPYPARTY_IMAGE` nel `.env` con quella senza componenti extra, e fissa una versione (`./src/scripts/pin-images.sh`).
