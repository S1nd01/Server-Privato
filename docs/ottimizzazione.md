# Ottimizzazione delle risorse

Tutto quello che il progetto fa per consumare poco, e le impostazioni dei singoli servizi che conviene ritoccare. Per capire dove va la RAM apri
la sezione **Servizi** del pannello: ogni scheda mostra CPU e memoria del suo gruppo.

## Cosa fa già il progetto

| Cosa | Dove | Effetto |
|---|---|---|
| Interruttori per gruppo | pannello, Servizi e Utility | Download automatici, Immich, Immich (riconoscimento), Compressione video, Uptime Kuma e gli altri si accendono e spengono a parte |
| Stato dei servizi con una sola chiamata a Docker | `src/backend/app/main.py` | meno lavoro a ogni aggiornamento del pannello |
| Statistiche senza attesa | `src/backend/app/stats.py` | la CPU si calcola dalla lettura precedente, non serve aspettare un secondo per container |
| Un solo client Docker condiviso | `src/backend/app/dockerutil.py` | niente connessioni nuove a ogni richiesta |
| Thread limitati a 16 | `src/backend/app/main.py` | quanti ne regge il client Docker condiviso |
| Statistiche ogni 15 secondi, stato ogni 5 | `src/frontend/views.js` | il pannello aperto pesa poco; in secondo piano non fa nulla |
| Backup Restic a bassa priorità | `src/backend/app/backup.py` | al massimo 2 core, lettura file meno parallela, priorità CPU ridotta |
| Rotazione dei log | `compose.yaml` (`x-logging`) | 3 file da 10 MB per container invece di log senza fine |
| Priorità CPU (`cpu_shares`) | `compose.yaml` | conta solo se il server è occupato: Immich ML, Unmanic, Diun e Autoheal cedono il passo a Jellyfin e Vaultwarden. Il gruppo Download non ha più priorità ridotta |
| Limiti di RAM | `compose.yaml` | Immich ML 3 GB, Unmanic 2 GB, Diun 128 MB, Autoheal 64 MB. Il gruppo Download (qBittorrent, FlareSolverr, Radarr, Sonarr, Prowlarr, Bazarr) non ha limiti |
| Modalità Risparmio | pannello, [risparmio.md](risparmio.md) | con un tocco spegne Immich e il gruppo Download; "Tutto acceso" li riaccende |
| Tetto di CPU | `compose.yaml` | Unmanic al massimo 2 core (`UNMANIC_CPUS` nel `.env`), così la compressione non soffoca Jellyfin |
| Riavvio di ciò che non risponde | Autoheal, [manutenzione.md](manutenzione.md) | solo i container con controllo di salute e l'etichetta `autoheal=true` |
| Protezione dall'esaurimento della RAM (`oom_score_adj`) | `compose.yaml` | se la memoria finisce, Linux ferma prima Immich ML e FlareSolverr; Vaultwarden e Tailscale sono gli ultimi |

I limiti di RAM sono prudenti, non misurati sul tuo server. Se un servizio viene riavviato da solo (`Riavvii` nella scheda del pannello), il limite è troppo basso:
alzalo in `compose.yaml` e `docker compose up -d`. Se invece ne usa molto meno, puoi abbassarlo e lasciare più RAM agli altri.

## Impostazioni dentro i servizi

I nomi delle voci possono cambiare tra versioni.

**Immich** (Amministrazione)
- *Impostazioni dei job*: riduci la concorrenza (miniature, ricerca intelligente, rilevamento volti) a 1 o 2 su un Raspberry.
- *Machine learning*: se non usi volti o ricerca per contenuto, disattivali. Così puoi tenere sempre spento **Immich, riconoscimento**.

**Jellyfin** (Pannello di controllo)
- Riproduzione, Transcodifica: lascia attivo il *throttling* della transcodifica e, se la CPU è debole, imposta un numero di thread invece di *Auto*.
- Librerie: spegni il *monitoraggio in tempo reale* sulle librerie che riempi a blocchi (lo stack arr importa comunque e avvisa Jellyfin).
- Attività pianificate: tieni una sola scansione notturna delle librerie, non più frequente.

**Radarr e Sonarr**
- Impostazioni, Indicizzatori, opzioni: *Intervallo sincronizzazione RSS* da 15 a 60 minuti.
- Impostazioni, Media: *Riesamina la cartella dopo l'aggiornamento* = *Dopo aggiornamento manuale*, non *Sempre*.

**qBittorrent** (Opzioni)
- BitTorrent, Accodamento: massimo 3 download attivi e 5 torrent attivi.
- Connessione: connessioni globali al massimo 200 e 50 per torrent.
- Velocità: un limite alternativo per le ore in cui serve la rete.

## Non ancora fatto

- **Altre modalità del pannello** (per esempio "Solo foto"): la modalità Risparmio c'è già, si possono definire altre in `src/backend/app/services.py`.
- **Spegnimento programmato**, per esempio dei download in certe ore o di Immich ML fuori dagli orari di caricamento.
- **Limiti calibrati** sull'uso reale di ogni servizio dopo qualche giorno di funzionamento.
