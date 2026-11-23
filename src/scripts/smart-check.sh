#!/usr/bin/env bash
# Controlla lo stato di salute dei dischi (SMART) e ti avvisa su ntfy (docs/smart.md).
#
#   ./src/scripts/smart-check.sh               controlla e, se c'e' un problema, manda un avviso su ntfy
#   ./src/scripts/smart-check.sh --stampa      controlla e stampa, senza mandare nulla
#   ./src/scripts/smart-check.sh --test        manda un avviso di prova (per verificare ntfy)
#   ./src/scripts/smart-check.sh --forza       come senza opzioni, ma avvisa anche se l'avviso identico e' gia' partito di recente
#
# Gira SUL COMPUTER (non in un container: un container con accesso ai dischi sarebbe un privilegio in piu' e un servizio in piu' in
# RAM). Serve smartmontools (sudo apt install smartmontools) e i permessi per leggere i dischi: da root, oppure col tuo utente con
# questa riga in /etc/sudoers.d/smartctl (visudo -f):   TUOUTENTE ALL=(root) NOPASSWD: /usr/sbin/smartctl
# Si pianifica con cron o con un timer di systemd (esempio in docs/smart.md); una volta al giorno basta.
#
# Cosa segnala:
#   - il disco dichiara di essere in guasto o con attributi sotto soglia (esito SMART non "PASSED");
#   - settori in attesa o non correggibili maggiori di zero (SATA: GUASTO); settori riallocati maggiori di zero (ATTENZIONE); avviso critico, spazio di riserva e usura (NVMe);
#   - errori nel registro del disco o nei test automatici;
#   - temperatura oltre SMART_TEMP_WARN (di serie 55 gradi).
# Uscita: 0 tutto bene, 1 c'e' qualcosa da guardare, 2 errore dello script (smartctl mancante, disco illeggibile...).
# Gli avvisi identici non si ripetono per 7 giorni (sennò ricevi lo stesso messaggio ogni mattina).
set -uo pipefail
cd "$(dirname "$0")/../.."

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 2; }
get() { { grep -E "^$1=" .env 2>/dev/null || true; } | head -n1 | cut -d= -f2-; }

mode=notify
case "${1:-}" in
  "") ;;
  --stampa) mode=print ;;
  --test) mode=test ;;
  --forza) mode=force ;;
  *) die "Opzione sconosciuta: $1 (vedi l'intestazione dello script)" ;;
esac

data_dir="$(get DATA_DIR)"
temp_warn="$(get SMART_TEMP_WARN)"; temp_warn="${temp_warn:-55}"
topic="$(get SMART_NTFY_TOPIC)"; topic="${topic:-homeserver}"
ntfy_url="${SMART_NTFY_URL:-http://127.0.0.1:2586}"           # la porta di ntfy e' pubblicata solo su 127.0.0.1
ntfy_user="$(get DIUN_NTFY_USER)"; ntfy_pass="$(get DIUN_NTFY_PASSWORD)"
devices="${SMART_DEVICES:-$(get SMART_DEVICES)}"   # la variabile d'ambiente ha la precedenza sul .env (utile per le prove)
[[ "$temp_warn" =~ ^[0-9]+$ ]] || die "SMART_TEMP_WARN deve essere un numero."

notify() {  # notify TITOLO MESSAGGIO PRIORITA TAG
  command -v curl >/dev/null || { echo "curl non trovato: non posso avvisare su ntfy." >&2; return 1; }
  local auth=()
  [ -n "$ntfy_user" ] && auth=(-u "$ntfy_user:$ntfy_pass")
  curl -fsS -m 15 "${auth[@]}" -H "Title: $1" -H "Priority: $3" -H "Tags: $4" -d "$2" "$ntfy_url/$topic" >/dev/null \
    || { echo "Non sono riuscito a mandare l'avviso a $ntfy_url/$topic (ntfy spento, utente o password sbagliati?)." >&2; return 1; }
}

if [ "$mode" = test ]; then
  notify "Prova controllo dischi" "Se leggi questo messaggio, gli avvisi SMART arrivano." 3 "white_check_mark" && echo "Avviso di prova inviato a $ntfy_url/$topic."
  exit $?
