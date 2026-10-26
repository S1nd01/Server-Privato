#!/usr/bin/env bash
# Collega i servizi che hanno bisogno di un dato creato solo DOPO il loro primo avvio. Si puo' rilanciare quando vuoi.
#  - Recyclarr: legge le chiavi API di Radarr e Sonarr (data/<app>/config/config.xml) e le scrive nel .env
#  - Beszel: legge la chiave pubblica del hub (data/beszel/data/id_ed25519.pub) e la scrive nel .env per l'agente
# Se un dato cambia, ricrea SOLO il container interessato. Lo lancia da solo start.sh dopo ogni avvio.
# Non mostra mai le chiavi: restano nel .env (permessi 600).
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077
[ -f .env ] || { echo "ERRORE: .env non trovato: lancia prima ./src/scripts/sync-env.sh" >&2; exit 1; }

get() { { grep -E "^$1=" .env || true; } | head -n1 | cut -d= -f2-; }
set_kv() {
  local key="$1" value="$2" escaped
  escaped="${value//\\/\\\\}"; escaped="${escaped//&/\\&}"; escaped="${escaped//|/\\|}"
  if grep -q "^$key=" .env; then sed -i "s|^$key=.*|$key=$escaped|" .env; else printf '%s=%s\n' "$key" "$value" >> .env; fi
}
data_dir="$(get DATA_DIR)"
[ -n "$data_dir" ] || { echo "ERRORE: DATA_DIR vuoto nel .env: lancia ./src/scripts/sync-env.sh" >&2; exit 1; }

recreate=()

# ---------------------------------------------------------------- Recyclarr: chiavi API di Radarr e Sonarr
arr_key() {   # $1 = radarr|sonarr
  local f="$data_dir/$1/config/config.xml"
  [ -r "$f" ] || return 0
  sed -n 's:.*<ApiKey>\([A-Za-z0-9]\{16,64\}\)</ApiKey>.*:\1:p' "$f" | head -n1
}
for app in radarr sonarr; do
  var="$(printf '%s' "$app" | tr a-z A-Z)_API_KEY"
  new="$(arr_key "$app")"
  if [ -z "$new" ]; then
    echo "Recyclarr: ${app^} non ha ancora creato la sua configurazione (avvialo almeno una volta): ${var} resta com'e'."
    continue
  fi
  if [ "$(get "$var")" != "$new" ]; then
    set_kv "$var" "$new"
    echo "Recyclarr: chiave API di ${app^} salvata nel .env."
    recreate+=(recyclarr)
  fi
done

# ---------------------------------------------------------------- Beszel: chiave pubblica del hub
pub="$data_dir/beszel/data/id_ed25519.pub"
if [ -z "$(get BESZEL_KEY)" ]; then
  if docker compose ps --status running --services 2>/dev/null | grep -qx beszel; then
    for _ in $(seq 1 20); do [ -r "$pub" ] && break; sleep 1; done   # il hub la crea al primo avvio
  fi
  if [ -r "$pub" ]; then
    key="$(head -n1 "$pub" | tr -d '\r\n')"
    if [ -n "$key" ]; then
      set_kv BESZEL_KEY "$key"
      echo "Beszel: chiave del hub salvata nel .env."
      recreate+=(beszel-agent)
    fi
  else
    echo "Beszel: chiave del hub non trovata (data/beszel/data/id_ed25519.pub). Avvia il hub, poi rilancia questo script;" >&2
    echo "        in alternativa copia la chiave dalla finestra 'Aggiungi sistema' del hub in BESZEL_KEY nel .env (docs/beszel.md)." >&2
  fi
fi

# ---------------------------------------------------------------- ricrea solo cio' che e' cambiato
if [ "${#recreate[@]}" -gt 0 ]; then
  mapfile -t uniq < <(printf '%s\n' "${recreate[@]}" | sort -u)
  docker compose up -d "${uniq[@]}"
fi
echo "post-avvio completato."
