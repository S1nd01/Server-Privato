#!/usr/bin/env bash
# Backup di Vaultwarden: database SQLite (copia consistente) + attachments, sends, chiavi RSA.
# Uso: BACKUP_DIR=/percorso ./scripts/backup-vaultwarden.sh   (default: ./backups, ultime 14 copie)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${KEEP:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
SRC="${DATA_DIR:?DATA_DIR non impostato}/vaultwarden"
mkdir -p "$BACKUP_DIR"

# 1) Copia consistente del DB mentre il server gira (sottocomando `backup` di Vaultwarden)
if docker exec vaultwarden /vaultwarden backup >/dev/null 2>&1; then
  echo "DB: backup online ok"
  RESTART=0
else
  # 2) Fallback: ferma il container per qualche secondo e copia i file
  echo "DB: sottocomando backup non disponibile, fermo il container un attimo"
  docker stop vaultwarden >/dev/null
  RESTART=1
fi

tar -czf "$BACKUP_DIR/vaultwarden-$STAMP.tar.gz" \
  --exclude='icon_cache' --exclude='tmp' -C "$SRC" .

[ "$RESTART" = 1 ] && docker start vaultwarden >/dev/null

# Rotazione
ls -1t "$BACKUP_DIR"/vaultwarden-*.tar.gz | tail -n +"$((KEEP + 1))" | xargs -r rm --
echo "Creato: $BACKUP_DIR/vaultwarden-$STAMP.tar.gz"
echo "Ricorda: il backup contiene il vault cifrato e le chiavi, ma copialo anche FUORI dal server (altro disco/PC)."
