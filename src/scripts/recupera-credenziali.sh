#!/usr/bin/env bash
# Recupero credenziali e password dei servizi. Si lancia dal terminale del SERVER, col tuo utente (mai con sudo).
# Chi arriva a questo terminale e' gia' il proprietario della macchina: per questo il recupero non passa mai da internet
# e il pannello web non puo' rivelare ne' reimpostare nulla (mostra solo cosa fare, vedi la sezione Accessi).
#
#   ./src/scripts/recupera-credenziali.sh                 elenco dei comandi
#   ./src/scripts/recupera-credenziali.sh mostra NOME     mostra una password salvata in chiaro (pihole, immich-db, restic, backup-vaultwarden)
#   ./src/scripts/recupera-credenziali.sh pannello        nuovo token del pannello
#   ./src/scripts/recupera-credenziali.sh pihole          nuova password di Pi-hole
#   ./src/scripts/recupera-credenziali.sh immich          nuova password dell'amministratore di Immich
#   ./src/scripts/recupera-credenziali.sh vaultwarden-admin   nuovo token per la pagina /admin di Vaultwarden
#   ./src/scripts/recupera-credenziali.sh arr radarr|sonarr|prowlarr   toglie la password (la reimposti dal browser)
#   ./src/scripts/recupera-credenziali.sh qbittorrent     nuova password temporanea di qBittorrent
#   ./src/scripts/recupera-credenziali.sh ntfy [UTENTE]   cambia la password di un utente ntfy (senza nome: elenca gli utenti)
#   ./src/scripts/recupera-credenziali.sh kuma            nuova password di Uptime Kuma
#   ./src/scripts/recupera-credenziali.sh portainer       nuova password di Portainer
#   ./src/scripts/recupera-credenziali.sh beszel EMAIL    nuova password di Beszel per quell'utente
# HS_SI=1 salta le conferme (per gli script). Le password nuove si mostrano UNA volta: salvale nel password manager.
set -euo pipefail
cd "$(dirname "$0")/../.."
umask 077

die() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" != 0 ] || die "Non lanciarlo come root/sudo: i file dei dati devono restare tuoi."
[ -f .env ] || die ".env non trovato: sei nella cartella del progetto? (./src/scripts/sync-env.sh lo crea)"
command -v docker >/dev/null 2>&1 || die "Docker non e' installato o non e' nel PATH."

get() { { grep -E "^$1=" .env || true; } | head -n1 | cut -d= -f2-; }
set_kv() {
  local key="$1" value="$2" escaped
  escaped="${value//\\/\\\\}"; escaped="${escaped//&/\\&}"; escaped="${escaped//|/\\|}"
  if grep -q "^$key=" .env; then sed -i "s|^$key=.*|$key=$escaped|" .env; else printf '%s=%s\n' "$key" "$value" >> .env; fi
}
data_dir="$(get DATA_DIR)"
[ -n "$data_dir" ] || die "DATA_DIR vuoto nel .env: lancia ./src/scripts/sync-env.sh"

confirm() {   # $1 = cosa sta per succedere
  [ "${HS_SI:-}" = 1 ] && return 0
  [ -t 0 ] || die "Serve un terminale per confermare (oppure HS_SI=1)."
  printf '%s [s/N] ' "$1" >&2
  local a=""; read -r a || true
  case "$a" in [sSyY]*) return 0 ;; *) echo "Annullato." >&2; exit 1 ;; esac
}
running() { docker compose ps --status running --services 2>/dev/null | grep -qx "$1"; }
need() { running "$1" || die "$1 non e' acceso: docker compose up -d $1"; }
newpass() { openssl rand -hex 12; }
show_once() {   # $1 = etichetta, $2 = valore
  printf '\n================================================================\n'
  printf ' %s\n\n   %s\n\n Copialo ORA nel password manager: non viene mostrato di nuovo.\n' "$1" "$2"
  printf '================================================================\n'
}
stamp() { date +%Y%m%d-%H%M%S; }

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; }

