# ntfy

Server di notifiche push: un servizio (Uptime Kuma, Radarr, Sonarr, uno script) manda un messaggio a un *argomento* e l'app **ntfy** sul telefono lo mostra.
Niente account esterni: i messaggi passano dal tuo server.

| Dove | Indirizzo |
|---|---|
| Dal server | http://localhost:2586 |
| Da Tailscale | `https://<nome>.ts.net:2586` |
| Dentro Docker | `http://ntfy:80` |

I dati stanno in `data/ntfy`. L'accesso è **solo con utente e password** (`NTFY_AUTH_DEFAULT_ACCESS=deny-all`): nessun argomento è leggibile o scrivibile senza accedere.

## Primo avvio

1. Nel `.env` imposta `NTFY_BASE_URL=https://<nome>.<rete>.ts.net:2586` (lo vedi nel pannello, sezione Rete).
2. `docker compose up -d ntfy`
3. Crea il tuo utente amministratore (ti chiede la password):

   ```bash
   docker compose exec ntfy ntfy user add --role=admin IL_TUO_NOME
   ```

4. Sul telefono: installa l'app **ntfy**, Impostazioni, *Aggiungi utente* (o all'iscrizione a un argomento scegli *Usa un altro server*):
   server `https://<nome>.<rete>.ts.net:2586`, con il tuo utente e password, con Tailscale acceso. Poi *Iscriviti* all'argomento `homeserver`.
5. Prova: `docker compose exec ntfy ntfy publish -u IL_TUO_NOME homeserver "Prova"` (chiede la password).

Per i servizi conviene un utente separato con accesso limitato:

```bash
docker compose exec ntfy ntfy user add servizi
docker compose exec ntfy ntfy access servizi homeserver write-only
```

## Collegare i servizi

| Servizio | Dove | Campi |
|---|---|---|
| Uptime Kuma | Impostazioni, Notifiche, tipo Ntfy | server `http://ntfy:80`, argomento `homeserver`, utente e password |
| Radarr, Sonarr | Impostazioni, Connetti, *Ntfy* | server `http://ntfy:80`, argomento `homeserver`, utente e password; scegli gli eventi (per esempio *Importazione completata*, *Errore*) |

## Da sapere

- Sull'iPhone le notifiche istantanee richiedono di impostare `NTFY_UPSTREAM_BASE_URL=https://ntfy.sh` nel servizio (passano da ntfy.sh solo come
  segnale, senza contenuto): non l'ho attivato di proposito. Vedi la documentazione di ntfy prima di abilitarlo.
- Se il telefono non ha Tailscale acceso, non raggiunge il server e non riceve le notifiche.
