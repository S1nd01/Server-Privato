#!/usr/bin/env bash
# Configura il ponte ntfy -> Telegram (docs/telegram.md). Si puo' rilanciare: riusa cio' che esiste gia'.
#
#   ./src/scripts/telegram-setup.sh             configura (o ripara) e avvia il ponte
#   ./src/scripts/telegram-setup.sh --da-capo   richiede il token del bot, rifa' il chat ID e rigenera l'utente ntfy
#
# Prima: crea il bot con @BotFather (/newbot) e scrivigli /start dal tuo account Telegram.
# Cosa fa:
#   1. chiede il token del bot (senza mostrarlo) e lo salva in data/telegram/telegram_bot_token, permessi 600
#   2. ricava il tuo chat ID dai messaggi che hai mandato al bot, ti chiede conferma e ti scrive un messaggio di prova
#   3. crea in ntfy l'utente "telegram" con permesso di SOLA LETTURA sull'argomento e ne salva il token in data/telegram/ntfy_token
#   4. scrive TELEGRAM_CHAT_ID nel .env e avvia il container ntfy-telegram
# I token non finiscono mai nel .env, nei log, nelle variabili d'ambiente del container né sulla riga di comando (chi guarda `ps` non li vede).
set -euo pipefail
cd "$(dirname "$0")/../.."

redo=0
case "${1:-}" in
  "") ;;
  --da-capo) redo=1 ;;
  *) echo "Uso: $0 [--da-capo]" >&2; exit 2 ;;
esac

die() { echo "ERRORE: $*" >&2; exit 1; }
for c in docker curl python3 openssl; do command -v "$c" >/dev/null || die "manca il comando '$c'"; done
[ -f .env ] || die ".env non trovato (lancia prima ./src/scripts/start.sh)"

envget() { { grep -E "^$1=" .env 2>/dev/null || true; } | head -n1 | cut -d= -f2-; }
envset() {
  local key="$1" value="$2" escaped
  escaped="$(printf '%s' "$value" | sed 's/[&|\\]/\\&/g')"
  if grep -q "^$key=" .env; then sed -i "s|^$key=.*|$key=$escaped|" .env; else printf '%s=%s\n' "$key" "$value" >> .env; fi
}

data_dir="$(envget DATA_DIR)"; data_dir="${data_dir:-./data}"
topics="$(envget TELEGRAM_NTFY_TOPIC)"; topics="${topics:-homeserver}"
tg_dir="$data_dir/telegram"
[ -d "$data_dir" ] || die "cartella dati '$data_dir' inesistente (lancia prima ./src/scripts/start.sh)"
umask 077
mkdir -p "$tg_dir/state"
chmod 700 "$tg_dir"

# --- 1. token del bot ------------------------------------------------------------------------------------------
tokfile="$tg_dir/telegram_bot_token"
if [ "$redo" -eq 0 ] && [ -s "$tokfile" ]; then
  TOKEN="$(tr -d '[:space:]' < "$tokfile")"
  echo "Token del bot gia' salvato: lo riuso (--da-capo per cambiarlo)."
else
  echo "Incolla il token del bot (quello di @BotFather, tipo 123456789:AA...). Non viene mostrato."
  read -rsp "Token: " TOKEN; echo
  TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
fi
[[ "$TOKEN" =~ ^[0-9]{6,}:[A-Za-z0-9_-]{30,}$ ]] || die "non sembra un token di BotFather (formato 123456789:AAAA...)"

