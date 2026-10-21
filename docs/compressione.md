# Compressione video (Unmanic)

**Unmanic** ricodifica i film e le serie che hai già in libreria (di solito da H.264 a HEVC/H.265) per liberare spazio. Nel pannello è la scheda **Compressione video** nel blocco **Utility**,
con un interruttore a parte: **tienilo spento finché non serve**, perché la conversione porta la CPU al massimo per ore.

| Dove | Indirizzo |
|---|---|
| Dal server | http://localhost:8888 |
| Da Tailscale | `https://<nome>.ts.net:8888` |

Unmanic **non ha autenticazione**: per questo la porta è su `127.0.0.1` e da fuori si passa solo da Tailscale (la tua rete personale). Non aprirla in LAN con `BIND_ADDR=0.0.0.0` senza proteggerla.

## Prima di cominciare: ha senso sul tuo server?

- **Dell Inspiron (adesso):** sì, con cautela. Con la sola CPU (x265) un film di 2 ore in 1080p può richiedere diverse ore. Se la CPU è Intel con grafica integrata, la codifica HEVC con
  l'accelerazione hardware (QuickSync/VAAPI) è molto più veloce e leggera: controlla con `ls /dev/dri` sul server. Se la cartella esiste, togli il commento alle righe `devices:` di `unmanic` in `compose.yaml`.
  Non funziona nella WSL.
- **Raspberry Pi (dopo):** in pratica no. Il Pi 5 non ha un codificatore video hardware e il Pi 4 codifica solo H.264, non HEVC: resterebbe x265 sulla CPU, lentissimo e con il server al limite.
  Se passi al Pi conviene comprimere sul PC e poi spostare i file, oppure lasciar perdere.
- **Compatibilità:** l'HEVC va riprodotto senza ricodifica (*direct play*) dai tuoi dispositivi (TV, telefono, browser). Dove non è supportato, Jellyfin ricodifica al volo e perdi il vantaggio, caricando pure la CPU.
  Prova con **un solo file** e guarda nel pannello di Jellyfin (Dashboard, Attività) se sul tuo dispositivo parte in *direct play*.
- **Risparmio:** da H.264 a HEVC si guadagna in genere tra un terzo e la metà dello spazio a qualità simile. I file già in HEVC non servono, e i file piccoli o già molto compressi risparmiano poco.

## Avvio

```bash
./src/scripts/sync-env.sh        # crea data/unmanic/config e data/unmanic/cache
docker compose up -d unmanic
```

Nel `.env` (facoltativo) puoi cambiare i limiti:

| Variabile | Valore di serie | Significato |
|---|---|---|
| `UNMANIC_CPUS` | `2` | tetto di CPU del container, in core (lascia liberi gli altri per Jellyfin e il resto) |
| `UNMANIC_MEM` | `2g` | tetto di RAM (4K e preset lenti possono volerne di più) |

## Configurazione

I nomi delle voci e dei plugin possono cambiare tra versioni.

1. **Libreria:** Impostazioni, Libreria, aggiungi `/media/Film` e `/media/Serie TV` (Unmanic vede la stessa cartella `/media` di Radarr, Sonarr e Jellyfin).
   **Non** aggiungere `/media/downloads`: sono i file ancora in condivisione (seeding) e quelli appena scaricati.
2. **Worker:** Impostazioni, Worker: **1**. Due conversioni in parallelo non vanno più veloci su una CPU sola, la saturano soltanto.
3. **Plugin** (Impostazioni, Plugin, installa dall'elenco della comunità e aggiungili al flusso della libreria):
   - un **transcodificatore video** con codifica HEVC (libx265, o l'encoder hardware se hai abilitato `/dev/dri`); come punto di partenza una qualità CRF intorno a 22–24 e l'audio copiato senza modifiche;
   - un plugin che **salti i file già in HEVC** (o la regola equivalente del transcodificatore);
   - i plugin che avvisano **Radarr** e **Sonarr** del file cambiato, se vuoi che aggiornino le informazioni.
4. **Orario:** meglio di notte o quando non guardi nulla. Se un'attività dura più del previsto, spegni la scheda dal pannello: il file in corso va perso, quelli già convertiti restano.
5. **Prova:** prima di lasciarlo girare su tutta la libreria, convertine uno e guardalo su Jellyfin.

## Cose da sapere

- **Il file in libreria viene sostituito** da quello ricompresso. Se il file originale era un collegamento fisico (hardlink) a quello in `downloads` ancora in condivisione, il collegamento si rompe:
  la copia in `downloads` continua a occupare il suo spazio finché non la rimuovi da qBittorrent. Il risparmio vero arriva dopo.
- **Estensione del file:** se la conversione cambia il contenitore (per esempio da `.mp4` a `.mkv`) Radarr e Sonarr vedono il vecchio file sparito finché non lo rileggono. Tenere lo stesso contenitore o usare i plugin di notifica evita il problema.
- **Spazio temporaneo:** la conversione scrive in `data/unmanic/cache`, circa un file per worker. Serve spazio libero pari al file più grande.
- **Autoheal:** con la CPU al massimo gli altri servizi possono rispondere piano ai controlli di salute; per questo il container ha un tetto di CPU. Vedi [manutenzione.md](manutenzione.md).
- **Backup:** `data/unmanic/config` (impostazioni e flusso dei plugin) non è tra le fonti di Restic.

## Risorse

Con `UNMANIC_CPUS=2` e `UNMANIC_MEM=2g` un server a 4 core resta usabile mentre converte; Jellyfin e Vaultwarden hanno priorità sul resto (`cpu_shares`). Il container è anche il primo a essere fermato se la RAM finisce (`oom_score_adj`).
