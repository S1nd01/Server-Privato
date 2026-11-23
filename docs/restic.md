# Backup con Restic

Salva Vaultwarden, le foto di Immich, la configurazione di Pi-hole, Jellyfin e dei servizi di download in un archivio **cifrato** (AES-256 con autenticazione) e deduplicato: ogni copia aggiunge solo ciò che è cambiato.

**Il backup parte solo quando l'amministratore lo avvia dal pannello** (sezione Backup). Non c'è nessun orario automatico. L'archivio sta su un **disco esterno** che colleghi al server solo quando serve.

## Perché manuale e su disco esterno

- Un disco collegato solo durante il backup non subisce una scarica sul server, un ransomware o un errore di cancellazione. Un disco lasciato **sempre collegato** protegge dal guasto dell'SSD, ma non da questi tre rischi.
- Il disco, anche se sta accanto al portatile, **non è una copia fuori casa**: un furto o un incendio colpiscono entrambi. Per quello serve una seconda destinazione (vedi Limiti).
- Un backup che dipende da te può essere dimenticato: il pannello mostra un avviso quando l'ultima copia ha più di `BACKUP_WARN_DAYS` giorni (14 di default, `0` = mai).

## Attivazione

La passphrase la crea l'installazione (`start.sh`, `sync-env.sh` o `setup-windows.bat`) la prima volta: viene salvata in `~/.restic-pass` (permessi 600) e te la mostra **una volta sola**.
**Copia la passphrase fuori dal server** (non nel Vaultwarden di questo stesso server): senza, i backup non si aprono più.

Poi collega il disco, montalo e lancia, col tuo utente e senza `sudo`:

```bash
./src/scripts/backup-disco.sh                       # elenca i dischi montati e chiede quale usare
./src/scripts/backup-disco.sh /media/utente/BACKUP  # oppure indica tu il percorso
./src/scripts/backup-disco.sh --stato               # configurazione attuale
./src/scripts/backup-disco.sh --locale              # torna all'archivio in data/backups/restic
```

Lo script controlla che sia un disco diverso da quello dei dati e che si possa scrivere, crea sul disco la cartella `homeserver-restic` e il file marcatore `.homeserver-backup`, scrive `RESTIC_REPO_DIR`, `BACKUP_DISK_DIR` e `BACKUP_MOUNT_PARENT` nel `.env` e riavvia il backend. Se esiste già un archivio locale, ti chiede se copiarlo sul disco (non lo cancella). Per un disco nuovo usa ext4: `sudo chown $USER: /media/utente/BACKUP` se non è scrivibile.

Nel pannello, sezione Backup: **Prepara l'archivio** (una volta sola) e **Esegui backup**. A lavoro finito: espelli il disco dal sistema e scollegalo.

## Cosa succede se il disco non è collegato

Il disco si riconosce dal file `.homeserver-backup`, che esiste solo sul disco. Senza, il pannello rifiuta ogni operazione ("Il disco di backup non è collegato"). Il controllo serve perché Docker, davanti a un percorso inesistente, **lo crea sul disco di sistema**: senza il marcatore, un backup a disco scollegato riempirebbe l'SSD del server credendo di scrivere sul disco esterno. Per lo stesso motivo il servizio `restic` monta l'archivio con `create_host_path: false`.

Il backend vede il disco anche se lo colleghi dopo l'avvio perché monta la cartella madre (`BACKUP_MOUNT_PARENT`, per esempio `/media/utente`) in sola lettura con propagazione `rslave`. Serve che la radice dell'host sia condivisa. Se `docker compose up` risponde *not a shared or slave mount*:

```bash
sudo mount --make-rshared /
```

(Su Ubuntu con systemd di solito è già così; il comando vale fino al riavvio.)

## Chi può fare il backup

Solo l'amministratore. Le rotte che scrivono (`POST /api/backup/jobs`: prepara, backup, pulisci, controlla) dichiarano `require_admin` e `check-config.py` controlla che non ne compaia una senza. **Oggi `require_admin` non distingue ancora i ruoli**: l'accesso al pannello è con un solo token, quindi chi entra è amministratore. Il vincolo diventa effettivo quando arriveranno gli utenti con ruoli.

## Pulizia delle copie vecchie

Anche la pulizia è manuale (pulsante **Pulisci copie vecchie**): tiene 7 copie giornaliere, 4 settimanali e 6 mensili. Fai una pulizia ogni tanto, altrimenti il disco si riempie.

## Cosa viene salvato

`vaultwarden`, `immich/upload` (foto e i dump automatici del database), `pihole`, `jellyfin/config`, le configurazioni di
`seerr`, `radarr`, `sonarr`, `prowlarr` e `qbittorrent`, `bazarr`, `kuma` (Uptime Kuma), `ntfy` (utenti e argomenti, non la cache dei messaggi),
`beszel`, `unmanic` (solo le impostazioni), `panel` (stato del pannello) e `tailscale` (l'identità del server: ripristinarla mantiene lo stesso
indirizzo `.ts.net`), e `photos`. Portainer e Diun non sono inclusi. Film, serie e download in `media/` **non** sono inclusi.
Miniature, video convertiti, registri e locandine di Radarr/Sonarr sono esclusi (si rigenerano).
Prima del backup Vaultwarden viene copiato in modo coerente; se non riesce, il backup parte comunque e te lo dice.

**Verifica una volta** in Immich (Amministrazione, Impostazioni, *Backup del database*) che i dump automatici siano attivi: il database non viene copiato mentre è in uso.

Il backup notturno di Vaultwarden (GnuPG, ultime 14 copie, cron alle 03:00 se l'hai attivato) è un'altra cosa: resta **automatico**, locale in `data/backups/vaultwarden`, e non passa dal disco esterno.

## Ripristino

Con il disco collegato:

```bash
docker compose --profile tools run --rm restic -r /repo snapshots
docker compose --profile tools run --rm restic -r /repo restore latest --target /restore
```
I file ripristinati compaiono in `$DATA_DIR/restore`: copiali al loro posto a servizi fermi.
Prova un ripristino una volta, quando va tutto bene, non il giorno in cui serve.

## Limiti

- Il disco accanto al server non è una copia fuori casa. Una seconda destinazione (disco a rotazione, o un servizio remoto con `restic copy`) non è ancora collegata al pannello.
- Il pulsante *Controlla integrità* verifica la struttura dell'archivio, non legge tutti i dati.
- Il comportamento con disco collegato dopo l'avvio (propagazione `rslave`) dipende dal sistema host: provalo una volta collegando e scollegando il disco con il pannello aperto.

## Copia fuori sede

L'archivio sta sul disco di casa. Per una copia anche fuori casa (cloud, SFTP, altro disco) vedi [backup-remoto.md](backup-remoto.md); per sapere in anticipo se un disco sta per rompersi, [smart.md](smart.md).