# Chiamata all'API: l'indirizzo col token passa da stdin (curl -K -), mai dalla riga di comando.
tg() {
  local method="$1"; shift
  printf 'url = "https://api.telegram.org/bot%s/%s"\n' "$TOKEN" "$method" | curl -sS --max-time 25 -K - "$@"
}
jget() { python3 -I -c 'import json,sys
try: d=json.load(sys.stdin)
except ValueError: sys.exit(2)
for k in sys.argv[1].split("."):
    d=d.get(k) if isinstance(d,dict) else None
print("" if d is None else d)' "$1"; }

me="$(tg getMe || true)"
[ "$(printf '%s' "$me" | jget ok)" = "True" ] || die "Telegram ha rifiutato il token (o non e' raggiungibile): $(printf '%s' "$me" | jget description)"
botname="$(printf '%s' "$me" | jget result.username)"
printf '%s' "$TOKEN" > "$tokfile"; chmod 600 "$tokfile"
echo "Bot riconosciuto: @$botname"

# --- 2. chat ID -------------------------------------------------------------------------------------------------
chat="$(envget TELEGRAM_CHAT_ID)"
if [ "$redo" -eq 1 ] || [ -z "$chat" ]; then
  upd="$(tg getUpdates || true)"
  [ "$(printf '%s' "$upd" | jget ok)" = "True" ] || die "getUpdates non riuscito: $(printf '%s' "$upd" | jget description)"
  # chat private da cui il bot ha ricevuto messaggi: "id<TAB>nome"
  mapfile -t found < <(printf '%s' "$upd" | python3 -I -c '
import json, sys
seen = {}
for u in json.load(sys.stdin).get("result", []):
    m = u.get("message") or u.get("edited_message") or {}
    c = m.get("chat") or {}
    if c.get("type") == "private" and c.get("id") is not None:
        who = " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x)
        if c.get("username"):
            who += " (@%s)" % c["username"]
        seen[c["id"]] = who or "(senza nome)"
for i, w in seen.items():
    print("%s\t%s" % (i, w.replace("\t", " ").replace("\n", " ")))')
  [ "${#found[@]}" -gt 0 ] || die "il bot non ha messaggi: apri @$botname su Telegram, scrivigli /start e rilancia questo script."
  pick=0
  if [ "${#found[@]}" -gt 1 ]; then
    echo "Piu' persone hanno scritto al bot (il bot e' pubblico: chiunque lo trovi puo' farlo):"
    for i in "${!found[@]}"; do printf '  %d) %s\n' "$((i + 1))" "${found[$i]#*$'\t'}"; done
    read -rp "Quale sei tu? [1-${#found[@]}]: " n
    [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "${#found[@]}" ] || die "scelta non valida"
    pick=$((n - 1))
  fi
  chat="${found[$pick]%%$'\t'*}"
  who="${found[$pick]#*$'\t'}"
  # senza conferma, un estraneo che ha scritto al bot prima di te riceverebbe le tue notifiche
  read -rp "Invio le notifiche a: $who. E' il tuo account? [s/N] " ok
  [[ "$ok" =~ ^[sSyY]$ ]] || die "annullato: nessun chat ID salvato"
fi
[[ "$chat" =~ ^-?[0-9]+$ ]] || die "TELEGRAM_CHAT_ID non numerico: '$chat'"
res="$(tg sendMessage --data-urlencode "chat_id=$chat" --data-urlencode "text=Ponte HomeServer: collegamento riuscito. Da ora qui arrivano le notifiche di ntfy." || true)"
[ "$(printf '%s' "$res" | jget ok)" = "True" ] || die "non riesco a scrivere al chat $chat: $(printf '%s' "$res" | jget description)"
envset TELEGRAM_CHAT_ID "$chat"
echo "Messaggio di prova inviato: controlla Telegram."

# --- 3. utente ntfy in sola lettura -------------------------------------------------------------------------
ntfyfile="$tg_dir/ntfy_token"
if [ "$redo" -eq 0 ] && [ -s "$ntfyfile" ]; then
  echo "Token ntfy gia' salvato: lo riuso (--da-capo per rigenerarlo)."
else
  [ "$(docker inspect -f '{{.State.Running}}' ntfy 2>/dev/null || true)" = "true" ] || die "ntfy non e' in funzione: docker compose up -d ntfy"
  nt() { docker compose exec -T ntfy ntfy "$@"; }
  nt user del telegram >/dev/null 2>&1 || true   # un utente rimasto da un tentativo precedente (e il suo vecchio token)
  # la password serve solo a creare l'utente: si usa il token, quindi la si butta. Passa da stdin, non dalla riga di comando.
  openssl rand -hex 24 | docker compose exec -T ntfy sh -c 'NTFY_PASSWORD="$(cat)" exec ntfy user add --role=user telegram' >/dev/null \
    || die "non riesco a creare l'utente ntfy 'telegram'"
  IFS=',' read -ra tl <<< "$topics"
  for t in "${tl[@]}"; do nt access telegram "$t" read-only >/dev/null || die "permesso di lettura su '$t' non assegnato"; done
  out="$(nt token add telegram)" || die "non riesco a creare il token ntfy"
  ntoken="$(printf '%s' "$out" | grep -oE 'tk_[A-Za-z0-9]+' | head -n1 || true)"
  [ -n "$ntoken" ] || die "token ntfy non trovato nell'output di 'ntfy token add': $out"
  printf '%s' "$ntoken" > "$ntfyfile"; chmod 600 "$ntfyfile"
  echo "Utente ntfy 'telegram' creato: puo' solo leggere ($topics)."
fi

# --- 4. avvio ---------------------------------------------------------------------------------------------------
if ! docker compose --profile telegram up -d --force-recreate --wait --wait-timeout 120 ntfy-telegram; then
  die "Il ponte non risulta connesso a ntfy. Guarda: docker compose logs ntfy-telegram"
fi
echo "Ponte connesso a ntfy."
echo "Prova: invia una notifica di test da Uptime Kuma verso l'argomento $topics e controlla il messaggio su Telegram."
