#!/usr/bin/env bash
# Installazione automatica DENTRO Ubuntu (WSL o Linux). Lo lancia setup-windows.bat, ma si puo' usare anche a mano:
#   bash install-linux.sh <cartella-con-il-progetto>
# Si puo' rilanciare quante volte vuoi: conserva le impostazioni del .env e i dati gia' presenti.
# Tutti i dati vengono salvati in data/ dentro il progetto: non serve modificare il .env a mano.
set -euo pipefail

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nERRORE: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || [ "${HS_ALLOW_ROOT:-0}" = "1" ] || die "Non lanciarlo come root: usa il tuo utente normale (serve per i permessi delle cartelle)."
SRC="${1:-}"
[ -n "$SRC" ] && [ -f "$SRC/compose.yaml" ] || die "Indica la cartella del progetto (quella con compose.yaml): bash install-linux.sh <cartella>"
SRC="$(cd "$SRC" && pwd)"
DEST="${HS_DEST:-$HOME/homeserver}"
SKIP_SYSTEM="${HS_SKIP_SYSTEM:-0}"   # solo per i test: salta apt, Docker e l'avvio dei container

# ---------------------------------------------------------------- 1. copia del progetto
say "1/6 Copio il progetto in $DEST"
# I container NON devono girare da una cartella di Windows (/mnt/c): e' lenta e rompe i permessi.
mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude='.env' --exclude='.git/' "$SRC"/ "$DEST"/
  else
    (cd "$SRC" && tar --exclude='./.env' --exclude='./.git' -cf - .) | (cd "$DEST" && tar -xf -)
  fi
fi
cd "$DEST"
# se i file arrivano da Windows possono avere i ritorni a capo di Windows: bash non li digerisce
sed -i 's/\r$//' src/scripts/*.sh .env.example 2>/dev/null || true
chmod +x src/scripts/*.sh

# ---------------------------------------------------------------- 2. programmi necessari
if [ "$SKIP_SYSTEM" != "1" ]; then
  say "2/6 Installo Docker e gli strumenti (ti chiedo la password di Ubuntu)"
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-v2 openssl unzip rsync curl dnsutils gnupg cron
  if [ -d /run/systemd/system ]; then
    sudo systemctl enable --now docker
  else
    sudo service docker start || true
    # senza systemd Docker non riparte da solo dopo un riavvio: lo attivo in WSL
    if ! grep -qs '^systemd *= *true' /etc/wsl.conf 2>/dev/null; then
      printf '\n[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf >/dev/null
      echo "Ho attivato systemd in /etc/wsl.conf: avra' effetto al prossimo riavvio di WSL."
    fi
  fi
  sudo usermod -aG docker "$USER" || true
  for _ in $(seq 1 20); do sudo docker info >/dev/null 2>&1 && break; sleep 1; done
  sudo docker info >/dev/null 2>&1 || die "Docker non parte. Prova: sudo service docker start, poi rilancia."
  sudo docker compose version >/dev/null 2>&1 || die "Manca il plugin 'docker compose'. Prova: sudo apt install docker-compose-v2"
  DC="sudo docker compose"   # per questa volta; dal prossimo accesso basta 'docker compose'
else
  say "2/6 (test) salto l'installazione dei programmi"
  DC="echo [test] docker compose"
fi

# ---------------------------------------------------------------- 3. .env, percorsi e cartelle
say "3/6 Preparo il .env e le cartelle dati del progetto"
# crea il .env se manca e le cartelle sotto data/ col tuo utente
./src/scripts/sync-env.sh

# ---------------------------------------------------------------- 4. Tailscale
say "4/6 Tailscale"
if ! grep -qE '^TS_AUTHKEY=.+' .env; then
  echo
  echo "Tailscale (accesso dal telefono). Se non l'hai ancora, crea la chiave qui:"
  echo "  login.tailscale.com -> Settings -> Keys -> Generate auth key"
  echo "(e prima in DNS attiva MagicDNS e HTTPS Certificates)."
  printf "Incolla la chiave (tskey-auth-...) oppure premi Invio per saltare: "
  read -r KEY || KEY=""
  if [ -n "$KEY" ]; then
    if [[ "$KEY" =~ ^tskey-[A-Za-z0-9_-]+$ ]]; then
      sed -i "s/^TS_AUTHKEY=.*/TS_AUTHKEY=$KEY/" .env
    else
      echo "La chiave non ha il formato giusto: salto. Potrai metterla dopo nel .env."
    fi
  fi
fi

# ---------------------------------------------------------------- 5. token del pannello
say "5/6 Token del pannello"
if grep -qE '^API_TOKEN_HASH=sha256:[0-9a-f]{64}$' .env; then
  echo "Token gia' impostato: lo lascio."
else
  ./src/scripts/gen-api-token.sh
  echo
  printf "Hai copiato il token? Premi Invio per continuare "
  read -r _ || true
fi

# ---------------------------------------------------------------- 6. avvio
say "6/6 Avvio i servizi (la prima volta scarica alcuni GB: puo' volerci un quarto d'ora)"
$DC config -q || die "Il file compose.yaml non e' valido con questo .env."
$DC up -d --build --remove-orphans
$DC ps

BACKUP_NOTE=""
if grep -qE '^RESTIC_REPO_DIR=.+' .env; then
  BACKUP_NOTE="
Backup: nel pannello, sezione Backup, premi 'Prepara l'archivio' (una volta sola).
Le passphrase dei backup sono in ~/.restic-pass e ~/.vw-backup-pass: copiale FUORI dal server."
fi

cat <<MSG

Fatto. Apri nel browser di Windows:
  Pannello   http://localhost:8088
  Immich     http://localhost:2283
  Jellyfin   http://localhost:8096
  Seerr      http://localhost:5055   (con Radarr 7878, Sonarr 8989, Prowlarr 9696, qBittorrent 8080: docs/seerr.md)
  Pi-hole    http://localhost:8053/admin
  Vaultwarden http://localhost:8222   (da Tailscale in HTTPS sulla porta 8443: docs/vaultwarden.md)
  Portainer  https://localhost:9443   (certificato autofirmato: docs/portainer.md)

Il progetto e' in: $DEST
Dati dei servizi: $(grep -E '^DATA_DIR=' .env | cut -d= -f2-)
$BACKUP_NOTE
Prossimo passo (telefono): docs/tailscale.md
MSG
