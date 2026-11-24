#!/usr/bin/env bash
# Rimette spenti i servizi che avevi fermato dal pannello (docs/risparmio.md).
#
# `docker compose up -d` riaccende tutto cio' che e' nel compose, anche quello che avevi spento: il pannello ricorda cosa
# hai fermato (data/panel/stopped.txt, scritto dal backend) e questo script lo ferma di nuovo. Lo lancia anche start.sh.
# Non tocca altro: solo i container elencati e solo se sono in funzione. Un container fermato con `docker stop` o da
# Portainer non e' nell'elenco (il pannello registra solo cio' che passa da lui).
#
#   ./src/scripts/riapplica-stato.sh           ferma i container elencati ancora in funzione
#   ./src/scripts/riapplica-stato.sh --prova   mostra cosa fermerebbe, senza fermare nulla
set -euo pipefail
cd "$(dirname "$0")/../.."

dry=0
case "${1:-}" in
  "") ;;
  --prova) dry=1 ;;
  *) echo "Uso: $0 [--prova]" >&2; exit 2 ;;
esac

data_dir="$({ grep -E '^DATA_DIR=' .env 2>/dev/null || true; } | head -n1 | cut -d= -f2-)"
data_dir="${data_dir:-./data}"
list="$data_dir/panel/stopped.txt"

if [ ! -f "$list" ]; then
  echo "Nessun servizio spento dal pannello da riapplicare."
  exit 0
fi

project="$(docker compose config --format json | python3 -c 'import json, sys; print(json.load(sys.stdin)["name"])')"
stopped=0
while IFS= read -r name || [ -n "$name" ]; do
  # stessa regola del backend (desired.py): niente opzioni, spazi o percorsi
  [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]] || continue
  [[ "$name" != hs_frontend && "$name" != hs_backend && "$name" != tailscale ]] || continue
  owner="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$name" 2>/dev/null || true)"
  [ "$owner" = "$project" ] || continue
  [ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)" = "true" ] || continue
  if [ "$dry" -eq 1 ]; then
    echo "Fermerei: $name"
  else
    echo "Ferma (come lasciato dal pannello): $name"
    docker stop -t 20 "$name" >/dev/null || echo "  non sono riuscito a fermare $name" >&2
  fi
  stopped=$((stopped + 1))
done < "$list"

if [ "$stopped" -eq 0 ]; then echo "Tutto come lo avevi lasciato."; fi
