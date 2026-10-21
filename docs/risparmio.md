# Modalità Risparmio

Nella sezione **Servizi** del pannello, sopra le schede, ci sono due pulsanti: **Risparmio** e **Normale**. Con un tocco accendono o spengono più gruppi insieme, invece di usare gli interruttori uno a uno.

| Modalità | Cosa fa |
|---|---|
| **Risparmio** | Spegne **Immich** (server, database, cache), **Immich, riconoscimento** e tutti i **Download automatici** (qBittorrent, Radarr, Sonarr, Prowlarr, Bazarr, FlareSolverr) |
| **Normale** | Riaccende **Immich** e i **Download automatici**. Il riconoscimento di Immich resta com'è: se lo tieni spento, rimane spento |

Il pulsante evidenziato è la modalità attiva: lo è quando tutti i suoi gruppi sono già nello stato che produce. Se hai acceso o spento qualcosa a mano, nessun pulsante è evidenziato e sotto compare la descrizione di entrambe.
Tutto il resto (Jellyfin, Vaultwarden, Pi-hole, Tailscale, Manutenzione, Compressione…) non viene toccato.

## Da sapere

- **Resta anche dopo un riavvio.** I container fermati dal pannello restano fermi anche se il server si riaccende (`restart: unless-stopped`).
  Attenzione però a `docker compose up -d`: ricrea e riavvia **tutto** quello che è nel compose, anche ciò che avevi spento. Dopo un aggiornamento, riapplica Risparmio dal pannello.
- **Immich spento = niente backup foto dal telefono.** L'app aspetta e riprova quando lo riaccendi. Se vuoi risparmiare ma continuare a ricevere le foto, spegni solo *Immich, riconoscimento* dal suo interruttore.
- **Uptime Kuma** segnalerà come "giù" i servizi spenti, se li monitora: metti in pausa quei monitor o accetta gli avvisi.
- **I download in corso si interrompono** (qBittorrent riprende da dove era arrivato quando lo riaccendi).
- **Container non ancora creati** (per esempio se non hai mai avviato un servizio) vengono saltati, senza errori.

## Cambiare o aggiungere modalità

Le modalità sono definite in `MODES`, nel file `src/backend/app/services.py`: un nome, una descrizione, l'azione (`stop` o `start`) e l'elenco dei gruppi (gli id sono le chiavi di `SERVICES`).
Per esempio, una modalità "Solo foto" che spegne i download e lascia Immich:

```python
    "solo-foto": {
        "name": "Solo foto",
        "description": "Spegne i download automatici e lascia Immich",
        "action": "stop",
        "services": ["download"],
    },
```

Poi `docker compose up -d --build backend` e ricarica il pannello. Tailscale non viene mai fermato da una modalità, anche se lo metti nell'elenco.

API: `GET /api/modes` elenca le modalità, `POST /api/modes/{id}/apply` applica una modalità (fino a 4 container per volta, così non si aspettano i 10 secondi di arresto di ciascuno).