fi

smartctl_bin="${SMARTCTL_BIN:-smartctl}"
command -v "${smartctl_bin%% *}" >/dev/null || die "smartctl non trovato: sudo apt install smartmontools"
if [ -z "${SMARTCTL_BIN:-}" ] && [ "$(id -u)" != 0 ]; then smartctl_bin="sudo -n smartctl"; fi
# shellcheck disable=SC2086
sc() { $smartctl_bin "$@"; }

# elenco dei dischi: "dispositivo|opzioni" (le opzioni, per esempio -d sat, vengono da `smartctl --scan`)
list=()
if [ -n "$devices" ]; then
  for d in $devices; do [[ "$d" =~ ^/dev/[A-Za-z0-9/_-]+$ ]] || die "SMART_DEVICES: dispositivo non valido: $d"; list+=("$d|"); done
else
  while IFS= read -r line; do
    dev="$(awk '{print $1}' <<<"$line")"; opt="$(sed -n 's/^[^ ]* \(-d [A-Za-z0-9,+]*\).*/\1/p' <<<"$line")"
    [ -n "$dev" ] && list+=("$dev|$opt")
  done < <(sc --scan 2>/dev/null)
fi
[ "${#list[@]}" -gt 0 ] || die "Non trovo nessun disco da controllare (smartctl --scan e' vuoto: permessi? imposta SMART_DEVICES nel .env)."

problems=(); warnings=(); errors=(); checked=0
for item in "${list[@]}"; do
  dev="${item%%|*}"; opt="${item#*|}"
  # shellcheck disable=SC2086
  out="$(sc -H -A -i -l error $opt "$dev" 2>&1)"; code=$?
  # disco USB: se non si apre o il ponte non e' riconosciuto, riprova dichiarando il tipo SAT
  if [ -z "$opt" ] && { [ $((code & 2)) -ne 0 ] || grep -qi 'unknown usb bridge\|please specify device type' <<<"$out"; }; then
    out="$(sc -H -A -i -l error -d sat "$dev" 2>&1)"; code=$?
  fi
  if [ $((code & 3)) -ne 0 ] || ! grep -qiE 'overall-health|SMART Health Status|Critical Warning' <<<"$out"; then
    errors+=("$dev: non riesco a leggere i dati SMART (permessi, disco assente o ponte USB senza SMART)")
    continue
  fi
  checked=$((checked + 1))
  name="$(sed -n 's/^\(Device Model\|Model Number\|Product\):[[:space:]]*//p' <<<"$out" | head -n1)"; label="$dev${name:+ ($name)}"

  result="$(sed -n 's/^SMART overall-health self-assessment test result:[[:space:]]*//p; s/^SMART Health Status:[[:space:]]*//p' <<<"$out" | head -n1)"
  if [ -n "$result" ] && ! grep -qiE '^(PASSED|OK)$' <<<"$result"; then problems+=("$label: esito SMART \"$result\" (il disco dichiara un guasto)"); fi
  [ $((code & 8)) -ne 0 ] && problems+=("$label: SMART segnala un guasto imminente")
  [ $((code & 16)) -ne 0 ] && problems+=("$label: un attributo prefail e' sotto soglia")
  [ $((code & 32)) -ne 0 ] && warnings+=("$label: in passato un attributo e' andato sotto soglia")
  [ $((code & 64)) -ne 0 ] && warnings+=("$label: il registro errori del disco non e' vuoto")
  [ $((code & 128)) -ne 0 ] && warnings+=("$label: errori nei test automatici del disco")

  # attributi SATA: l'ultimo campo prima dell'eventuale testo e' il valore grezzo (colonna 10)
  while read -r id aname raw; do
    case "$id" in
      5) [ "${raw:-0}" -gt 0 ] 2>/dev/null && warnings+=("$label: $raw settori riallocati (il disco si sta consumando: tienilo d'occhio, e' grave se il numero cresce)") ;;
      197) [ "${raw:-0}" -gt 0 ] 2>/dev/null && problems+=("$label: $raw settori in attesa di riallocazione") ;;
      198) [ "${raw:-0}" -gt 0 ] 2>/dev/null && problems+=("$label: $raw settori non correggibili") ;;
    esac
  done < <(awk '$1 ~ /^[0-9]+$/ && NF >= 10 {print $1, $2, $10}' <<<"$out")
  temp="$(awk '$1 == 194 || $1 == 190 {print $10; exit}' <<<"$out")"
  [ -z "$temp" ] && temp="$(sed -n 's/^Temperature:[[:space:]]*\([0-9]*\).*/\1/p; s/^Current Drive Temperature:[[:space:]]*\([0-9]*\).*/\1/p' <<<"$out" | head -n1)"
  if [[ "$temp" =~ ^[0-9]+$ ]] && [ "$temp" -ge "$temp_warn" ]; then warnings+=("$label: temperatura $temp gradi (soglia $temp_warn)"); fi

  # NVMe
  crit="$(sed -n 's/^Critical Warning:[[:space:]]*\(0x[0-9a-fA-F]*\).*/\1/p' <<<"$out" | head -n1)"
  if [ -n "$crit" ] && [ $((crit)) -ne 0 ]; then problems+=("$label: avviso critico NVMe $crit"); fi
  used="$(sed -n 's/^Percentage Used:[[:space:]]*\([0-9]*\)%.*/\1/p' <<<"$out" | head -n1)"
  if [[ "$used" =~ ^[0-9]+$ ]] && [ "$used" -ge 90 ]; then warnings+=("$label: usura al ${used}%"); fi
  spare="$(sed -n 's/^Available Spare:[[:space:]]*\([0-9]*\)%.*/\1/p' <<<"$out" | head -n1)"
  spare_min="$(sed -n 's/^Available Spare Threshold:[[:space:]]*\([0-9]*\)%.*/\1/p' <<<"$out" | head -n1)"
  if [[ "$spare" =~ ^[0-9]+$ && "$spare_min" =~ ^[0-9]+$ ]] && [ "$spare" -le "$spare_min" ]; then problems+=("$label: spazio di riserva NVMe esaurito (${spare}%)"); fi
