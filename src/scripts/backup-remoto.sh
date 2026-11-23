#!/usr/bin/env bash
# Copia l'archivio Restic fuori sede con rclone (docs/backup-remoto.md).
#
#   ./src/scripts/backup-remoto.sh --config      crea o modifica il "remote" di rclone (cloud, SFTP, altro disco...), una volta
#   ./src/scripts/backup-remoto.sh --prova       mostra cosa copierebbe e cosa cancellerebbe sul remoto, senza fare nulla
#   ./src/scripts/backup-remoto.sh               copia (sync) l'archivio sul remoto
#   ./src/scripts/backup-remoto.sh --stato       data dell'ultima copia riuscita
#
# L'archivio e' gia' cifrato da Restic: sul remoto finiscono solo file cifrati, ma senza la passphrase (RESTIC_PASSWORD_FILE) non
# si ripristina nulla: tienila anche fuori dal server. Lo script NON lancia il backup Restic (lo fa il pannello): copia quello che c'e'.
# Si lancia a mano o da cron/systemd sul server, col tuo utente (senza sudo); non e' una funzione del pannello.
#
# Protezioni contro il caso peggiore (copiare "il nulla" sopra una copia buona):
#   - rifiuta se l'archivio locale non ha config, chiavi e almeno un'istantanea, o se il disco di backup non e' collegato;
#   - rifiuta se un backup Restic e' in corso;
#   - `sync` cancella sul remoto cio' che non c'e' piu' in locale (e' giusto: Restic fa pulizia), ma mai piu' di
#     BACKUP_REMOTO_MAX_DELETE file per volta (2000 di serie); oltre, si ferma;
#   - la cartella dei lock di Restic non si copia.
set -euo pipefail
cd "$(dirname "$0")/../.."

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" != 0 ] || die "Non lanciarlo con sudo: i file di configurazione di rclone diventerebbero di root."
[ -f .env ] || die "Manca il .env: lancia prima ./src/scripts/start.sh (o sync-env.sh)."
command -v docker >/dev/null || die "docker non trovato."
get() { { grep -E "^$1=" .env || true; } | head -n1 | cut -d= -f2-; }

data_dir="$(get DATA_DIR)"; [ -n "$data_dir" ] || die "DATA_DIR e' vuoto nel .env: lancia prima ./src/scripts/sync-env.sh."
remote="$(get RCLONE_REMOTE)"
max_delete="$(get BACKUP_REMOTO_MAX_DELETE)"; max_delete="${max_delete:-2000}"
kuma="$(get BACKUP_REMOTO_KUMA_PUSH)"
disk="$(get BACKUP_DISK_DIR)"
state="$data_dir/panel/backup-remoto.json"
rc() { docker compose --profile tools run --rm -T rclone "$@"; }

case "${1:-}" in
  --config)
    mkdir -p "$data_dir/rclone"
    # col tuo utente (non root): cosi' rclone.conf resta tuo e lo puoi leggere e modificare
    exec docker compose --profile tools run --rm -u "$(id -u):$(id -g)" rclone config
    ;;
  --stato)
    if [ -f "$state" ]; then
      last="$(sed -n 's/.*"last_ok": *"\([^"]*\)".*/\1/p' "$state")"
      if [ -n "$last" ] && ts="$(date -d "$last" +%s 2>/dev/null)"; then
        echo "Ultima copia riuscita: $last ($(( ( $(date +%s) - ts ) / 86400 )) giorni fa)"
      else
        echo "Lo stato esiste ma non si legge: $state"
      fi
    else
      echo "Nessuna copia fuori sede finora."
    fi
    echo "Destinazione: ${remote:-(RCLONE_REMOTE non impostato nel .env)}"
    exit 0
    ;;
  --prova) dry=(--dry-run) ;;
  "") dry=() ;;
  *) die "Opzione sconosciuta: $1 (vedi l'intestazione dello script)" ;;
esac

[ -n "$remote" ] || die "RCLONE_REMOTE e' vuoto nel .env. Prima: ./src/scripts/backup-remoto.sh --config, poi scrivi nel .env  RCLONE_REMOTE=nome:cartella"
[[ "$remote" =~ ^[A-Za-z0-9_.-]+:[A-Za-z0-9_./@+-]*$ ]] || die "RCLONE_REMOTE non ha la forma nome:cartella (solo lettere, numeri e . _ - / @ +): $remote"
[[ "$max_delete" =~ ^[0-9]+$ ]] || die "BACKUP_REMOTO_MAX_DELETE deve essere un numero."
[ -f "$data_dir/rclone/rclone.conf" ] || die "Manca la configurazione di rclone ($data_dir/rclone/rclone.conf): lancia $0 --config"

# 1) disco di backup collegato? (stesso marcatore che usa il pannello)
if [ -n "$disk" ] && [ ! -f "$disk/.homeserver-backup" ]; then
  die "Il disco di backup non e' collegato (manca $disk/.homeserver-backup): collegalo e riprova."
fi
# 2) un backup Restic in corso?
if [ -n "$(docker ps -q --filter label=hs.restic --filter status=running)" ]; then
  die "C'e' un backup Restic in corso: riprova quando finisce."
fi
# 3) l'archivio locale sembra un archivio vero? (letto dal container: i file di Restic sono di root e non si leggono dall'utente)
n_files() { rc lsf --files-only "$@" 2>/dev/null | wc -l; }
rc lsf --files-only /repo 2>/dev/null | grep -qx config || die "L'archivio locale non ha il file config: non copio nulla (disco sbagliato o archivio non creato?)."
[ "$(n_files /repo/keys)" -ge 1 ] || die "L'archivio locale non ha chiavi: non copio nulla."
[ "$(n_files -R /repo/snapshots)" -ge 1 ] || die "L'archivio locale non ha nessuna istantanea: non copio nulla (prima fai un backup dal pannello)."

echo "Copio l'archivio Restic su $remote ${dry:+(prova: non cambia nulla)}"
set +e
rc sync /repo "$remote" "${dry[@]}" \
  --exclude '/locks/**' --max-delete "$max_delete" --transfers 4 --checkers 8 --retries 3 \
  --stats 30s --stats-one-line -v
code=$?
set -e
if [ "$code" -ne 0 ]; then
  die "rclone e' uscito con errore $code: la copia fuori sede NON e' aggiornata. Se il motivo e' il limite di cancellazioni (--max-delete), controlla con --prova e alza BACKUP_REMOTO_MAX_DELETE nel .env."
fi
if [ ${#dry[@]} -gt 0 ]; then echo "Prova finita: nulla e' stato copiato."; exit 0; fi

mkdir -p "$data_dir/panel"
printf '{"last_ok": "%s", "remote": "%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${remote%%:*}" > "$state.tmp" && mv -f "$state.tmp" "$state"
echo "Copia fuori sede completata."
if [ -n "$kuma" ]; then
  curl -fsS -m 10 -G --data-urlencode "status=up" --data-urlencode "msg=copia fuori sede ok" "$kuma" >/dev/null 2>&1 \
    || echo "Nota: non sono riuscito a segnalarlo a Uptime Kuma (BACKUP_REMOTO_KUMA_PUSH)." >&2
fi
