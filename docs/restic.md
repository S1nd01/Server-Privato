# Backup con Restic

Salva Vaultwarden, le foto di Immich, la configurazione di Pi-hole e di Jellyfin in un archivio **cifrato** (AES-256 con autenticazione) e deduplicato: ogni giorno si aggiunge solo ciò che è cambiato.

## Attivazione

1. Scegli dove tenere l'archivio, **meglio su un disco diverso** da quello dei dati (es. `/mnt/e/backup-restic`).
2. Crea la passphrase:
   ```bash
   umask 077; openssl rand -base64 32 > ~/.restic-pass
   ```
   **Copiala anche fuori dal server** (password manager, foglio stampato): senza, i backup non si aprono più.
3. Nel `.env`: `RESTIC_REPO_DIR=/mnt/e/backup-restic` e `RESTIC_PASSWORD_FILE=/home/<tu>/.restic-pass` (percorsi assoluti).
4. `docker compose up -d --build backend`
5. Pannello, sezione Backup: **Prepara l'archivio**, poi **Esegui backup ora**.

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
