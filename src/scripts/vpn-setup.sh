#!/usr/bin/env bash
# Attiva o disattiva la VPN WireGuard di qBittorrent (compose.vpn.yml, docs/vpn.md).
#
#   ./src/scripts/vpn-setup.sh /percorso/wg0.conf    legge il file WireGuard del tuo provider e attiva la VPN nel .env
#   ./src/scripts/vpn-setup.sh --disattiva           toglie la VPN dal .env (qBittorrent torna a uscire con la tua connessione)
#   ./src/scripts/vpn-setup.sh --stato               dice se la VPN e' attiva nel .env
#
# Funziona con qualsiasi provider che ti faccia scaricare un file WireGuard (.conf): Mullvad, Proton, IVPN, AirVPN, un tuo server...
# Cosa fa: copia la chiave privata in ~/.wireguard-key (permessi 600, FUORI dal progetto), scrive nel .env indirizzi, chiave
# pubblica e endpoint del server, e aggiunge compose.vpn.yml a COMPOSE_FILE. Non avvia nulla: i passi dopo sono stampati alla fine.
# Limiti: non supporta la PresharedKey (si ferma e lo dice); se l'endpoint e' un nome lo risolve in un indirizzo IP una volta sola
# (se il provider cambia l'indirizzo, rilancia lo script con il file nuovo). Va lanciato col tuo utente, senza sudo.
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" != 0 ] || die "Non lanciarlo con sudo: la chiave finirebbe in /root."
[ -f .env ] || die "Manca il .env: lancia prima ./src/scripts/start.sh (o sync-env.sh)."
get() { { grep -E "^$1=" .env || true; } | head -n1 | cut -d= -f2-; }
set_kv() {
  local key="$1" value="$2" escaped
  escaped="${value//\\/\\\\}"; escaped="${escaped//&/\\&}"; escaped="${escaped//|/\\|}"
  if grep -q "^$key=" .env; then sed -i "s|^$key=.*|$key=$escaped|" .env; else printf '%s=%s\n' "$key" "$value" >> .env; fi
}
drop_key() { sed -i "/^$1=/d" .env; }
VPN_FILE="compose.vpn.yml"

case "${1:-}" in
  --stato)
    cf="$(get COMPOSE_FILE)"
    if [[ ":$cf:" == *":$VPN_FILE:"* ]]; then
      echo "VPN ATTIVA nel .env (COMPOSE_FILE=$cf)"
      echo "Indirizzo del server VPN: $(get WIREGUARD_ENDPOINT_IP):$(get WIREGUARD_ENDPOINT_PORT)"
      kf="$(get WIREGUARD_KEY_FILE)"
      echo "File della chiave: ${kf:-(manca)} $( [ -f "$kf" ] && echo "(presente, permessi $(stat -c %a "$kf"))" || echo "(NON TROVATO)" )"
    else
      echo "VPN disattivata: qBittorrent esce con la tua connessione."
    fi
    exit 0 ;;
  --disattiva)
    cf="$(get COMPOSE_FILE)"
    if [[ ":$cf:" != *":$VPN_FILE:"* ]]; then echo "La VPN era gia' disattivata."; exit 0; fi
    new="$(printf '%s' "$cf" | tr ':' '\n' | grep -vx "$VPN_FILE" | paste -sd: -)"
    # se restano solo i file che compose carica comunque di serie, la riga si toglie del tutto
    if [ -z "$new" ] || [ "$new" = "compose.yaml" ] || [ "$new" = "compose.yaml:compose.override.yml" ]; then drop_key COMPOSE_FILE; else set_kv COMPOSE_FILE "$new"; fi
    echo "VPN disattivata nel .env. Applica con:  docker compose up -d"
    echo "(La chiave in $(get WIREGUARD_KEY_FILE) e le variabili WIREGUARD_* restano: cancellale tu se non ti servono piu'.)"
    exit 0 ;;
  ""|-*) die "Uso: $0 /percorso/wg0.conf | --disattiva | --stato" ;;
esac

conf="$1"
[ -f "$conf" ] || die "File non trovato: $conf"
[ -f "$VPN_FILE" ] || die "Manca $VPN_FILE nella cartella del progetto."