cmd="${1:-}"; [ $# -gt 0 ] && shift || true
case "$cmd" in
  "" | -h | --help | aiuto) usage ;;

  mostra)
    what="${1:-}"
    case "$what" in
      pihole)  label="Password di Pi-hole";                         value="$(get PIHOLE_PASSWORD)" ;;
      immich-db) label="Password del database di Immich (non e' quella con cui entri in Immich)"; value="$(get IMMICH_DB_PASSWORD)" ;;
      restic)  f="$(get RESTIC_PASSWORD_FILE)";        label="Passphrase dell'archivio Restic ($f)";               value="$( [ -r "$f" ] && cat "$f" || true )" ;;
      backup-vaultwarden) f="$(get BACKUP_PASSPHRASE_FILE)"; label="Passphrase dei backup di Vaultwarden ($f)"; value="$( [ -r "$f" ] && cat "$f" || true )" ;;
      *) die "Uso: mostra pihole | immich-db | restic | backup-vaultwarden" ;;
    esac
    [ -n "$value" ] || die "Non trovo nulla da mostrare per '$what' (valore vuoto o file mancante)."
    confirm "Mostro '$what' in chiaro su questo schermo?"
    printf '\n%s:\n  %s\n\n' "$label" "$value"
    ;;

  pannello)
    confirm "Genero un nuovo token per il pannello? Il vecchio smette di funzionare su tutti i dispositivi."
    ./src/scripts/gen-api-token.sh
    docker compose up -d backend
    echo "Backend riavviato con il nuovo token. Nei dispositivi gia' collegati il pannello chiedera' di inserirlo di nuovo."
    ;;

  pihole)
    confirm "Imposto una nuova password per Pi-hole? Il container si ricrea (il DNS si interrompe per qualche secondo)."
    pw="$(newpass)"
    set_kv PIHOLE_PASSWORD "$pw"
    docker compose up -d pihole
    show_once "Nuova password di Pi-hole (salvata anche nel .env)" "$pw"
    ;;

  immich)
    need immich-server
    echo "Immich genera una password casuale per l'amministratore e la mostra qui sotto."
    confirm "Reimposto la password dell'amministratore di Immich?"
    docker compose exec immich-server immich-admin reset-admin-password
    ;;

  vaultwarden-admin)
    echo "Genero l'hash per ADMIN_TOKEN (la pagina /admin di Vaultwarden). Ti chiede la password che vuoi usare."
    echo "NON apre il tuo vault: la master password non si puo' recuperare (docs/credenziali.md)."
    confirm "Procedo?"
    docker run --rm -it vaultwarden/server /vaultwarden hash
    cat <<'EOF'

Copia la riga ADMIN_TOKEN='...' che compare qui sopra nel .env (sostituendo quella vecchia, con gli apici singoli),
poi:  docker compose up -d vaultwarden
EOF
    ;;

  arr)
    app="${1:-}"
    case "$app" in radarr | sonarr | prowlarr) ;; *) die "Uso: arr radarr | sonarr | prowlarr" ;; esac
    cfg="$data_dir/$app/config/config.xml"
    [ -f "$cfg" ] || die "Non trovo $cfg"
    grep -q '<AuthenticationMethod>' "$cfg" || die "$cfg non ha <AuthenticationMethod>: la password si toglie dal database (docs/credenziali.md)."
    confirm "Tolgo la richiesta di password a ${app^} e lo riavvio? (copia del file di configurazione salvata accanto, con la chiave API)"
    docker compose stop "$app"
    cp -p "$cfg" "$cfg.bak-$(stamp)"
    sed -i 's|<AuthenticationMethod>[^<]*</AuthenticationMethod>|<AuthenticationMethod>None</AuthenticationMethod>|' "$cfg"
    sed -i 's|<AuthenticationRequired>[^<]*</AuthenticationRequired>|<AuthenticationRequired>DisabledForLocalAddresses</AuthenticationRequired>|' "$cfg"
    docker compose up -d "$app"
    cat <<EOF

${app^} ora si apre senza password (anche da Tailscale: fallo SUBITO).
Aprilo, Impostazioni, Generale, Sicurezza: Autenticazione "Moduli" (o Basic), Obbligatoria, utente e password nuovi, Salva.
La copia della vecchia configurazione e' in $cfg.bak-*: cancellala quando hai finito.
EOF
    ;;

  qbittorrent)
    conf="$data_dir/qbittorrent/config/qBittorrent/qBittorrent.conf"
    [ -f "$conf" ] || die "Non trovo $conf"
    confirm "Tolgo la password salvata di qBittorrent e lo riavvio? Ne verra' generata una temporanea."
    docker compose stop qbittorrent
    cp -p "$conf" "$conf.bak-$(stamp)"
    sed -i '/^WebUI\\Password_PBKDF2=/d' "$conf"
    docker compose up -d qbittorrent
    sleep 10
    echo "Password temporanea (dal log):"
    docker compose logs --no-log-prefix --tail 80 qbittorrent | grep -i "password" || echo "  (non la trovo ancora: docker compose logs qbittorrent | grep -i password)"
    echo "Entra con utente admin e cambiala in Strumenti, Opzioni, WebUI. Copia della vecchia configurazione: $conf.bak-*"
    ;;

  ntfy)
    need ntfy
    user="${1:-}"
    if [ -z "$user" ]; then docker compose exec ntfy ntfy user list; echo "Per cambiare una password: $0 ntfy NOME"; exit 0; fi
    docker compose exec ntfy ntfy user change-pass "$user"
    ;;

  kuma)
    need uptime-kuma
    docker compose exec uptime-kuma npm run reset-password
    ;;

  portainer)
    confirm "Fermo Portainer, reimposto la password dell'amministratore e lo riavvio?"
    docker compose stop portainer
    docker run --rm -v "$data_dir/portainer:/data" portainer/helper-reset-password
    docker compose up -d portainer
    echo "Entra con la password mostrata sopra (utente admin) e cambiala subito."
    ;;

  beszel)
    need beszel
    email="${1:-}"
    [ -n "$email" ] || die "Uso: beszel EMAIL"
    printf 'Nuova password per %s: ' "$email" >&2
    pw=""; read -rs pw || true; printf '\n' >&2
    [ "${#pw}" -ge 8 ] || die "Almeno 8 caratteri."
    docker compose exec -T beszel /beszel superuser upsert "$email" "$pw"
    ;;

  *) die "Comando sconosciuto: $cmd (prova senza argomenti per l'elenco)" ;;
esac
