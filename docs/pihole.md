# Pi-hole (blocco pubblicità)

Pi-hole è un server DNS che rifiuta i nomi dei siti di pubblicità e tracker, per tutti i dispositivi che lo usano.

1. La password dell'interfaccia la genera `./src/scripts/sync-env.sh` (`PIHOLE_PASSWORD` nel `.env`).
2. `docker compose up -d pihole`, poi apri http://localhost:8053/admin.
3. Prova dal computer: `dig @127.0.0.1 doubleclick.net` deve rispondere `0.0.0.0`.

Per usarlo davvero su tutta la rete di casa:
1. Dai al server un IP fisso (prenotazione DHCP sul router).
2. Nel `.env`: `PIHOLE_DNS_BIND=<IP del server>`, poi `docker compose up -d pihole`.
3. Nel router imposta quell'IP come DNS della rete. Se Pi-hole è spento, la rete non risolve i nomi: tieni un DNS di riserva.

Attenzione su Windows/WSL: la porta 53 può essere occupata; in quel caso usalo solo per prove (127.0.0.1) e passa al vero server per l'uso in rete.

Per fargli risolvere i nomi da solo, senza Google o Cloudflare come intermediari, c'è [Unbound](unbound.md): `./src/scripts/pihole-unbound.sh on`.
