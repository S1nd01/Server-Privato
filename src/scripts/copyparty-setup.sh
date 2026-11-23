#!/usr/bin/env bash
# Crea la configurazione e l'account di Copyparty, lo scambio file (docs/scambio-file.md).
#
#   ./src/scripts/copyparty-setup.sh                 crea la configurazione se manca e mostra la password UNA volta
#   ./src/scripts/copyparty-setup.sh --reimposta     sceglie una password nuova (stesso nome utente)
#   ./src/scripts/copyparty-setup.sh --stato         dice se la configurazione c'e' e per chi
#   ./src/scripts/copyparty-setup.sh --utente NOME   nome dell'account (di serie: il tuo utente di sistema)
#
# Va lanciato PRIMA di avviare Copyparty: senza data/copyparty/cfg/copyparty.conf il container non parte (e' voluto: la
# configurazione di serie di Copyparty lascia la cartella a chiunque). Il file ha permessi 600; la password e' in chiaro lì
# dentro (come quella di Pi-hole nel .env): chi legge quel file e' gia' proprietario del server.
# Va lanciato col tuo utente, senza sudo.
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" != 0 ] || die "Non lanciarlo con sudo: il file diventerebbe di root e il container (che gira col tuo utente) non potrebbe leggerlo."
[ -f .env ] || die "Manca il .env: lancia prima ./src/scripts/start.sh (o sync-env.sh)."
get() { { grep -E "^$1=" .env || true; } | head -n1 | cut -d= -f2-; }
data_dir="$(get DATA_DIR)"
[ -n "$data_dir" ] || die "DATA_DIR e' vuoto nel .env: lancia prima ./src/scripts/sync-env.sh."

mode=create; user="$(id -un)"
while [ $# -gt 0 ]; do
  case "$1" in
    --reimposta) mode=reset ;;
    --stato) mode=status ;;
    --utente) shift; user="${1:-}" ;;
    *) die "Opzione sconosciuta: $1 (vedi l'intestazione dello script)" ;;
  esac
  shift
done
# solo caratteri sicuri: il nome finisce in un file di configurazione
[[ "$user" =~ ^[A-Za-z][A-Za-z0-9_-]{0,31}$ ]] || die "Nome utente non valido: usa lettere, numeri, - e _ (massimo 32, deve iniziare con una lettera)."

cfg_dir="$data_dir/copyparty/cfg"
cfg="$cfg_dir/copyparty.conf"
mkdir -p "$cfg_dir" "$data_dir/copyparty/hist" "$data_dir/scambio"

current_user() { sed -n '/^\[accounts\]/,/^\[/{s/^[[:space:]]*\([A-Za-z][A-Za-z0-9_-]*\):[[:space:]].*/\1/p}' "$cfg" | head -n1; }

if [ "$mode" = status ]; then
  if [ -f "$cfg" ]; then
    echo "Configurazione presente: $cfg"
    echo "Account: $(current_user)"
    echo "Permessi: $(stat -c %a "$cfg") (devono essere 600)"
  else
    echo "Configurazione assente: lancia ./src/scripts/copyparty-setup.sh"
  fi
  exit 0
fi

if [ "$mode" = create ] && [ -f "$cfg" ]; then
  echo "La configurazione esiste gia' ($cfg, account: $(current_user)). Per cambiare la password: $0 --reimposta"
  exit 0
fi
[ "$mode" != reset ] || { [ -f "$cfg" ] || die "Non c'e' ancora una configurazione: lancia $0 senza opzioni."; user="$(current_user)"; [ -n "$user" ] || die "Non trovo l'account nel file di configurazione."; }

command -v openssl >/dev/null || die "openssl non trovato."
pw="$(openssl rand -base64 24 | tr -d '/+=\n' | cut -c1-24)"
[ "${#pw}" -ge 20 ] || die "Non sono riuscito a generare la password."

tmp="$(mktemp "$cfg_dir/.copyparty.XXXXXX")"
cat > "$tmp" <<EOF
# Generato da src/scripts/copyparty-setup.sh. Permessi 600. Modificalo solo se sai cosa fai (documentazione: docs/scambio-file.md).
# Formato: https://github.com/9001/copyparty (sezione "configuration" del README).
[global]
  # indice e miniature: fuori dalla cartella condivisa, in data/copyparty/hist
  hist: /hist
  # indice dei file (ricerca e controllo dei duplicati)
  e2d

[accounts]
  $user: $pw

# Un'unica cartella, data/scambio (visibile nel container come /w). Solo $user puo' leggere e scrivere: nessun accesso anonimo.
[/]
  /w
  accs:
    rw: $user
EOF
chmod 600 "$tmp"
mv -f "$tmp" "$cfg"

echo "Configurazione scritta in $cfg"
echo
echo "  Utente:   $user"
echo "  Password: $pw"
echo
echo "Salva la password nel tuo gestore di password: qui non viene mostrata di nuovo (la rileggi dal file, che ha permessi 600)."
if command -v docker >/dev/null 2>&1 && docker compose ps --status running --services 2>/dev/null | grep -qx copyparty; then
  docker compose restart copyparty >/dev/null && echo "Copyparty riavviato con la nuova configurazione."
else
  echo "Avvialo con:  docker compose up -d copyparty"
fi
