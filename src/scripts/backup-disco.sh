#!/usr/bin/env bash
# Mette l'archivio di backup Restic su un disco esterno collegato al server, da collegare solo quando serve.
#
#   ./src/scripts/backup-disco.sh                       -> mostra i dischi montati e chiede quale usare
#   ./src/scripts/backup-disco.sh /media/utente/BACKUP  -> usa quel disco (deve essere gia' collegato e montato)
#   ./src/scripts/backup-disco.sh --stato               -> mostra la configurazione attuale
#   ./src/scripts/backup-disco.sh --locale              -> torna all'archivio in data/backups (quello sul disco non si tocca)
#
# Cosa fa: controlla che sia un disco diverso da quello dei dati e che si possa scrivere, crea sul disco la cartella
# dell'archivio e il file marcatore .homeserver-backup (senza il quale il pannello rifiuta di fare backup: cosi' un disco
# scollegato non fa mai scrivere l'archivio sul disco di sistema), scrive le variabili nel .env e riavvia il backend.
# Va lanciato col tuo utente, senza sudo. Non cancella e non sposta nulla; la copia dell'archivio locale e' facoltativa.
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*" >&2; }

[ "$(id -u)" != 0 ] || die "Non lanciarlo con sudo: i file sul disco diventerebbero di root e il backup non potrebbe scriverli."
[ "$(uname -s)" = Linux ] || die "Funziona solo su Linux (serve il montaggio con propagazione, vedi docs/restic.md)."
[ -f .env ] || die "Manca il .env: lancia prima ./src/scripts/start.sh (o sync-env.sh)."

# stesse due funzioni di sync-env.sh
get() { { grep -E "^$1=" .env || true; } | head -n1 | cut -d= -f2-; }
set_kv() {
  local key="$1" value="$2" escaped
  escaped="${value//\\/\\\\}"; escaped="${escaped//&/\\&}"; escaped="${escaped//|/\\|}"
  if grep -q "^$key=" .env; then sed -i "s|^$key=.*|$key=$escaped|" .env; else printf '%s=%s\n' "$key" "$value" >> .env; fi
}

data_dir="$(get DATA_DIR)"
[ -n "$data_dir" ] && [ -d "$data_dir" ] || die "DATA_DIR non e' valido nel .env: lancia ./src/scripts/sync-env.sh."
INTERACTIVE=0; [ -t 0 ] && INTERACTIVE=1

restart_backend() {
  if docker compose up -d backend; then
    note "Backend riavviato con la nuova configurazione."
  else
    note "Non sono riuscito a riavviare il backend: lancia a mano 'docker compose up -d backend'."
    note "Se l'errore parla di 'not a shared or slave mount': sudo mount --make-rshared /   (vedi docs/restic.md)"
    exit 1
  fi
}

case "${1:-}" in
  --stato)
    disk="$(get BACKUP_DISK_DIR)"
    echo "Archivio:        $(get RESTIC_REPO_DIR)"
    if [ -z "$disk" ]; then echo "Disco esterno:   non configurato (archivio locale)"; exit 0; fi
    echo "Disco esterno:   $disk"
    echo "Cartella madre:  $(get BACKUP_MOUNT_PARENT)"
    if mountpoint -q "$disk" 2>/dev/null && [ -f "$disk/.homeserver-backup" ]; then echo "Stato:           collegato"; else echo "Stato:           NON collegato (o senza marcatore)"; fi
    exit 0 ;;
  --locale)
    set_kv RESTIC_REPO_DIR "$data_dir/backups/restic"
    set_kv BACKUP_DISK_DIR ""
    set_kv BACKUP_MOUNT_PARENT ""
    mkdir -p "$data_dir/backups/restic"
    echo "Archivio locale: $data_dir/backups/restic (sul disco esterno non e' stato toccato nulla)."
    restart_backend
    exit 0 ;;
  -*) die "Opzione sconosciuta: $1 (--stato, --locale, oppure il percorso del disco)." ;;
esac

# ---------------------------------------------------------------- quale disco
disk="${1:-}"
if [ -z "$disk" ]; then
  [ "$INTERACTIVE" = 1 ] || die "Indica il percorso del disco: ./src/scripts/backup-disco.sh /media/utente/BACKUP"
  command -v findmnt >/dev/null || die "findmnt non e' installato: indica a mano il percorso del disco."
  mapfile -t cands < <(findmnt -rno TARGET,FSTYPE,SIZE | awk '$1 ~ /^\/(media|mnt|run\/media)\// {print $1 "  (" $2 ", " $3 ")"}')
  [ "${#cands[@]}" -gt 0 ] || die "Non vedo nessun disco montato in /media, /mnt o /run/media: collegalo e, se non si monta da solo, montalo (es. sudo mount /dev/sdb1 /mnt/backup)."
  echo "Dischi montati:"
  for i in "${!cands[@]}"; do printf '  %d) %s\n' "$((i + 1))" "${cands[$i]}"; done
  printf 'Quale uso per i backup? [numero] ' >&2
  read -r n || n=""
  case "$n" in ''|*[!0-9]*) die "Scelta non valida." ;; esac
  [ "$n" -ge 1 ] && [ "$n" -le "${#cands[@]}" ] || die "Scelta non valida."
  disk="${cands[$((n - 1))]%%  (*}"
