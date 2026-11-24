#!/usr/bin/env bash
# Verifica che qBittorrent esca davvero dalla VPN (docs/vpn.md).
#
#   ./src/scripts/vpn-test.sh                 controlla i container, l'IP pubblico e l'accesso al web di qBittorrent
#   ./src/scripts/vpn-test.sh --kill-switch   in piu' ferma la VPN per qualche secondo e controlla che qBittorrent resti SENZA rete
#                                             (interrompe i download; alla fine ripristina tutto)
#
# Il test dell'IP e' la prova che conta: l'indirizzo visto da internet dentro qBittorrent deve essere diverso da quello del server.
set -uo pipefail
cd "$(dirname "$0")/../.."

fail=0
ok() { printf '  OK      %s\n' "$*"; }
ko() { printf '  FALLITO %s\n' "$*"; fail=1; }
die() { printf 'ERRORE: %s\n' "$*" >&2; exit 2; }
command -v docker >/dev/null || die "docker non trovato."
kill_test=0
case "${1:-}" in "") ;; --kill-switch) kill_test=1 ;; *) die "Uso: $0 [--kill-switch]" ;; esac

myip() { curl -fsS -m 10 https://api.ipify.org 2>/dev/null || curl -fsS -m 10 https://ifconfig.me 2>/dev/null; }
inside_ip() { docker exec qbittorrent sh -c 'curl -fsS -m 10 https://api.ipify.org 2>/dev/null || wget -qO- -T 10 https://api.ipify.org 2>/dev/null'; }
running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ]; }

echo "Container"
running gluetun || die "gluetun non e' in esecuzione: la VPN e' attiva nel .env? (./src/scripts/vpn-setup.sh --stato; docker compose up -d gluetun qbittorrent)"
running qbittorrent || die "qbittorrent non e' in esecuzione."
health="$(docker inspect -f '{{.State.Health.Status}}' gluetun 2>/dev/null)"
[ "$health" = healthy ] && ok "gluetun e' healthy (tunnel attivo)" || ko "gluetun non e' healthy (stato: ${health:-sconosciuto}): guarda  docker logs gluetun"
[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' qbittorrent)" = "container:$(docker inspect -f '{{.Id}}' gluetun)" ] \
  && ok "qBittorrent usa la rete di gluetun" || ko "qBittorrent NON usa la rete di gluetun (riavvialo: docker compose up -d --force-recreate qbittorrent)"

echo "Indirizzo pubblico"
host_ip="$(myip)"; vpn_ip="$(inside_ip)"
[ -n "$host_ip" ] || ko "non riesco a leggere l'IP del server (rete assente?)"
[ -n "$vpn_ip" ] || ko "da dentro qBittorrent non esce nulla (tunnel non ancora pronto? guarda docker logs gluetun)"
if [ -n "$host_ip" ] && [ -n "$vpn_ip" ]; then
  if [ "$host_ip" != "$vpn_ip" ]; then ok "server: $host_ip   qBittorrent: $vpn_ip (diversi)"; else ko "qBittorrent esce con lo STESSO IP del server ($host_ip): la VPN non e' in uso"; fi
fi

echo "Accesso al web di qBittorrent"
code="$(docker exec radarr curl -s -o /dev/null -m 10 -w '%{http_code}' http://qbittorrent:8080 2>/dev/null)"
case "$code" in 200|401|403) ok "Radarr raggiunge http://qbittorrent:8080 (risposta $code)" ;; *) ko "Radarr non raggiunge http://qbittorrent:8080 (risposta: ${code:-nessuna}): FIREWALL_INPUT_PORTS, alias di rete" ;; esac

if [ "$kill_test" = 1 ]; then
  echo "Kill switch (i download si fermano per qualche secondo)"
  docker stop gluetun >/dev/null
  leak="$(inside_ip)"
  if [ -z "$leak" ]; then ok "con la VPN ferma qBittorrent non raggiunge Internet"; else ko "con la VPN ferma qBittorrent ha raggiunto Internet con l'IP $leak: PERDITA DI IP"; fi
  docker compose up -d gluetun qbittorrent >/dev/null 2>&1
  # dopo un riavvio di gluetun qBittorrent deve ripartire per riagganciare la rete nuova
  docker restart qbittorrent >/dev/null 2>&1
  echo "  (VPN e qBittorrent riavviati: controlla con  docker compose ps)"
fi

echo
[ "$fail" = 0 ] && echo "Tutto a posto." || echo "Ci sono controlli falliti: non scaricare nulla finche' non li risolvi."
exit "$fail"
