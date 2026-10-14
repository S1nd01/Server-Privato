#!/usr/bin/env bash
# Prepara il progetto. Si puo' rilanciare quante volte vuoi: non cancella e non sposta nulla.
#  - crea il .env se manca (non serve modificarlo a mano)
#  - la prima volta chiede dove tenere i dati dei servizi e dove scaricare i giochi Steam
#    (per cambiarli piu' avanti: ./src/scripts/sync-env.sh --percorsi)
#  - aggiunge al .env le variabili nuove di .env.example SENZA toccare quelle che hai gia'
#  - genera la password di Pi-hole se manca
#  - crea le cartelle dei dati col tuo utente (altrimenti Docker le crea come root e Jellyfin non parte),
#    comprese quelle dei giochi Steam
#  - la prima volta imposta i backup: cartella, passphrase (generate e mostrate UNA volta) e, se vuoi,
#    il backup notturno di Vaultwarden. Senza domande: HS_BACKUP_DIR=/percorso (o =no), HS_VW_CRON=1
# Senza domande (script, test): HS_DATA_DIR=/percorso HS_STEAM_GAMES_DIR=/percorso ./src/scripts/sync-env.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }

ASK_PATHS=0
case "${1:-}" in
  "") ;;
  --percorsi) ASK_PATHS=1 ;;
  *) die "Opzione sconosciuta: $1 (l'unica e' --percorsi, per cambiare le cartelle)." ;;
esac
INTERACTIVE=0
if [ -t 0 ]; then INTERACTIVE=1; fi

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
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
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

