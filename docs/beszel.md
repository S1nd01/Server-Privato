# Beszel (storico delle risorse)

**Beszel** registra nel tempo CPU, RAM, dischi, rete, temperatura e consumo di ogni container, con grafici e avvisi. Il pannello del progetto mostra lo stato **di adesso**;
Beszel serve a rispondere a «che cosa ha riempito la RAM stanotte?» o «quando si è scaldato il server?». È molto più leggero di Grafana con Prometheus.

| Dove | Indirizzo |
|---|---|
| Dal server | http://localhost:8090 |
| Da Tailscale | `https://<nome>.ts.net:8090` |

Nel pannello è la scheda **Beszel**: un solo interruttore per due container, il *hub* (interfaccia e dati) e l'*agente* (misura il computer). Dati in `data/beszel`.

## Primo avvio

```bash
./src/scripts/start.sh          # avvia tutto e lancia post-avvio.sh, che dà all'agente la chiave del hub
```

1. Apri `http://localhost:8090` **subito** e crea l'utente amministratore: il primo che arriva lo diventa.
2. Nel hub: *Add System* (Aggiungi sistema). Scegli un nome (per esempio `homeserver`) e come **Host / IP** scrivi esattamente:

   ```
   /beszel_socket/beszel.sock
   ```

   Hub e agente parlano tramite un socket condiviso: nessuna porta in più, nessuna rete.
3. Se il sistema resta «down»: l'agente non ha ancora la chiave. `./src/scripts/post-avvio.sh` la legge da `data/beszel/data/id_ed25519.pub` e ricrea l'agente.
   Se il file non si legge, copia la chiave pubblica dalla finestra *Add System* nel `.env` (`BESZEL_KEY=...`) e `docker compose up -d beszel-agent`.
4. (Facoltativo) Per i link nelle notifiche: `BESZEL_APP_URL=https://<nome>.<rete>.ts.net:8090` nel `.env`, poi `docker compose up -d beszel`.

Poi, nelle impostazioni del hub, puoi collegare gli avvisi a **ntfy**: server `http://ntfy:80` con l'utente creato per i servizi (vedi [ntfy.md](ntfy.md)); l'indirizzo
nelle notifiche di Beszel usa il formato di Shoutrrr (`ntfy://utente:password@ntfy:80/homeserver?scheme=http`).

## Come si collega al pannello

- Nel pannello Beszel è una scheda come le altre: acceso, spento, riavvia, «Apri» e uso di CPU e RAM dei suoi container.
- Pannello e Beszel misurano cose diverse: il pannello dice **come sta ora** e accende o spegne i gruppi; Beszel tiene lo **storico** e manda gli avvisi.

## Cose da sapere

- L'agente usa la **rete dell'host** (per vedere le vere schede di rete) e monta `/var/run/docker.sock` **in sola lettura**: serve a elencare i container, ma chi controlla l'agente
  potrebbe leggere le variabili d'ambiente di tutti i container. Il suo socket con il hub è dentro `data/beszel/socket`, non è raggiungibile dalla rete.
- Memoria: hub circa 50 MB, agente circa 15 MB (tetti a 256 e 128 MB). Sul Raspberry funziona senza problemi (immagini multi-architettura).
- La **temperatura** si legge solo dove il sistema espone i sensori (Raspberry e molti PC; di solito non nella WSL).
- Perdi la password del hub: `./src/scripts/recupera-credenziali.sh beszel LA_TUA_EMAIL`.
