# Jellyfin (film, serie, musica)

1. I file stanno in `$DATA_DIR/media` (dentro `data/` nel progetto). Lo script crea `Film/`, `Serie TV/`, `Discoveries/` e `downloads/`; aggiungi
   a mano altre cartelle (per esempio `Musica/`). Jellyfin le legge in sola lettura, tranne `Discoveries/` (la usa il plugin JellyBridge, vedi [seerr.md](seerr.md)).
   Radarr e Sonarr riempiono `Film/` e `Serie TV/` da soli.
2. `./src/scripts/sync-env.sh` (crea le cartelle col tuo utente) e `docker compose up -d jellyfin`.
3. Apri http://localhost:8096 (o `https://<nome>.ts.net:8096` da fuori casa) e segui la procedura guidata: crea l'utente, poi *Aggiungi libreria*
   e scegli `/media/Film` (tipo Film) e `/media/Serie TV` (tipo Serie). Non aggiungere `/media/downloads`.
4. App per telefono e TV: cerca *Jellyfin*; come server usa l'indirizzo qui sopra.

Note:
- Su Raspberry Pi la conversione dei video è pesante: preferisci file che il tuo dispositivo riproduce direttamente.
- Per la TV in casa serve `BIND_ADDR=0.0.0.0` nel `.env` (e firewall che lascia entrare solo la rete di casa), oppure Tailscale sulla TV.
- Configurazione e utenti sono in `$DATA_DIR/jellyfin/config` (inclusa nel backup Restic).
