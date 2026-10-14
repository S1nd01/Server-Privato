#!/usr/bin/env bash
# Genera un token API casuale (256 bit) per il pannello.
# In .env finisce SOLO l'hash SHA-256 (API_TOKEN_HASH); il token si vede una volta sola, qui.
# Rilancialo quando vuoi ruotare il token. Poi: docker compose up -d backend
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { echo "ERRORE: .env non trovato (copia prima .env.example)" >&2; exit 1; }

TOKEN="$(openssl rand -hex 32)"
HASH="$(printf %s "$TOKEN" | sha256sum | cut -d' ' -f1)"

umask 077
if grep -q '^API_TOKEN_HASH=' .env; then
  sed -i "s/^API_TOKEN_HASH=.*/API_TOKEN_HASH=sha256:$HASH/" .env
else
  printf '\nAPI_TOKEN_HASH=sha256:%s\n' "$HASH" >> .env
fi
# il vecchio token in chiaro non serve piu'
sed -i 's/^API_TOKEN=.*/API_TOKEN=/' .env
chmod 600 .env

cat <<EOF

Token del pannello (copialo ORA nel tuo password manager, non verra' mostrato di nuovo):

  $TOKEN

In .env e' salvato solo l'hash. Applica con:  docker compose up -d backend
Se lo perdi: rilancia questo script e usa il nuovo token.
EOF