# ---------------------------------------------------------------- percorsi
# Stampa il percorso pulito (assoluto, senza caratteri strani), oppure il motivo su stderr e ritorna 1.
# $1 = quello che ha scritto l'utente, $2 = data (dati dei servizi) | steam (giochi)
norm_path() {
  local p="$1" kind="$2" d rest
  p="${p#"${p%%[![:space:]]*}"}"; p="${p%"${p##*[![:space:]]}"}"   # niente spazi ai lati
  p="${p#\"}"; p="${p%\"}"                                         # virgolette se ha trascinato la cartella
  case "$p" in "~") p="$HOME" ;; "~/"*) p="$HOME/${p#\~/}" ;; esac
  if [[ "$p" =~ ^([A-Za-z]):[\\/](.*)$ ]]; then                    # D:\Giochi -> /mnt/d/Giochi (WSL)
    d="${BASH_REMATCH[1],,}"; rest="${BASH_REMATCH[2]//\\//}"
    p="/mnt/$d/$rest"
  fi
  while [ "${#p}" -gt 1 ] && [ "${p%/}" != "$p" ]; do p="${p%/}"; done
  case "$p" in /*) ;; *) echo "Il percorso deve iniziare con / oppure con una lettera di disco, per esempio D:\\Giochi" >&2; return 1 ;; esac
  if [[ ! "$p" =~ ^/[A-Za-z0-9._/@+-]+$ ]]; then
    echo "Nel percorso usa solo lettere, numeri e . _ - + @ / (niente spazi, accenti o altri simboli: usa per esempio Giochi_Steam)." >&2; return 1
  fi
  case "/$p/" in *"/../"*) echo "Il percorso non puo' contenere \"..\"." >&2; return 1 ;; esac
  case "$p" in /bin|/boot|/dev|/etc|/home|/lib|/proc|/root|/run|/sbin|/sys|/usr|/var)
    echo "$p e' una cartella di sistema: scegline una tua." >&2; return 1 ;; esac
  if [ "$kind" = data ] && [[ "$p" =~ ^/mnt/[a-z](/|$) ]]; then
    echo "I dati dei servizi (database) non funzionano su un disco Windows (NTFS/exFAT): scegli una cartella nel disco di Linux." >&2; return 1
  fi
  if [ "$kind" != data ] && [[ "$p" =~ ^/mnt/[a-z]$ ]]; then
    echo "Indica una cartella dentro il disco, per esempio D:\\Giochi, non il disco intero." >&2; return 1
  fi
  printf '%s\n' "$p"
}

try_mkdir() {
  if mkdir -p "$1" 2>/dev/null && [ -w "$1" ]; then return 0; fi
  echo "Non riesco a creare o scrivere in $1 (il disco e' collegato? hai i permessi?)." >&2
  return 1
}

# choose_path CHIAVE "domanda" predefinito data|steam
choose_path() {
  local key="$1" question="$2" def="$3" kind="$4" envname="HS_$1" ans eof p=""
  if [ -n "${!envname:-}" ]; then
    p="$(norm_path "${!envname}" "$kind")" && try_mkdir "$p" || die "$envname non e' utilizzabile."
  elif [ "$INTERACTIVE" = 1 ]; then
    while true; do
      printf '\n%s\n  Invio = %s\n> ' "$question" "$def" >&2
      eof=0; read -r ans || eof=1
      if [ -z "${ans//[[:space:]]/}" ]; then ans="$def"; fi
      if p="$(norm_path "$ans" "$kind")" && try_mkdir "$p"; then break; fi
      [ "$eof" = 0 ] || die "Input terminato senza un percorso valido."
    done
  else
    p="$(norm_path "$def" "$kind")" && try_mkdir "$p" || die "Il percorso predefinito $def non e' utilizzabile: rilancia da un terminale per sceglierne un altro."
    echo "Nessun terminale per le domande: uso il percorso predefinito $p" >&2
  fi
  set_kv "$key" "$p"
  echo "$key = $p"
}

needs_path() {
  local v; v="$(get "$1")"
  [ "$ASK_PATHS" = 1 ] || [ -z "$v" ] || [[ "$v" == *CAMBIAMI* ]]
}
# un .env vecchio puo' avere ancora il segnaposto /home/CAMBIAMI: lo trasformo nella tua home
fix_placeholder() { local v="${1/\/home\/CAMBIAMI/$HOME}"; [[ "$v" == *CAMBIAMI* ]] && v=""; printf '%s' "$v"; }

old_data="$(get DATA_DIR)"
def_data="$(fix_placeholder "$old_data")"; def_data="${def_data:-$HOME/homeserver-data}"
if needs_path DATA_DIR; then
  choose_path DATA_DIR "Dove vuoi tenere i dati dei servizi (database, impostazioni, foto caricate)?
  Deve essere nel disco di Linux, non un disco Windows come D:\\." "$def_data" data
fi
data_dir="$(get DATA_DIR)"

def_steam="$(fix_placeholder "$(get STEAM_GAMES_DIR)")"; def_steam="${def_steam:-$data_dir/steam-games}"
if needs_path STEAM_GAMES_DIR; then
  choose_path STEAM_GAMES_DIR "Dove vuoi scaricare i giochi Steam?
  Puoi scegliere anche un disco di Windows: D:\\Giochi diventa /mnt/d/Giochi." "$def_steam" steam
fi
steam_dir="$(get STEAM_GAMES_DIR)"

if [ "$ASK_PATHS" = 1 ] && [ -n "$old_data" ] && [ "$old_data" != "$data_dir" ] && [ -d "$old_data" ]; then
  echo "NOTA: i dati gia' salvati restano in $old_data. Per usarli nella nuova cartella spostali a mano (con i servizi fermi)." >&2
fi

# ---------------------------------------------------------------- cartelle
SUBDIRS=(jellyfin/config jellyfin/cache media panel pihole tailscale restore)   # tienile uguali a src/backend/app/stats.py

make_dirs() {
  local d
  mkdir -p "$data_dir" "$steam_dir" 2>/dev/null || return 1
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
    die "Non riesco a creare le cartelle in $data_dir e $steam_dir. Per sceglierne altre: ./src/scripts/sync-env.sh --percorsi"
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
backup_base=""

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

# imposta backup_base (cartella) oppure lo lascia vuoto se l'utente rinuncia ("no")
ask_backup_base() {
  local def="$1" ans eof p envv="${HS_BACKUP_DIR:-}"
  if [ -n "$envv" ]; then
    case "${envv,,}" in no|none|0) return 0 ;; esac
    p="$(norm_path "$envv" backup)" && try_mkdir "$p" || die "HS_BACKUP_DIR non e' utilizzabile."
    backup_base="$p"
  elif [ "$INTERACTIVE" = 1 ]; then
    while true; do
      printf '\nDove vuoi salvare i backup (Restic e Vaultwarden)?\n  Meglio su un disco diverso da quello dei dati, per esempio un SSD esterno (D:\\Backup).\n  Invio = %s   |   scrivi "no" per non attivarli ora\n> ' "$def" >&2
      eof=0; read -r ans || eof=1
      ans="${ans#"${ans%%[![:space:]]*}"}"; ans="${ans%"${ans##*[![:space:]]}"}"
      if [ "${ans,,}" = no ]; then return 0; fi
      if [ -z "$ans" ]; then ans="$def"; fi
      if p="$(norm_path "$ans" backup)" && try_mkdir "$p"; then backup_base="$p"; return 0; fi
      [ "$eof" = 0 ] || die "Input terminato senza un percorso valido."
    done
  else
    p="$(norm_path "$def" backup)" && try_mkdir "$p" || die "Il percorso predefinito $def non e' utilizzabile: rilancia da un terminale per sceglierne un altro."
    backup_base="$p"
    echo "Nessun terminale per le domande: backup nel percorso predefinito $p" >&2
  fi
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
  local def="$HOME/homeserver-backups" cur ans="" do_cron=""
  cur="$(get RESTIC_REPO_DIR)"
  if [ "$ASK_PATHS" != 1 ] && [ -n "$cur" ] && [ -n "$(get RESTIC_PASSWORD_FILE)" ] && [ -n "$(get BACKUP_PASSPHRASE_FILE)" ]; then
    set_kv BACKUP_SETUP done      # backup gia' configurati a mano: li rispetto
    return 0
  fi
  if [ -n "$cur" ] && [ "$(basename "$cur")" = restic ]; then def="$(dirname "$cur")"; fi
  ask_backup_base "$def"
  if [ -z "$backup_base" ]; then
    set_kv BACKUP_SETUP skipped
    echo "Backup non attivati. Per attivarli piu' avanti: ./src/scripts/sync-env.sh --percorsi" >&2
    return 0
  fi
  try_mkdir "$backup_base/restic" && try_mkdir "$backup_base/vaultwarden" || die "Non riesco a creare le cartelle dei backup in $backup_base."
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
  if [ -z "$do_cron" ] && [ "$INTERACTIVE" = 1 ]; then
    printf '\nBackup automatico di Vaultwarden ogni notte alle 03:00? [S/n] ' >&2
    read -r ans || ans="n"
    case "$ans" in [nN]*) do_cron=0 ;; *) do_cron=1 ;; esac
  fi
  if [ "$do_cron" = 1 ]; then
    install_cron
  else
    echo "Backup automatico di Vaultwarden non attivato: a mano con ./src/scripts/backup-vaultwarden.sh (o HS_VW_CRON=1 per attivarlo)." >&2
  fi
}

if [ "$ASK_PATHS" = 1 ] || [ -z "$(get BACKUP_SETUP)" ]; then setup_backup; fi

echo "Cartelle pronte: dati in $data_dir, giochi Steam in $steam_dir"
echo "Variabili aggiunte al .env: ${added[*]:-nessuna}"
if [ -n "$(get RESTIC_REPO_DIR)" ]; then echo "Backup: Restic in $(get RESTIC_REPO_DIR), Vaultwarden in $(get BACKUP_DIR)"; fi
