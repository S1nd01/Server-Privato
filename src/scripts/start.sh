#!/usr/bin/env bash
# Comando unico per costruire e avviare tutto: prepara il .env e le cartelle (la prima volta chiede dove
# salvare i dati e i giochi Steam), poi lancia docker compose. Argomenti extra vanno a docker compose:
#   ./src/scripts/start.sh            -> up -d --build --remove-orphans
#   ./src/scripts/start.sh frontend   -> solo quel servizio
set -euo pipefail
cd "$(dirname "$0")/../.."
./src/scripts/sync-env.sh
if ! grep -qE '^API_TOKEN_HASH=sha256:[0-9a-f]{64}$' .env; then
  echo
  echo "Il pannello non ha ancora un token di accesso: ./src/scripts/gen-api-token.sh (poi riavvia con questo comando)."
fi
echo
docker compose up -d --build --remove-orphans "$@"
