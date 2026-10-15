# Download remoto con SteamCMD

```
pannello ──▶ backend ──docker.sock──▶ container one-shot "steamcmd_<appid>" ──▶ $STEAM_GAMES_DIR/<appid>/
```

Dal pannello inserisci un AppID e scegli la piattaforma: il backend lancia un container SteamCMD che scarica il
gioco e poi si ferma. Lo stato e i log si vedono nel pannello. Per i giochi per il tuo PC Windows lascia
**platform = windows**: SteamCMD scarica i file Windows anche se gira su Linux.

## Account: anonymous o il tuo

- `anonymous` funziona solo per app gratuite e dedicated server.
- I tuoi giochi richiedono il tuo account. Il login con Steam Guard si fa **una volta** a mano:

```bash
docker compose run --rm steamcmd +login IL_TUO_USERNAME
# inserisci password e codice Steam Guard, poi:
quit
```

Il token resta in `$DATA_DIR/steamcmd`. Da quel momento nel pannello metti solo lo username nel campo login
(la password **non** passa mai dal pannello né compare in `docker inspect`). Se il token scade, ripeti il comando.
Se un download con account resta fermo, guarda i log: probabilmente sta chiedendo la password.

Un solo download alla volta (SteamCMD condivide la cartella di config): un secondo avvio riceve `409`.

## Dove vanno i file e che disco usare

| Cosa | Dove | Filesystem |
|---|---|---|
| Config/token di SteamCMD | `$DATA_DIR/steamcmd` | **Linux (ext4)**: usa symlink, su exFAT/NTFS si rompe |
| Giochi scaricati | `$DATA_DIR/steam-games` | **Linux (ext4)**, come il resto dei dati del progetto |

I percorsi sono fissi e vengono preparati da `./src/scripts/sync-env.sh` dentro `data/` nel progetto.
Non spostare giochi o configurazione su partizioni NTFS/exFAT: database, token e giochi sono mantenuti sul
filesystem Linux (ext4).

## Usare i giochi sul PC Windows

I file arrivano in `<AppID>/` con il manifest in `<AppID>/steamapps/appmanifest_<AppID>.acf`. Per farli vedere a Steam:

1. Su Windows: Steam → Impostazioni → Download → Cartelle della libreria → aggiungi una cartella sul disco esterno.
2. Sposta la cartella del gioco in `<libreria>\steamapps\common\<NomeCartella>` (il nome è il campo `installdir`
   del manifest) e copia l'`.acf` in `<libreria>\steamapps\`.
3. In Steam premi "Installa" sul gioco: rileva i file già presenti e si limita a verificarli.

È la procedura standard di Steam per file già copiati, ma provala con un gioco piccolo prima di scaricarne uno da 80 GB.

## Sul Raspberry (da sapere prima di comprarlo)

SteamCMD è un binario **x86 a 32 bit**, e l'immagine Docker è per x86_64. Un Raspberry (ARM) può eseguirlo solo
tramite emulazione (box86/box64 o FEX), una strada della community: funziona per molti, ma non è supportata da
Valve ed è più lenta e fragile. Prima dell'acquisto scegli:

- Raspberry + emulatore (verifica guide recenti per il tuo modello), oppure
- un mini PC x86 usato: stesso `compose.yaml`, nessuna emulazione, di solito nella stessa fascia di prezzo (da controllare).

Tutto il resto (Immich, Vaultwarden, Tailscale, Jellyfin, Pi-hole, pannello) ha immagini ARM e gira sul Pi.

## API

| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/api/steam/downloads` | `{"appid": 440, "platform": "windows", "login": "anonymous", "validate_files": true}` |
| GET | `/api/steam/downloads` | elenco download (stato, exit code) |
| GET | `/api/steam/downloads/{appid}/logs?tail=40` | ultime righe di log |
| DELETE | `/api/steam/downloads/{appid}` | annulla/rimuovi (i file scaricati restano) |
| GET | `/api/steam/library` | giochi su disco, letti dai manifest |
