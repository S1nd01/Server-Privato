# Maintainerr (pulizia della libreria)

**Maintainerr** guarda la tua libreria Jellyfin e, con le regole che scrivi tu, mette in una **collezione** i film e le serie da togliere
(per esempio «mai guardati da 12 mesi»). Passati i giorni che scegli, esegue l'azione della regola: di solito **cancella da Radarr/Sonarr**, che eliminano anche i file.
Se un elemento viene riguardato nel frattempo, esce dalla collezione.

| Dove | Indirizzo |
|---|---|
| Dal server | http://localhost:6246 |
| Da Tailscale | `https://<nome>.ts.net:6246` |

Nel pannello è la scheda **Maintainerr**. I dati stanno in `data/maintainerr`. Maintainerr funziona con Jellyfin (oltre che con Plex ed Emby).

## Sicurezza: niente cancellazioni a sorpresa

Hai chiesto che **non cancelli nulla senza una tua conferma**. Maintainerr non ha un pulsante «conferma» per ogni file: la protezione sta nel modo in cui scrivi le regole.

1. **Prima regola solo di prova.** Quando crei una regola, scegli come azione **«Do nothing»** (se la tua versione la offre) oppure lascia la regola **disattivata**: così Maintainerr
   si limita a riempire la collezione in Jellyfin e **non toglie niente**. Guarda cosa propone, per qualche giorno.
2. **Elementi che non vuoi toccare**: dalla collezione (in Maintainerr, *Collections*) puoi **escludere** un elemento: non verrà mai più proposto per quella regola.
3. **Tempo per ripensarci**: nelle impostazioni della collezione c'è il numero di giorni *prima di eseguire l'azione*. Mettine parecchi (30 o più).
4. **Quando sei contento della regola**, passa all'azione che cancella. Da quel momento cancella da solo **solo gli elementi che non hai escluso**, allo scadere dei giorni.
5. Tieni attivo il backup Restic prima di abilitare una regola che cancella: i film cancellati si riscaricano (Seerr li riconosce come non presenti), ma i tuoi dati in Radarr/Sonarr no.

> La verifica di queste voci va fatta nell'interfaccia della versione che installi: i nomi delle azioni cambiano tra una versione e l'altra.
> Se non trovi un'azione che non cancella, lascia la regola disattivata e usa solo le collezioni.

## Primo avvio

```bash
docker compose up -d maintainerr
```

Apri l'indirizzo e segui l'impostazione guidata. Trattalo come se **non avesse una password** (di serie non la chiede): la porta resta su `127.0.0.1` e da fuori si arriva solo da Tailscale, come per Unmanic. Non aprirla in LAN. Se la tua versione offre un accesso con utente e password, attivalo.

Collega i servizi (nomi Docker, mai `localhost`):

| Servizio | Indirizzo | Altro |
|---|---|---|
| Jellyfin | `http://jellyfin:8096` | una chiave API: Jellyfin, Dashboard, *Chiavi API* |
| Radarr | `http://radarr:7878` | la chiave API di Radarr (Impostazioni, Generale) |
| Sonarr | `http://sonarr:8989` | la chiave API di Sonarr |
| Seerr | `http://seerr:5055` | la chiave API di Seerr (Impostazioni, Generale): serve per togliere anche le richieste dei contenuti rimossi |

I film e le serie sono **in sola lettura** per Jellyfin, ma Maintainerr non tocca i file: chiede a Radarr e Sonarr, che li eliminano. Per questo in Radarr/Sonarr
la cartella deve essere quella di sempre (`/media`), come nella catena di [Seerr](seerr.md).

## Con le altre parti del server

- **Seerr / JellyBridge:** se togli un film, scompare anche dalle richieste (se hai collegato Seerr) e potrà essere richiesto di nuovo.
- **Download automatici spenti:** se spegni il gruppo dal pannello, le regole che cancellano falliscono finché Radarr e Sonarr non sono di nuovo accesi. Non perdi nulla.
- **Risorse:** circa 150-300 MB di RAM, tetto a 512 MB. Se la RAM è poca, spegnilo dal pannello: non serve tenerlo acceso tutto il giorno (le regole girano all'orario che scegli).
