#!/usr/bin/env bash
# Prepara il progetto. Si puo' rilanciare quante volte vuoi: non cancella e non sposta nulla.
#  - crea il .env se manca (non serve modificarlo a mano)
#  - salva tutti i dati nella directory data/ del progetto
#  - aggiunge le variabili nuove al .env e riallinea i percorsi gestiti dallo script
#  - genera la password di Pi-hole se manca
#  - crea le cartelle dei dati col tuo utente (altrimenti Docker le crea come root e Jellyfin non parte),
#    comprese quelle dei giochi Steam
#  - la prima volta imposta i backup nella directory data/backups e genera le passphrase
#    (mostrate UNA volta); il backup notturno di Vaultwarden e' facoltativo.
# --percorsi e' accettato per compatibilita': i percorsi restano sempre dentro data/.
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }

ASK_PATHS=0
case "${1:-}" in
  "") ;;
  --percorsi) ASK_PATHS=1 ;;
  *) die "Opzione sconosciuta: $1 (l'unica e' --percorsi, per riallineare la configurazione)." ;;
esac
INTERACTIVE=0
if [ -t 0 ]; then INTERACTIVE=1; fi
project_dir="$(pwd -P)"
data_dir="$project_dir/data"
steam_dir="$data_dir/steam-games"
backup_base="$data_dir/backups"

# ---------------------------------------------------------------- .env
[ -f .env.example ] || die "Manca .env.example: scompatta di nuovo lo zip del progetto."
sed -i 's/\r$//' .env.example   # se arriva da Windows ha i ritorni a capo di Windows
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^PUID=.*/PUID=$(id -u)/; s/^PGID=.*/PGID=$(id -g)/" .env
  sed -i "s/^IMMICH_DB_PASSWORD=.*/IMMICH_DB_PASSWORD=$(openssl rand -hex 8)/" .env
  echo "Creato il file .env."
fi
sed -i 's/\r$//' .env
chmod 600 .env

get() { { grep -E "^$1=" .env || true; } | head -n1 | cut -d= -f2-; }
set_kv() {
  local key="$1" value="$2" escaped
  escaped="${value//\\/\\\\}"; escaped="${escaped//&/\\&}"; escaped="${escaped//|/\\|}"
  if grep -q "^$key=" .env; then sed -i "s|^$key=.*|$key=$escaped|" .env; else printf '%s=%s\n' "$key" "$value" >> .env; fi
}

