# Recyclarr (profili di qualità per Radarr e Sonarr)

**Recyclarr** copia in Radarr e Sonarr i profili di qualità e i punteggi (*custom format*) delle guide [TRaSH](https://trash-guides.info), così non li configuri a mano
e restano aggiornati. Non scarica nulla e non tocca i film che hai già: crea o aggiorna i **profili**, poi sei tu a sceglierli.

Nel pannello fa parte del gruppo **Download automatici** (si spegne con gli altri). Una volta al giorno sincronizza, il resto del tempo sta fermo (pochi MB).

## Come funziona la configurazione

- Il file è `data/recyclarr/config/recyclarr.yml`. `sync-env.sh` lo crea la prima volta dal modello `recyclarr/recyclarr.yml` e **poi non lo tocca più**: è tuo.
- Le chiavi API di Radarr e Sonarr non stanno nel file: arrivano dal `.env` (`RADARR_API_KEY`, `SONARR_API_KEY`) tramite `!env_var`.
  Le scrive `./src/scripts/post-avvio.sh` leggendole dalla configurazione di Radarr e Sonarr (esiste solo dopo il loro primo avvio). `start.sh` lo lancia da solo.
- Il modello usa due profili con `trash_id`:
  - Radarr: **HD Bluray + WEB** (1080p). Per il 4K sostituisci l'ID con `64fb5f9858489bdac2af690e27c8f42f` (**UHD Bluray + WEB**).
  - Sonarr: **WEB-1080p**.

  Un profilo con `trash_id` porta con sé i custom format e i punteggi consigliati dalla guida. L'elenco aggiornato dei profili:
  `docker compose run --rm recyclarr config list templates` (e, dal sito di Recyclarr, gli ID per Sonarr e Radarr).

## Primo avvio

```bash
./src/scripts/start.sh                    # (o: docker compose up -d recyclarr, poi ./src/scripts/post-avvio.sh)
docker compose run --rm recyclarr sync    # prima sincronizzazione subito, senza aspettare la notte
docker compose logs recyclarr             # cosa ha fatto
```

Poi in **Radarr / Sonarr** (Impostazioni, Profili) compaiono i nuovi profili. Per usarli:

- in **Seerr** (Impostazioni, Radarr / Sonarr) scegli il nuovo profilo come predefinito per le richieste;
- per i contenuti già in libreria, in Radarr/Sonarr (Modifica in blocco) cambia il profilo: **può far riscaricare** versioni migliori, valuta prima.

Se la sincronizzazione scrive che la chiave API manca o non è valida: `./src/scripts/post-avvio.sh` (con Radarr e Sonarr accesi almeno una volta) e poi di nuovo `sync`.

## Preferire l'audio italiano

Recyclarr gestisce solo i custom format delle guide TRaSH, che non conoscono l'italiano. Il formato per l'audio italiano si crea **a mano** in Radarr e Sonarr:

1. Impostazioni, *Custom Formats*, aggiungi **Audio italiano**.
2. Condizioni (basta che una sia vera): *Language* = Italian, oppure *Release Title* con l'espressione `\b(ITA|ITALIAN|MULTI)\b`.
3. Nel profilo di qualità (*Impostazioni, Profili*) dai al formato un punteggio positivo (per esempio +150): a parità di qualità vince la versione con l'audio italiano.

Non è una garanzia: se esiste solo la versione in inglese, la scarica lo stesso (a meno di alzare il *Minimum Custom Format Score*).

> **Attenzione a `reset_unmatched_scores`.** Se lo attivi nel `recyclarr.yml`, Recyclarr azzera i punteggi di **tutti** i custom format che non gestisce lui, compreso quello dell'audio italiano.
> Lasciarlo spento (com'è nel modello), oppure elencare il tuo formato tra le eccezioni (`except`).

## Compressione con Unmanic

I profili TRaSH per l'HD penalizzano i file x265. Con [Unmanic](compressione.md) ricodifichi in HEVC dopo l'importazione: i file già importati non vengono riscaricati per questo,
ma i nuovi download possono preferire release x264. Se vuoi scaricare direttamente in HEVC, cambia il punteggio del formato *x265 (HD)* nella sezione `custom_formats` del `recyclarr.yml`:
quello che modifichi a mano in Radarr o Sonarr su un formato gestito da Recyclarr viene riscritto a ogni sincronizzazione.

## Orario e comandi

| Cosa | Come |
|---|---|
| Orario della sincronizzazione | `RECYCLARR_SCHEDULE` nel `.env` (`@daily` di serie; oppure cron a 5 campi tra virgolette), poi `docker compose up -d recyclarr` |
| Sincronizza ora | `docker compose run --rm recyclarr sync` |
| Vedere cosa cambierebbe | `docker compose run --rm recyclarr sync --preview` |
| Log | `docker compose logs recyclarr` |

I dati (`data/recyclarr/config`) sono tra le fonti del backup Restic.
