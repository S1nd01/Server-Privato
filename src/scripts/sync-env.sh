#!/usr/bin/env bash
# Aggiorna il tuo .env dopo un aggiornamento del progetto:
#  - aggiunge le variabili nuove di .env.example SENZA toccare quelle che hai già
#  - genera la password di Pi-hole se manca
#  - crea le cartelle dei dati col tuo utente (altrimenti Docker le crea come root e Jellyfin non parte)
# Si può rilanciare quante volte vuoi.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "ERRORE: .env non trovato. Prima: cp .env.example .env" >&2; exit 1; }
umask 077

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
chmod 600 .env

data_dir="$(grep -E '^DATA_DIR=' .env | head -n1 | cut -d= -f2-)"
if [ -n "$data_dir" ] && [[ "$data_dir" != *CAMBIAMI* ]]; then
  mkdir -p "$data_dir"/{jellyfin/config,jellyfin/cache,media,panel,pihole,tailscale,restore}
  echo "Cartelle dei dati pronte in $data_dir"
fi

echo "Variabili aggiunte al .env: ${added[*]:-nessuna}"
if grep -q 'CAMBIAMI' .env; then
  echo "ATTENZIONE: nel .env c'è ancora il segnaposto CAMBIAMI: sostituiscilo con la tua cartella home." >&2
fi