added=()
while IFS= read -r line; do
  case "$line" in '' | \#*) continue ;; esac
  key="${line%%=*}"
  [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || continue
  if ! grep -q "^${key}=" .env; then
    printf '%s\n' "$line" >> .env
    added+=("$key")
  fi
done < .env.example

if ! grep -qE '^PIHOLE_PASSWORD=.+' .env; then
  pw="$(openssl rand -hex 12)"
  sed -i "s/^PIHOLE_PASSWORD=.*/PIHOLE_PASSWORD=$pw/" .env
  echo "Password di Pi-hole generata (la trovi nel .env): $pw"
fi

# ---------------------------------------------------------------- percorsi fissi dentro data/
old_data="$(get DATA_DIR)"
old_steam="$(get STEAM_GAMES_DIR)"
old_photos="$(get PHOTOS_DIR)"
old_media="$(get MEDIA_DIR)"
old_backup="$(get BACKUP_DIR)"
old_restic="$(get RESTIC_REPO_DIR)"
set_kv DATA_DIR "$data_dir"
set_kv STEAM_GAMES_DIR "$steam_dir"
set_kv PHOTOS_DIR "$data_dir/photos"
set_kv MEDIA_DIR "$data_dir/media"
set_kv BACKUP_DIR "$backup_base/vaultwarden"
set_kv RESTIC_REPO_DIR "$backup_base/restic"

warn_old_path() {
  local label="$1" path="$2" expected="$3"
  if [ -n "$path" ] && [ "$path" != "$expected" ] && [ -d "$path" ]; then
    echo "NOTA: $label esistenti restano in $path. Per riutilizzarli, spostali in $expected a servizi fermi." >&2
  fi
}
warn_old_path "I dati dei servizi" "$old_data" "$data_dir"
warn_old_path "I giochi Steam" "$old_steam" "$steam_dir"
warn_old_path "Le foto" "$old_photos" "$data_dir/photos"
warn_old_path "I media Jellyfin" "$old_media" "$data_dir/media"
warn_old_path "I backup Vaultwarden" "$old_backup" "$backup_base/vaultwarden"
warn_old_path "L'archivio Restic" "$old_restic" "$backup_base/restic"

# ---------------------------------------------------------------- cartelle
SUBDIRS=(jellyfin/config jellyfin/cache media photos panel pihole tailscale restore steamcmd steam-games immich/upload immich/postgres immich/model-cache vaultwarden caddy/data caddy/config backups/restic backups/vaultwarden)   # tienile uguali a src/backend/app/stats.py

make_dirs() {
  local d
  mkdir -p "$data_dir" 2>/dev/null || return 1
  for d in "${SUBDIRS[@]}"; do mkdir -p "$data_dir/$d" 2>/dev/null || return 1; done
}
mine() { [ "$(stat -c %u "$1")" = "$(id -u)" ]; }
# fix_flat = cartelle da prendere in carico (solo la cartella), fix_deep = anche col contenuto
find_problems() {
  fix_flat=(); fix_deep=()
  if [ -d "$data_dir" ] && [ ! -w "$data_dir" ]; then fix_flat+=("$data_dir"); fi
  # Jellyfin gira col tuo utente (PUID): la sua cartella deve essere tua
  if [ -e "$data_dir/jellyfin" ] && ! mine "$data_dir/jellyfin"; then fix_deep+=("$data_dir/jellyfin"); fi
}

made=1; make_dirs || made=0
find_problems
if [ "$made" = 0 ] || [ "${#fix_flat[@]}" -gt 0 ] || [ "${#fix_deep[@]}" -gt 0 ]; then
  if [ "${#fix_flat[@]}" -eq 0 ] && [ "${#fix_deep[@]}" -eq 0 ]; then
    die "Non riesco a creare le cartelle in $data_dir: controlla i permessi del progetto."
  fi
  uid="$(id -u):$(id -g)"
  echo "ATTENZIONE: queste cartelle non sono tue (di solito le ha create Docker come root) e Jellyfin non partirebbe:" >&2
  printf '  %s\n' "${fix_flat[@]}" "${fix_deep[@]}" >&2
  cmds=()
  if [ "${#fix_flat[@]}" -gt 0 ]; then cmds+=("sudo chown $uid ${fix_flat[*]}"); fi
  if [ "${#fix_deep[@]}" -gt 0 ]; then cmds+=("sudo chown -R $uid ${fix_deep[*]}"); fi
  if [ "$INTERACTIVE" != 1 ]; then
    printf 'Sistemale con:\n  %s\npoi rilancia ./src/scripts/sync-env.sh\n' "${cmds[@]}" >&2
    exit 1
  fi
  printf "Le sistemo adesso? Ti chiedo la password di Ubuntu. [S/n] " >&2
  ans=""; read -r ans || ans="n"
  case "$ans" in [nN]*) printf 'Va bene. Quando vuoi:\n  %s\npoi rilancia ./src/scripts/sync-env.sh\n' "${cmds[@]}" >&2; exit 1 ;; esac
  for c in "${cmds[@]}"; do $c || die "Comando non riuscito: $c"; done
  make_dirs || die "Le cartelle non si creano ancora: controlla i permessi di $data_dir."
fi

# ---------------------------------------------------------------- backup (Restic e Vaultwarden)
# Passphrase: file con permessi 600 nella tua home, come descritto in docs/restic.md e docs/vaultwarden.md.
RESTIC_PASS_FILE="$HOME/.restic-pass"
VW_PASS_FILE="$HOME/.vw-backup-pass"
CRON_MARK="# homeserver-vaultwarden-backup"
new_secrets=()

make_pass() {   # $1 = file, $2 = nome (per il messaggio). Non sovrascrive mai una passphrase che esiste gia'.
  local f="$1"
  if [ -e "$f" ]; then
    [ -f "$f" ] && [ "$(wc -c < "$f")" -ge 20 ] || die "$f esiste ma non e' una passphrase valida (minimo 20 caratteri): sistemalo o cancellalo e rilancia."
    chmod 600 "$f"
    return 0
  fi
  ( umask 077; openssl rand -base64 32 > "$f" )
  chmod 600 "$f"
  new_secrets+=("$2|$f")
}

