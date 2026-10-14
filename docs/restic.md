# Backup con Restic

Salva Vaultwarden, le foto di Immich, la configurazione di Pi-hole e di Jellyfin in un archivio **cifrato** (AES-256 con autenticazione) e deduplicato: ogni giorno si aggiunge solo ciò che è cambiato.

## Attivazione

La configurazione la fa l'installazione (`setup-windows.bat`, `start.sh` o `./src/scripts/sync-env.sh`) la prima volta:
- ti chiede **dove salvare i backup** (meglio un disco diverso da quello dei dati, per esempio `D:\Backup`; scrivi `no` per non attivarli);
- crea l'archivio in `<cartella>/restic` e imposta `RESTIC_REPO_DIR` e `RESTIC_PASSWORD_FILE` nel `.env`;
- genera la passphrase in `~/.restic-pass` (permessi 600) e te la **mostra una volta sola**.

**Copia la passphrase fuori dal server** (password manager nel cloud, foglio stampato): senza, i backup non si aprono più.
Se la perdi, la trovi con `cat ~/.restic-pass`, ma solo finché il server funziona.

Poi, nel pannello, sezione Backup: **Prepara l'archivio** (una volta sola) e **Esegui backup ora**.

Per cambiare cartella dopo: `./src/scripts/sync-env.sh --percorsi` (l'archivio già creato non viene spostato e la passphrase resta la stessa).
A mano si può fare anche dal `.env` (`RESTIC_REPO_DIR`, `RESTIC_PASSWORD_FILE`, percorsi assoluti), poi `docker compose up -d --build backend`.

Dopo, parte da solo ogni giorno all'ora di `RESTIC_SCHEDULE` (03:30): backup, poi pulizia delle copie vecchie (7 giornaliere, 4 settimanali, 6 mensili).

## Cosa viene salvato

`vaultwarden`, `immich/upload` (foto e i dump automatici del database), `pihole`, `jellyfin/config`, e la cartella foto esterna se hai impostato `PHOTOS_DIR`. Miniature e video convertiti sono esclusi (si rigenerano).
Prima del backup Vaultwarden viene copiato in modo coerente; se non riesce, il backup parte comunque e te lo dice.

**Verifica una volta** in Immich (Amministrazione, Impostazioni, *Backup del database*) che i dump automatici siano attivi: il database non viene copiato mentre è in uso.

## Ripristino

```bash
docker compose --profile tools run --rm restic -r /repo snapshots
docker compose --profile tools run --rm restic -r /repo restore latest --target /restore
```
I file ripristinati compaiono in `$DATA_DIR/restore`: copiali al loro posto a servizi fermi.
Prova un ripristino una volta, quando va tutto bene, non il giorno in cui serve.

## Limiti

- L'archivio è in locale: se il disco si rompe o la casa va a fuoco, va perso insieme ai dati. Una copia fuori casa (disco a rotazione, o un servizio remoto con `restic copy`) non è ancora collegata al pannello.
- Il pulsante *Controlla integrità* verifica la struttura dell'archivio, non legge tutti i dati.
