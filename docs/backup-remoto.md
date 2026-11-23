# Backup fuori sede (rclone)

Il backup Restic ([restic.md](restic.md)) sta sul computer o su un disco collegato: se il server prende fuoco, viene rubato o il disco muore insieme ai dati, perdi tutto.
Questa copia mette l'archivio **anche fuori casa** (un servizio cloud, un altro disco, il server di un amico via SFTP).

L'archivio è già cifrato da Restic: sul servizio remoto finiscono solo file cifrati. Ma **senza la passphrase (`RESTIC_PASSWORD_FILE`) non si ripristina nulla**: tienine una copia fuori dal server (per esempio in Vaultwarden e su carta).

## Come funziona

`./src/scripts/backup-remoto.sh` lancia `rclone sync` dall'archivio locale (montato **in sola lettura**: rclone non può modificarlo) al «remote» che scegli.
Non è una funzione del pannello e non parte da solo: lo lanci a mano o da cron/systemd. Il backup Restic resta quello del pannello: questo script copia ciò che c'è.

## Primo uso

```bash
./src/scripts/backup-remoto.sh --config      # procedura guidata di rclone: scegli il servizio e crea il remote (per esempio "b2")
# nel .env:  RCLONE_REMOTE=b2:nome-bucket/homeserver-restic
./src/scripts/backup-remoto.sh --prova       # mostra cosa farebbe, senza fare nulla
./src/scripts/backup-remoto.sh               # la prima copia (può durare ore: dipende dalla dimensione e dalla tua linea)
./src/scripts/backup-remoto.sh --stato       # data dell'ultima copia riuscita
```

Le credenziali del remote stanno in `data/rclone/rclone.conf` e **non** entrano nel backup (altrimenti le troveresti nella copia stessa).

## Pianificarlo

Dopo un backup Restic riuscito, una volta a settimana basta. Esempio con cron (col tuo utente, `crontab -e`), la domenica alle 5:
```
0 5 * * 0  cd /percorso/del/progetto && ./src/scripts/backup-remoto.sh >> /tmp/backup-remoto.log 2>&1
```
Per essere avvisato se si ferma: in Uptime Kuma crea un monitor di tipo **Push** con intervallo di 8 giorni e metti il suo indirizzo in `BACKUP_REMOTO_KUMA_PUSH` nel `.env`; lo script lo chiama a copia riuscita, e Kuma ti avvisa (ntfy) se passano più di 8 giorni.

## Protezioni (e cosa NON proteggono)

- Rifiuta di partire se il disco di backup non è collegato, se l'archivio locale non ha config, chiavi e almeno un'istantanea, o se un backup Restic è in corso: così non copia «il nulla» sopra una copia buona.
- Non cancella sul remoto più di `BACKUP_REMOTO_MAX_DELETE` file per volta (2000). La pulizia di Restic (`forget --prune`) può legittimamente cancellarne molti: se serve, alza il valore dopo aver guardato `--prova`.
- **Limite importante:** `sync` rende il remoto identico al locale, quindi se il server viene compromesso e l'archivio locale cancellato o cifrato da un ransomware *entro* il limite sopra, la copia remota lo segue. Contro questo servono le funzioni del servizio remoto: versioni dei file o blocco degli oggetti (per esempio il versioning di Backblaze B2 o S3 Object Lock) con una conservazione di qualche settimana. Scegli un servizio che le abbia.

## Ripristinare da zero

1. Reinstalla il server e ricrea la passphrase come file (`RESTIC_PASSWORD_FILE`).
2. Scarica l'archivio: `rclone sync <remote>:<cartella> /percorso/nuovo/archivio` (da un computer con rclone e lo stesso remote).
3. Controlla l'archivio e ripristina con le istruzioni di [restic.md](restic.md) (`restic check`, poi il ripristino dal pannello o `restic restore`).
Fai la prova **una volta** su un'altra cartella, prima di averne bisogno.

## Costi e tempi

La prima copia carica tutto l'archivio; le successive solo le novità (Restic crea file nuovi, non riscrive i vecchi). Calcola lo spazio dell'archivio e il prezzo mensile del servizio prima di scegliere. Con la linea di casa il caricamento può rallentare la rete: scegli un orario notturno.

## Cosa non è provato

Non l'ho potuto provare con un servizio remoto reale. Ho provato le protezioni dello script con un `docker` simulato (disco assente, backup in corso, archivio vuoto, errore di rclone, remote scritto male). Alla prima esecuzione guarda l'uscita di `--prova`.