# lettura del file WireGuard: [Interface] e [Peer], chiavi in qualsiasi maiuscola/minuscola, spazi attorno al =
section=""; priv=""; addr=""; pub=""; psk=""; endpoint=""; peers=0
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%#*}"; line="$(printf '%s' "$line" | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  [ -n "$line" ] || continue
  case "$line" in
    "[Interface]"|"[interface]") section=i; continue ;;
    "[Peer]"|"[peer]") section=p; peers=$((peers + 1)); continue ;;
  esac
  k="$(printf '%s' "${line%%=*}" | tr -d ' ' | tr 'A-Z' 'a-z')"; v="$(printf '%s' "${line#*=}" | sed 's/^[[:space:]]*//')"
  case "$section:$k" in
    i:privatekey) priv="$v" ;;
    i:address) addr="$v" ;;
    p:publickey) pub="$v" ;;
    p:presharedkey) psk="$v" ;;
    p:endpoint) endpoint="$v" ;;
  esac
done < "$conf"

[ "$peers" -eq 1 ] || die "Il file ha $peers sezioni [Peer]: ne serve una sola."
[ -z "$psk" ] || die "Il file usa una PresharedKey: questa versione non la supporta (servirebbe un secondo segreto in compose.vpn.yml). Scegli un file senza, se il provider lo permette."
[[ "$priv" =~ ^[A-Za-z0-9+/]{42,43}=$ ]] || die "PrivateKey assente o non valida."
[[ "$pub" =~ ^[A-Za-z0-9+/]{42,43}=$ ]] || die "PublicKey del peer assente o non valida."
[[ "$addr" =~ ^[0-9A-Fa-f.:/,[:space:]]+$ ]] && [ -n "$addr" ] || die "Address assente o non valido."
addr="$(printf '%s' "$addr" | tr -d ' ')"
[[ "$endpoint" =~ ^(.+):([0-9]{1,5})$ ]] || die "Endpoint assente o non nel formato host:porta."
host="${BASH_REMATCH[1]}"; port="${BASH_REMATCH[2]}"
[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || die "Porta dell'endpoint non valida: $port"
if [[ ! "$host" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
  ip="$(getent ahostsv4 "$host" 2>/dev/null | awk 'NR==1 {print $1}' || true)"
  [ -n "$ip" ] || die "Non riesco a risolvere l'endpoint '$host' in un indirizzo IPv4 (gluetun vuole un IP)."
  echo "Endpoint $host risolto in $ip (se il provider lo cambia, rilancia questo script)."
  host="$ip"
fi

# la chiave sta fuori dal progetto e dal .env: non finisce in git, nei backup del progetto ne' in `docker inspect`
key_file="${WIREGUARD_KEY_FILE_OUT:-$HOME/.wireguard-key}"
printf '%s\n' "$priv" > "$key_file"; chmod 600 "$key_file"

set_kv WIREGUARD_ADDRESSES "$addr"
set_kv WIREGUARD_PUBLIC_KEY "$pub"
set_kv WIREGUARD_ENDPOINT_IP "$host"
set_kv WIREGUARD_ENDPOINT_PORT "$port"
set_kv WIREGUARD_KEY_FILE "$key_file"

cf="$(get COMPOSE_FILE)"
if [ -z "$cf" ]; then cf="compose.yaml:compose.override.yml:$VPN_FILE"
elif [[ ":$cf:" != *":$VPN_FILE:"* ]]; then cf="$cf:$VPN_FILE"; fi
set_kv COMPOSE_FILE "$cf"

echo "VPN configurata."
echo "  Chiave privata: $key_file (permessi 600; fanne una copia nel tuo gestore di password: non e' nei backup)"
echo "  Server VPN:     $host:$port"
echo "  COMPOSE_FILE=$cf"
echo
echo "Passi successivi:"
echo "  1. docker compose config -q                       (controlla che il compose sia valido)"
echo "  2. docker compose up -d gluetun qbittorrent       (qBittorrent riparte dietro la VPN)"
echo "  3. ./src/scripts/vpn-test.sh                      (verifica che l'IP sia quello della VPN e che il kill switch tenga)"
echo "Se usi i tracker privati, leggi prima la sezione dedicata di docs/vpn.md: alcuni vietano o segnalano le VPN."