done

report=""
for m in "${problems[@]}"; do report+="GUASTO  $m"$'\n'; done
for m in "${warnings[@]}"; do report+="ATTENZIONE  $m"$'\n'; done
for m in "${errors[@]}"; do report+="ERRORE  $m"$'\n'; done
if [ -z "$report" ]; then echo "Dischi controllati: $checked. Nessun problema."; exit 0; fi
printf '%s' "$report"

[ "${#problems[@]}" -gt 0 ] && prio=5 tags="rotating_light,floppy_disk" title="Disco in pericolo" || prio=4 tags="warning,floppy_disk" title="Disco da controllare"
[ "${#problems[@]}" -eq 0 ] && [ "${#warnings[@]}" -eq 0 ] && { prio=3; tags="warning"; title="Controllo dischi non riuscito"; }

if [ "$mode" != print ]; then
  state="${data_dir:+$data_dir/panel/smart-state}"
  hash="$(printf '%s' "$report" | sha256sum | cut -d' ' -f1)"
  skip=0
  if [ "$mode" != force ] && [ -n "$state" ] && [ -f "$state" ]; then
    read -r old_hash old_ts < "$state" || true
    if [ "${old_hash:-}" = "$hash" ] && [ $(( $(date +%s) - ${old_ts:-0} )) -lt 604800 ]; then skip=1; fi
  fi
  if [ "$skip" = 1 ]; then
    echo "(Avviso identico gia' inviato negli ultimi 7 giorni: non lo ripeto. --forza per rimandarlo.)"
  elif notify "$title" "$report" "$prio" "$tags"; then
    [ -n "$state" ] && { mkdir -p "$(dirname "$state")" && printf '%s %s\n' "$hash" "$(date +%s)" > "$state"; }
    echo "Avviso inviato su ntfy."
  fi
fi
[ "${#problems[@]}" -gt 0 ] || [ "${#warnings[@]}" -gt 0 ] && exit 1
exit 2
