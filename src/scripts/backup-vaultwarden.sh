#!/usr/bin/env bash
# Backup CIFRATO di Vaultwarden: database SQLite (copia consistente) + allegati, sends, chiavi RSA.
# Cifratura: AES-256 (GnuPG, modalita' simmetrica, con controllo di integrita'), passphrase da FILE.
#
# Preparazione (una volta):
#   umask 077; openssl rand -base64 32 > ~/.vw-backup-pass     # poi copiala anche FUORI dal server!
#   in .env:  BACKUP_PASSPHRASE_FILE=/home/<utente>/.vw-backup-pass
#
# Uso: ./src/scripts/backup-vaultwarden.sh (salva in data/backups/vaultwarden, ultime 14 copie)
# Senza passphrase lo script SI RIFIUTA di creare backup in chiaro (a meno di ALLOW_PLAINTEXT_BACKUP=1).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; [ -f .env ] && . ./.env; set +a
umask 077

KEEP="${KEEP:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DATA_DIR="$PWD/data"
BACKUP_DIR="$DATA_DIR/backups/vaultwarden"
SRC="$DATA_DIR/vaultwarden"
PASS_FILE="${BACKUP_PASSPHRASE_FILE:-}"

if [ -n "$PASS_FILE" ]; then
  [ -r "$PASS_FILE" ] || { echo "ERRORE: passphrase non leggibile: $PASS_FILE" >&2; exit 1; }
  case "$(stat -c %a "$PASS_FILE")" in
    400|600) ;;
    *) echo "ERRORE: $PASS_FILE deve avere permessi 600 (chmod 600 $PASS_FILE)" >&2; exit 1 ;;
  esac
  [ "$(wc -c < "$PASS_FILE")" -ge 20 ] || { echo "ERRORE: passphrase troppo corta (minimo 20 caratteri)" >&2; exit 1; }
  command -v gpg >/dev/null || { echo "ERRORE: gpg non installato (sudo apt install gnupg)" >&2; exit 1; }
elif [ "${ALLOW_PLAINTEXT_BACKUP:-0}" != 1 ]; then
  echo "ERRORE: BACKUP_PASSPHRASE_FILE non impostato: non creo backup in chiaro." >&2
  echo "        Vedi l'intestazione dello script (oppure ALLOW_PLAINTEXT_BACKUP=1, sconsigliato)." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# 1) Copia consistente del DB mentre il server gira (sottocomando `backup` di Vaultwarden)
RESTART=0
if docker exec vaultwarden /vaultwarden backup >/dev/null 2>&1; then
  echo "DB: backup online ok"
else
  # 2) Fallback: ferma il container per qualche secondo e copia i file
  echo "DB: sottocomando backup non disponibile, fermo il container un attimo"
  docker stop vaultwarden >/dev/null
  RESTART=1
fi
trap '[ "$RESTART" = 1 ] && docker start vaultwarden >/dev/null 2>&1 || true' EXIT

gpg_opts=(--batch --yes --quiet --pinentry-mode loopback --passphrase-file "$PASS_FILE")

if [ -n "$PASS_FILE" ]; then
  OUT="$BACKUP_DIR/vaultwarden-$STAMP.tar.gz.gpg"
  # tar -> gpg in pipe: il tar in chiaro non tocca mai il disco
  tar -czf - --exclude='icon_cache' --exclude='tmp' -C "$SRC" . \
    | gpg "${gpg_opts[@]}" --symmetric --cipher-algo AES256 \
          --s2k-mode 3 --s2k-digest-algo SHA512 --s2k-count 65011712 -o "$OUT"
  # verifica che si possa davvero decifrare e leggere
  gpg "${gpg_opts[@]}" --decrypt "$OUT" | tar -tz >/dev/null
  echo "Verifica decifratura: ok"
else
  OUT="$BACKUP_DIR/vaultwarden-$STAMP.tar.gz"
  tar -czf "$OUT" --exclude='icon_cache' --exclude='tmp' -C "$SRC" .
  echo "ATTENZIONE: backup NON cifrato"
fi

# Rotazione (le vecchie copie, cifrate o no)
ls -1t "$BACKUP_DIR"/vaultwarden-*.tar.gz* 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm --
echo "Creato: $OUT"
echo "Ricorda: copia il backup E la passphrase FUORI dal server (altro disco/PC). Senza passphrase il backup non si apre."
