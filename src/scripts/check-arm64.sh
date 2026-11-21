#!/usr/bin/env bash
# Controlla che le immagini del compose esistano per il Raspberry (linux/arm64), PRIMA di spostare il server.
#
#   ./src/scripts/check-arm64.sh            controlla tutte le immagini, anche quelle dei profili (Portainer, strumenti)
#   ./src/scripts/check-arm64.sh amd64      controlla un'altra architettura (arm64, amd64, arm)
#
# Interroga il registro con `docker manifest inspect` (serve Internet, non scarica le immagini). Una riga per immagine:
#   ok         c'e' una versione per quell'architettura
#   MANCA      il registro risponde ma quell'architettura non c'e': il servizio non girerebbe sul Raspberry
#   ?          non verificabile (registro irraggiungibile, immagine privata, o immagine a una sola architettura senza elenco)
# Esce con 1 se c'e' almeno un MANCA. Le immagini costruite in locale (il backend del pannello) usano python:3.12-slim, node:22-alpine e nginx:alpine, che sono multi-architettura.
set -uo pipefail
cd "$(dirname "$0")/../.."
arch="${1:-arm64}"
case "$arch" in arm64|amd64|arm) ;; *) echo "Uso: $0 [arm64|amd64|arm]" >&2; exit 2 ;; esac
command -v docker >/dev/null || { echo "ERRORE: docker non trovato" >&2; exit 1; }

# Il compose chiede alcune variabili obbligatorie: se manca il .env se ne mettono di finte (qui servono solo i nomi delle immagini).
env_args=()
if [ ! -f .env ]; then
  env_args=(env DATA_DIR=/tmp/hs-check TZ=UTC PIHOLE_PASSWORD=x IMMICH_DB_PASSWORD=x TS_CERT_DOMAIN=x.ts.net)
fi

if ! images="$("${env_args[@]}" docker compose --profile '*' config --images 2>/dev/null | sort -u)"; then
  echo "ERRORE: docker compose config non riesce a leggere compose.yaml" >&2; exit 1
fi

missing=0; unknown=0; ok=0
while IFS= read -r img; do
  [ -n "$img" ] || continue
  case "$img" in homeserver-*) continue ;; esac     # costruita in locale (backend)
  if out="$(timeout 40 docker manifest inspect "$img" 2>&1)"; then
    if grep -q "\"architecture\": \"$arch\"" <<<"$out"; then
      printf '  ok      %s\n' "$img"; ok=$((ok + 1))
    elif grep -q '"architecture"' <<<"$out"; then
      printf '  MANCA   %s   (%s non disponibile)\n' "$img" "$arch"; missing=$((missing + 1))
    else
      printf '  ?       %s   (immagine a una sola architettura: controlla sul sito del progetto)\n' "$img"; unknown=$((unknown + 1))
    fi
  else
    printf '  ?       %s   (%s)\n' "$img" "$(head -n1 <<<"$out" | cut -c1-90)"; unknown=$((unknown + 1))
  fi
done <<<"$images"

echo
echo "Per $arch: $ok ok, $missing mancanti, $unknown non verificabili."
[ "$missing" -eq 0 ]
