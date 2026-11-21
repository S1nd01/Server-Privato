#!/usr/bin/env bash
# Comando unico per costruire e avviare tutto: prepara il .env e le cartelle dati/, poi lancia docker compose.
# Argomenti extra vanno a docker compose:
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
# Dati che esistono solo dopo il primo avvio (chiavi di Radarr/Sonarr per Recyclarr, chiave del hub Beszel).
# Se qualcosa non e' ancora pronto lo dice senza fermarsi: si rilancia a mano con ./src/scripts/post-avvio.sh
./src/scripts/post-avvio.sh || echo "Il collegamento di Recyclarr e Beszel non e' riuscito: rilancia ./src/scripts/post-avvio.sh tra qualche minuto." >&2
# Il ponte Telegram ha un profilo a parte (non parte con `up`): se l'hai configurato (telegram-setup.sh) lo riavvia qui, per esempio dopo un `down`.
data_dir="$({ grep -E '^DATA_DIR=' .env 2>/dev/null || true; } | head -n1 | cut -d= -f2-)"
if [ -s "${data_dir:-./data}/telegram/telegram_bot_token" ] && grep -qE '^TELEGRAM_CHAT_ID=.' .env; then
  docker compose --profile telegram up -d ntfy-telegram || echo "Il ponte Telegram non e' partito: docker compose --profile telegram logs ntfy-telegram" >&2
fi
# `up` ha riacceso anche cio' che avevi spento dal pannello: lo rimette come lo avevi lasciato (dopo post-avvio, che ha bisogno
# di Radarr e Sonarr in funzione per leggerne le chiavi).
./src/scripts/riapplica-stato.sh || echo "Non sono riuscito a riapplicare lo stato dei servizi spenti: rilancia ./src/scripts/riapplica-stato.sh" >&2
