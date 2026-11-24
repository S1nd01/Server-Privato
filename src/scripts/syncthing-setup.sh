#!/usr/bin/env bash
# Mette in sicurezza Syncthing al primo avvio (docs/syncthing.md).
#
#   ./src/scripts/syncthing-setup.sh            applica le impostazioni e mostra l'ID del dispositivo e la password UNA volta
#   ./src/scripts/syncthing-setup.sh --stato    mostra le impostazioni attuali (senza cambiarle)
#
# Cosa imposta (tutto tramite l'API di Syncthing, con la chiave che si e' generato da solo):
#   - niente server di scoperta globale, niente relay pubblici, niente NAT-PMP/UPnP, niente scoperta in LAN, niente statistiche:
#     i dispositivi si trovano solo per indirizzo, passando dal tailnet (tcp://<server>.ts.net:22000);
#   - utente e password per l'interfaccia web (finche' non li imposti l'interfaccia e' aperta a chiunque sia sul tailnet);
#   - controllo dell'Host disattivato: l'interfaccia e' dietro Tailscale Serve, che usa un altro nome di host, e senza questo
#     Syncthing risponde "Host check error".
# Non provato su un'immagine reale di Syncthing: se un passaggio fallisce lo script si ferma e dice quale.
# Va lanciato dopo `docker compose up -d syncthing`, col tuo utente, senza sudo.
set -euo pipefail
cd "$(dirname "$0")/../.."

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" != 0 ] || die "Non lanciarlo con sudo."
command -v docker >/dev/null || die "docker non trovato."
status_only=0
case "${1:-}" in "") ;; --stato) status_only=1 ;; *) die "Uso: $0 [--stato]" ;; esac

docker inspect -f '{{.State.Running}}' syncthing 2>/dev/null | grep -qx true || die "Il container syncthing non e' in esecuzione: docker compose up -d syncthing"

# curl e' nell'immagine ufficiale (ci fa il controllo di salute); se un giorno non ci fosse, meglio dirlo che indovinare
dx() { docker exec syncthing "$@"; }
dx sh -c 'command -v curl >/dev/null' || die "Nell'immagine di Syncthing manca curl: imposta a mano i punti elencati nell'intestazione (docs/syncthing.md)."

# la configurazione si crea al primo avvio: qualche secondo
key=""
for _ in $(seq 1 30); do
  key="$(dx sh -c "sed -n 's:.*<apikey>\\(.*\\)</apikey>.*:\\1:p' /var/syncthing/config/config.xml 2>/dev/null" | head -n1 | tr -d '\r')"
  [ -n "$key" ] && break
  sleep 1
done
[ -n "$key" ] || die "Non trovo la chiave API in /var/syncthing/config/config.xml (Syncthing non ha ancora finito l'avvio?)."

api() {  # api METODO PERCORSO [JSON]
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$body" ]; then
    dx curl -fsS -X "$method" -H "X-API-Key: $key" -H 'Content-Type: application/json' -d "$body" "http://127.0.0.1:8384$path"
  else
    dx curl -fsS -X "$method" -H "X-API-Key: $key" "http://127.0.0.1:8384$path"
  fi
}

if [ "$status_only" = 1 ]; then
  echo "Opzioni:"; api GET /rest/config/options | tr ',' '\n' | grep -E '"(globalAnnounceEnabled|localAnnounceEnabled|relaysEnabled|natEnabled|urAccepted|crashReportingEnabled)"' || true
  echo "Interfaccia:"; api GET /rest/config/gui | tr ',' '\n' | grep -E '"(user|insecureSkipHostcheck|address)"' || true
  exit 0
fi

command -v openssl >/dev/null || die "openssl non trovato."
user="$(id -un)"
pw="$(openssl rand -base64 24 | tr -d '/+=\n' | cut -c1-24)"
[ "${#pw}" -ge 20 ] || die "Non sono riuscito a generare la password."

# prima l'autenticazione: e' l'impostazione che chiude l'interfaccia
api PATCH /rest/config/gui "{\"user\":\"$user\",\"password\":\"$pw\",\"insecureSkipHostcheck\":true}" >/dev/null || die "Non sono riuscito a impostare utente e password."
api PATCH /rest/config/options '{"globalAnnounceEnabled":false,"localAnnounceEnabled":false,"relaysEnabled":false,"natEnabled":false,"urAccepted":-1,"crashReportingEnabled":false,"startBrowser":false}' >/dev/null \
  || die "Utente e password sono impostati, ma non le opzioni di rete: guarda docs/syncthing.md e impostale dall'interfaccia (Azioni, Impostazioni)."

# verifica: senza credenziali l'interfaccia deve rifiutare
code="$(dx curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8384/rest/system/status || true)"
case "$code" in 401|403) ;; *) echo "ATTENZIONE: senza credenziali l'interfaccia ha risposto $code invece di 401/403: controlla la password dall'interfaccia." >&2 ;; esac

id="$(api GET /rest/system/status | tr ',' '\n' | sed -n 's/.*"myID": *"\([A-Z0-9-]*\)".*/\1/p' | head -n1)"
echo "Syncthing configurato."
echo
echo "  Utente:   $user"
echo "  Password: $pw"
echo "  ID del dispositivo: ${id:-(non letto: lo vedi in Azioni, Mostra ID)}"
echo
echo "Salva la password nel tuo gestore di password: qui non viene mostrata di nuovo."
echo "Sugli altri dispositivi aggiungi questo come indirizzo del server (non usare 'dynamic'):  tcp://<nome-server>.<tuarete>.ts.net:22000"
echo "Le cartelle da sincronizzare vanno create sotto /sync (per esempio /sync/documenti): corrisponde a data/sync sul server."
