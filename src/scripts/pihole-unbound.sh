#!/usr/bin/env bash
# Collega (o scollega) Pi-hole a Unbound. Non cambia nulla finche' non lo chiedi tu.
#   ./src/scripts/pihole-unbound.sh stato   mostra l'upstream attuale e prova Unbound
#   ./src/scripts/pihole-unbound.sh on      Pi-hole usa Unbound (salva prima l'upstream di adesso)
#   ./src/scripts/pihole-unbound.sh off     torna all'upstream salvato (o a Cloudflare, se non ce n'e')
# Unbound risponde sulla rete privata dns: 10.89.53.2, porta 5335 (compose.yaml, unbound/unbound.conf).
set -euo pipefail
cd "$(dirname "$0")/../.."

UNBOUND_UP="10.89.53.2#5335"
FALLBACK='["1.1.1.1","1.0.0.1"]'
data_dir="$({ grep -E '^DATA_DIR=' .env 2>/dev/null || true; } | head -n1 | cut -d= -f2-)"
[ -n "$data_dir" ] || { echo "ERRORE: .env o DATA_DIR mancanti: lancia ./src/scripts/sync-env.sh" >&2; exit 1; }
saved="$data_dir/pihole/upstream-prima-di-unbound.json"

running() { docker compose ps --status running --services 2>/dev/null | grep -qx "$1"; }
running pihole  || { echo "ERRORE: Pi-hole non e' acceso (docker compose up -d pihole)." >&2; exit 1; }
current() { docker compose exec -T pihole pihole-FTL --config dns.upstreams | tr -d '\r'; }
# FTL stampa la lista come "[ 8.8.8.8, 8.8.4.4 ]": la riscrivo come array JSON, che accetta sempre in ingresso
to_json() {
  printf '%s' "$1" | tr -d '[]"' | tr ',' '\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d' \
    | awk 'BEGIN { printf "[" } { printf "%s\"%s\"", (NR > 1 ? "," : ""), $0 } END { printf "]" }'
}
test_unbound() {
  # una richiesta DNS vera a Unbound, dal container di Pi-hole
  docker compose exec -T pihole dig +short +time=10 +tries=1 -p 5335 @10.89.53.2 example.com 2>/dev/null | head -n1
}

case "${1:-stato}" in
  stato)
    echo "Upstream di Pi-hole: $(current)"
    if running unbound; then
      ans="$(test_unbound || true)"
      if [ -n "$ans" ]; then echo "Unbound risponde (example.com -> $ans)."; else echo "Unbound e' acceso ma non risponde alla prova: docker compose logs unbound" >&2; fi
    else
      echo "Unbound non e' acceso: docker compose up -d unbound"
    fi
    ;;
  on)
    running unbound || { echo "ERRORE: Unbound non e' acceso (docker compose up -d unbound)." >&2; exit 1; }
    ans="$(test_unbound || true)"
    [ -n "$ans" ] || { echo "ERRORE: Unbound non risponde, non cambio nulla. Guarda: docker compose logs unbound" >&2; exit 1; }
    cur="$(current)"
    case "$cur" in *10.89.53.2*) echo "Pi-hole usa gia' Unbound."; exit 0 ;; esac
    umask 077
    to_json "$cur" > "$saved"
    docker compose exec -T pihole pihole-FTL --config dns.upstreams "[\"$UNBOUND_UP\"]" >/dev/null
    echo "Fatto: Pi-hole usa Unbound. Upstream precedente salvato in $saved."
    echo "La prima volta ogni sito e' piu' lento (Unbound parte con la cache vuota): dopo qualche minuto si assesta."
    echo "Per tornare indietro: ./src/scripts/pihole-unbound.sh off"
    ;;
  off)
    prev="$FALLBACK"
    [ -s "$saved" ] && prev="$(cat "$saved")"
    docker compose exec -T pihole pihole-FTL --config dns.upstreams "$prev" >/dev/null
    echo "Fatto: Pi-hole usa di nuovo $prev."
    ;;
  *) echo "Uso: $0 [stato|on|off]" >&2; exit 2 ;;
esac