fi

arg="$disk"
disk="$(realpath -- "$arg" 2>/dev/null)" || die "Il percorso non esiste: $arg"
[ "$disk" != "/" ] || die "Percorso non valido."

# ---------------------------------------------------------------- controlli sul disco
mountpoint -q "$disk" || die "$disk non e' un punto di montaggio: il disco e' collegato e montato? (Una semplice cartella sul disco di sistema non protegge da nulla.)"
dev_data="$(stat -c %d -- "$data_dir")"
dev_disk="$(stat -c %d -- "$disk")"
[ "$dev_data" != "$dev_disk" ] || die "$disk e' sullo stesso disco dei dati ($data_dir): non proteggerebbe da un guasto del disco."
test_file="$disk/.hs-prova-scrittura-$$"
if ! { : > "$test_file"; } 2>/dev/null; then
  die "Non riesco a scrivere in $disk col tuo utente. Per un disco ext4 nuovo: sudo chown $(id -un): '$disk'"
fi
rm -f -- "$test_file"
fstype="$(findmnt -no FSTYPE -- "$disk" 2>/dev/null || echo ?)"
case "$fstype" in
  ext2|ext3|ext4|xfs|btrfs) ;;
  *) note "ATTENZIONE: il disco e' formattato come '$fstype'. Per un archivio Restic e' consigliato ext4 (permessi, file grandi, robustezza); con $fstype funziona ma non lo garantisco." ;;
esac
parent="$(dirname -- "$disk")"
[ "$parent" != "/" ] || die "Il disco e' montato direttamente in /: montalo in una sottocartella (es. /mnt/backup) e rilancia."
[ -d "$parent" ] || die "$parent non esiste."
echo "Disco:           $disk ($fstype), liberi $(df -h --output=avail -- "$disk" | tail -n1 | tr -d ' ')"
echo "Cartella madre:  $parent (il backend la monta in sola lettura per accorgersi del disco)"

# ---------------------------------------------------------------- archivio e marcatore
repo="$disk/homeserver-restic"
mkdir -p -- "$repo"
printf 'Disco di backup di homeserver (non cancellare: senza questo file il pannello rifiuta di scrivere qui).\n' > "$disk/.homeserver-backup"

local_repo="$data_dir/backups/restic"
if [ -f "$repo/config" ]; then
  echo "Sul disco c'e' gia' un archivio Restic: lo riuso."
elif [ -f "$local_repo/config" ]; then
  ans="${HS_COPIA_ARCHIVIO:-}"
  if [ -z "$ans" ] && [ "$INTERACTIVE" = 1 ]; then
    printf "Esiste un archivio locale (%s). Lo copio sul disco? [S/n] " "$local_repo" >&2
    read -r ans || ans=n
    case "$ans" in [nN]*) ans=0 ;; *) ans=1 ;; esac
  fi
  if [ "${ans:-0}" = 1 ]; then
    echo "Copio l'archivio locale sul disco (puo' volerci un po')..."
    if command -v rsync >/dev/null; then rsync -a -- "$local_repo/" "$repo/"; else cp -a -- "$local_repo/." "$repo/"; fi
    [ -f "$repo/config" ] || die "La copia non e' riuscita: manca $repo/config."
    echo "Copiato. L'archivio locale resta dov'e': cancellalo tu quando avrai controllato la copia (pannello, Backup, Controlla integrita')."
  else
    echo "Non copio l'archivio locale: dal pannello, 'Prepara l'archivio' ne crea uno nuovo sul disco."
  fi
fi

chmod 700 -- "$repo"   # dopo la copia: rsync -a riporta i permessi della cartella di origine

# ---------------------------------------------------------------- .env e riavvio
set_kv RESTIC_REPO_DIR "$repo"
set_kv BACKUP_DISK_DIR "$disk"
set_kv BACKUP_MOUNT_PARENT "$parent"
sed -i '/^RESTIC_SCHEDULE=/d' .env
echo "Scritto nel .env: RESTIC_REPO_DIR, BACKUP_DISK_DIR, BACKUP_MOUNT_PARENT."
restart_backend

cat <<MSG

Fatto. Da ora il backup parte solo quando l'admin lo avvia dal pannello (sezione Backup), col disco collegato.
 - Se l'archivio e' nuovo: premi 'Prepara l'archivio' (una volta).
 - A backup finito, scollega il disco in modo sicuro (Espelli dal sistema) e tienilo spento o altrove.
 - Un disco collegato di continuo non protegge da un ransomware o da una scarica sul server: collegalo solo per il backup.
MSG
