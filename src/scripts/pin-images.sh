#!/usr/bin/env bash
# Fissa le versioni delle immagini che oggi seguono `latest` (docs/manutenzione.md, "Versioni fissate").
#
#   ./src/scripts/pin-images.sh           mostra cosa fisserebbe, senza scrivere nulla
#   ./src/scripts/pin-images.sh --apply   scrive le righe nel .env (poi: docker compose up -d)
#
# Parte dai container IN ESECUZIONE, non da `latest` di oggi: fissa quello che sta girando adesso.
# Per ogni immagine prova prima un tag di versione (letto dall'etichetta org.opencontainers.image.version e verificato nel
# registro con `docker manifest inspect`); se non c'e' o non esiste, ripiega sul digest (repo@sha256:...), che e' sempre valido.
# Il digest fissa l'immagine esatta ma Diun non vede piu' le nuove versioni di quel servizio (docs/manutenzione.md).
set -euo pipefail
cd "$(dirname "$0")/../.."

apply=0
case "${1:-}" in
  "") ;;
  --apply) apply=1 ;;
  *) echo "Uso: $0 [--apply]" >&2; exit 2 ;;
esac
[ -f .env ] || { echo "ERRORE: .env non trovato (lancia prima ./src/scripts/start.sh)" >&2; exit 1; }
command -v docker >/dev/null || { echo "ERRORE: docker non trovato" >&2; exit 1; }

# VARIABILE_NEL_ENV:nome_del_container
MAP=(
  TAILSCALE_IMAGE:tailscale
  VAULTWARDEN_IMAGE:vaultwarden
  PIHOLE_IMAGE:pihole
  JELLYFIN_IMAGE:jellyfin
  SEERR_IMAGE:seerr
  MAINTAINERR_IMAGE:maintainerr
  QBITTORRENT_IMAGE:qbittorrent
  PROWLARR_IMAGE:prowlarr
  RADARR_IMAGE:radarr
  SONARR_IMAGE:sonarr
  BAZARR_IMAGE:bazarr
  NTFY_IMAGE:ntfy
  BESZEL_IMAGE:beszel
  BESZEL_AGENT_IMAGE:beszel-agent
  DOCKER_PROXY_IMAGE:docker-proxy-ro
)

# Valori ammessi nel .env: solo i caratteri di un riferimento a immagine (niente apici, spazi, simboli di shell)
SAFE='^[A-Za-z0-9._:@/-]+$'
NOT_A_VERSION='^(latest|main|master|dev|develop|nightly|edge|release|stable|lts)$'

declare -a out_var out_val
note() { printf '  %-22s %s\n' "$1" "$2"; }

echo "Immagini in uso e cosa verrebbe fissato:"
for pair in "${MAP[@]}"; do
  var="${pair%%:*}"; ctr="${pair#*:}"

  if ! ref="$(docker inspect -f '{{.Config.Image}}' "$ctr" 2>/dev/null)"; then
    note "$var" "container '$ctr' non creato: salto"; continue
  fi
  case "$ref" in *@sha256:*) note "$var" "gia' fissata ($ref)"; continue ;; esac

  # repo senza tag (il ":" di una porta del registro sta prima dell'ultimo "/", quindi si toglie solo quello dopo)
  last="${ref##*/}"; repo="${ref%"$last"}${last%%:*}"
  img_id="$(docker inspect -f '{{.Image}}' "$ctr")"
  version="$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$img_id" 2>/dev/null || true)"
  digest="$(docker image inspect -f '{{range .RepoDigests}}{{println .}}{{end}}' "$img_id" 2>/dev/null | grep -F "${repo#docker.io/}@" | head -n1 || true)"
  [ -n "$digest" ] || digest="$(docker image inspect -f '{{range .RepoDigests}}{{println .}}{{end}}' "$img_id" 2>/dev/null | head -n1 || true)"

  new=""; how=""
  if [ -n "$version" ] && ! [[ "$version" =~ $NOT_A_VERSION ]] && [[ "$version" =~ ^[A-Za-z0-9._-]+$ ]]; then
    for cand in "$version" "v${version#v}" "${version#v}"; do
      if docker manifest inspect "$repo:$cand" >/dev/null 2>&1; then new="$repo:$cand"; how="versione $cand"; break; fi
    done
  fi
  if [ -z "$new" ] && [ -n "$digest" ]; then new="$digest"; how="digest (nessun tag di versione verificato)"; fi
  if [ -z "$new" ]; then note "$var" "NON fissabile ($ref): ne' versione ne' digest disponibili"; continue; fi
  [[ "$new" =~ $SAFE ]] || { note "$var" "valore inatteso, salto: $new"; continue; }

  note "$var" "$ref  ->  $new   [$how]"
  out_var+=("$var"); out_val+=("$new")
done

# Immich: una sola variabile per server e riconoscimento (devono avere la stessa versione)
if ver="$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$(docker inspect -f '{{.Image}}' immich_server 2>/dev/null)" 2>/dev/null)" \
   && [ -n "$ver" ] && [[ "$ver" =~ ^[A-Za-z0-9._-]+$ ]] && ! [[ "$ver" =~ $NOT_A_VERSION ]] \
   && docker manifest inspect "ghcr.io/immich-app/immich-server:$ver" >/dev/null 2>&1; then
  note "IMMICH_VERSION" "$(grep -E '^IMMICH_VERSION=' .env | head -n1 | cut -d= -f2- || true)  ->  $ver   [versione]"
  out_var+=("IMMICH_VERSION"); out_val+=("$ver")
else
  note "IMMICH_VERSION" "non determinata (immich_server assente o senza etichetta di versione): fissala a mano"
fi

echo
if [ "${#out_var[@]}" -eq 0 ]; then echo "Niente da fissare."; exit 0; fi
if [ "$apply" -eq 0 ]; then
  echo "Nessuna modifica scritta. Per applicare: $0 --apply"
  exit 0
fi

umask 077
for i in "${!out_var[@]}"; do
  v="${out_var[$i]}"; val="${out_val[$i]}"
  if grep -qE "^${v}=" .env; then
    sed -i "s|^${v}=.*|${v}=${val}|" .env
  else
    printf '%s=%s\n' "$v" "$val" >> .env
  fi
done
chmod 600 .env
echo "Scritte ${#out_var[@]} righe nel .env. Applica con: docker compose up -d"
echo "Per tornare a latest: togli la riga dal .env (o lasciala vuota) e rilancia docker compose up -d."
echo "Per aggiornare un servizio: cambia il valore, poi docker compose pull <servizio> && docker compose up -d <servizio>."