# backup automatico di Vaultwarden ogni notte alle 03:00 (crontab dell'utente, senza duplicati)
install_cron() {
  local line cur
  if ! command -v crontab >/dev/null 2>&1; then
    echo "NOTA: 'crontab' non e' installato: il backup di Vaultwarden resta manuale (./src/scripts/backup-vaultwarden.sh)." >&2
    return 0
  fi
  line="0 3 * * * cd \"$PWD\" && ./src/scripts/backup-vaultwarden.sh >> \"$(get BACKUP_DIR)/backup.log\" 2>&1 $CRON_MARK"
  cur="$( { crontab -l 2>/dev/null || true; } | { grep -vF "$CRON_MARK" || true; } )"
  printf '%s\n%s\n' "$cur" "$line" | sed '/^$/d' | crontab -
  echo "Backup automatico di Vaultwarden: ogni notte alle 03:00 (crontab)."
}

setup_backup() {
  local ans="" do_cron="${HS_VW_CRON:-}" first_setup=0
  [ "$(get BACKUP_SETUP)" = done ] || first_setup=1
  mkdir -p "$backup_base/restic" "$backup_base/vaultwarden" || die "Non riesco a creare le cartelle dei backup in $backup_base."
  set_kv RESTIC_REPO_DIR "$backup_base/restic"
  set_kv BACKUP_DIR "$backup_base/vaultwarden"
  if [ -z "$(get RESTIC_PASSWORD_FILE)" ]; then make_pass "$RESTIC_PASS_FILE" Restic; set_kv RESTIC_PASSWORD_FILE "$RESTIC_PASS_FILE"; fi
  if [ -z "$(get BACKUP_PASSPHRASE_FILE)" ]; then make_pass "$VW_PASS_FILE" Vaultwarden; set_kv BACKUP_PASSPHRASE_FILE "$VW_PASS_FILE"; fi
  set_kv BACKUP_SETUP done
  echo "RESTIC_REPO_DIR = $backup_base/restic"
  echo "BACKUP_DIR = $backup_base/vaultwarden"

  if [ "${#new_secrets[@]}" -gt 0 ]; then
    echo
    echo "================================================================================"
    echo " PASSPHRASE DEI BACKUP: salvale ORA FUORI da questo server"
    echo " (password manager nel cloud, NON il Vaultwarden di questo server; oppure stampale)."
    echo " Senza queste frasi i backup non si possono piu' aprire."
    echo
    local e
    for e in "${new_secrets[@]}"; do
      printf '   %-12s %s\n' "${e%%|*}:" "$(cat "${e#*|}")"
    done
    echo
    echo " Sono salvate anche in: $(printf '%s ' "${new_secrets[@]#*|}")"
    echo "================================================================================"
    if [ "$INTERACTIVE" = 1 ]; then
      printf 'Premi Invio quando le hai salvate: ' >&2
      read -r ans || true
    fi
  fi

  do_cron="${HS_VW_CRON:-}"
  if [ -z "$do_cron" ] && [ "$INTERACTIVE" = 1 ] && { [ "$ASK_PATHS" = 1 ] || [ "$first_setup" = 1 ]; }; then
    printf '\nBackup automatico di Vaultwarden ogni notte alle 03:00? [S/n] ' >&2
    read -r ans || ans="n"
    case "$ans" in [nN]*) do_cron=0 ;; *) do_cron=1 ;; esac
  fi
  if [ "$do_cron" = 1 ]; then
    install_cron
  else
    echo "Backup automatico di Vaultwarden non attivato: a mano con ./src/scripts/backup-vaultwarden.sh (HS_VW_CRON=1 per attivarlo)." >&2
  fi
}

if [ "$ASK_PATHS" = 1 ] || [ "$(get BACKUP_SETUP)" != done ]; then setup_backup; fi

echo "Cartelle pronte: tutti i dati sono in $data_dir"
echo "Variabili aggiunte al .env: ${added[*]:-nessuna}"
if [ -n "$(get RESTIC_REPO_DIR)" ]; then echo "Backup: Restic in $(get RESTIC_REPO_DIR), Vaultwarden in $(get BACKUP_DIR)"; fi
