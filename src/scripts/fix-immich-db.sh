#!/usr/bin/env bash
# Riallinea la password del database di Immich a quella scritta nel .env, SENZA cancellare nulla.
# Serve quando Immich scrive: password authentication failed for user "postgres"
# (il database e' stato creato con un'altra password, per esempio perche' il .env e' stato rifatto o sostituito).
# Funziona perche' dentro il container di Postgres la connessione locale (socket) non chiede la password.
set -euo pipefail
cd "$(dirname "$0")/../.."

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }

[ -f .env ] || die "Manca il .env: lancia prima ./src/scripts/sync-env.sh"
pw="$({ grep -E '^IMMICH_DB_PASSWORD=' .env || true; } | head -n1 | cut -d= -f2-)"
[ -n "$pw" ] || die "IMMICH_DB_PASSWORD e' vuota nel .env."
[[ "$pw" =~ ^[A-Za-z0-9]+$ ]] || die "IMMICH_DB_PASSWORD deve contenere solo lettere e numeri (simboli come \$ o # si rompono)."

docker compose up -d immich-postgres
printf 'Aspetto che Postgres sia pronto'
for _ in $(seq 1 40); do
  if docker compose exec -T immich-postgres pg_isready -U postgres -q; then ready=1; break; fi
  printf '.'; sleep 2
done
echo
[ "${ready:-0}" = 1 ] || die "Postgres non risponde: guarda docker compose logs immich-postgres"

docker compose exec -T immich-postgres psql -U postgres -v ON_ERROR_STOP=1 -c "ALTER USER postgres WITH PASSWORD '$pw';"
docker compose up -d immich-redis immich-machine-learning immich-server
docker compose restart immich-server
echo "Fatto: la password del database ora coincide col .env. Controlla con: docker compose logs -f immich-server"
