# Portainer

Interfaccia grafica per Docker: container, log, volumi, reti, aggiornamento delle immagini. Complementa il pannello del progetto,
che accende e spegne i gruppi di servizi: qui entri nei dettagli di ogni container.

| Dove | Indirizzo |
|---|---|
| Dal server | `https://localhost:9443` (certificato autofirmato: l'avviso del browser è normale) |
| Da Tailscale | `https://<nome>.<rete>.ts.net:9443` (certificato valido, via `tailscale/serve.json`) |

I dati stanno in `data/portainer`, dentro la cartella unica del progetto.

## Primo avvio

1. `docker compose up -d portainer`
2. Entro **5 minuti** apri l'indirizzo e crea l'utente amministratore (password lunga). Oltre il limite Portainer si blocca per
   sicurezza: `docker compose restart portainer` e riprova.
3. Scegli l'ambiente *Get Started* (Docker locale).

## Sicurezza

Portainer monta `/var/run/docker.sock`, come il backend del pannello: chi entra controlla la macchina. Per questo:

- la porta `9443` è pubblicata **solo su `127.0.0.1`** e non segue `BIND_ADDR`: non aprirla mai in LAN né sul router;
- da fuori si passa solo da Tailscale;
- l'amministratore deve avere una password lunga e unica.

## Se lo avevi già avviato con la versione precedente

Prima i dati finivano in `homeserver-data/portainer`. Per tenere l'utente e le impostazioni:

```bash
docker compose stop portainer
mkdir -p data/portainer
cp -a homeserver-data/portainer/. data/portainer/
docker compose up -d portainer
```

Poi, a prova fatta, cancella `homeserver-data`.
