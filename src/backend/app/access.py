"""Sezione "Accessi" del pannello: dove stanno le credenziali dei servizi e come si recuperano.

Il pannello NON rivela e NON reimposta nessuna password: mostra solo lo stato di cio' che puo' controllare senza leggere
segreti (per esempio se il file della passphrase esiste) e il comando da lanciare dal terminale del server
(src/scripts/recupera-credenziali.sh). Motivo: se il pannello potesse mostrare le password, chi ruba il token del pannello
(che comanda Docker, cioe' e' gia' root sulla macchina) avrebbe in piu' anche tutte le credenziali. Il recupero passa dal
terminale del server, a cui arriva solo il proprietario.

Nessun valore segreto compare mai nella risposta: solo testi fissi e booleani.
"""

import os
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/access", tags=["accessi"])

RESTIC_PASS = Path("/data/restic-pass")   # montato da compose.yaml (vuoto/assente se il backup non e' configurato)
SCRIPT = "./src/scripts/recupera-credenziali.sh"

# recovery: "mostra"  = e' salvata in chiaro sul server, si puo' rileggere
#           "reimposta" = non si legge, ma si sostituisce con una nuova
#           "impossibile" = non esiste modo di recuperarla (per scelta di progetto)
CATALOG = [
    {
        "id": "pannello", "name": "Token del pannello",
        "where": "Nel .env c'è solo l'hash: il token non si può rileggere.",
        "recovery": "reimposta", "command": f"{SCRIPT} pannello",
        "note": "Genera un token nuovo e riavvia il backend. Il vecchio smette di funzionare su tutti i dispositivi.",
    },
    {
        "id": "pihole", "name": "Pi-hole",
        "where": "In chiaro nel .env (PIHOLE_PASSWORD).",
        "recovery": "mostra", "command": f"{SCRIPT} mostra pihole",
        "note": f"Per sceglierne una nuova: {SCRIPT} pihole",
    },
    {
        "id": "immich", "name": "Immich, amministratore",
        "where": "Nel database di Immich, non leggibile.",
        "recovery": "reimposta", "command": f"{SCRIPT} immich",
        "note": "Mostra una password casuale nuova per l'amministratore.",
    },
    {
        "id": "immich-db", "name": "Immich, database",
        "where": "In chiaro nel .env (IMMICH_DB_PASSWORD). Non è quella con cui entri in Immich.",
        "recovery": "mostra", "command": f"{SCRIPT} mostra immich-db",
        "note": "Se Immich scrive «password authentication failed»: ./src/scripts/fix-immich-db.sh",
    },
    {
        "id": "vaultwarden-master", "name": "Vaultwarden, password master",
        "where": "Non esiste sul server: il vault è cifrato con la tua password e il server non la conosce.",
        "recovery": "impossibile", "command": None,
        "note": "Se la perdi, il contenuto del vault non si può aprire. Da un'app già collegata puoi ancora esportarlo: fallo subito. Tieni una copia della password master e dei codici di recupero della 2FA fuori dal server.",
    },
    {
        "id": "vaultwarden-admin", "name": "Vaultwarden, pagina /admin",
        "where": "Nel .env come hash (ADMIN_TOKEN).",
        "recovery": "reimposta", "command": f"{SCRIPT} vaultwarden-admin",
        "note": "Non apre il vault: serve solo alla pagina di amministrazione.",
    },
    {
        "id": "jellyfin", "name": "Jellyfin e Seerr",
        "where": "Nel database di Jellyfin. Seerr usa gli stessi utenti.",
        "recovery": "reimposta", "command": None,
        "note": "Dalla pagina di accesso di Jellyfin scegli «Password dimenticata» (dalla rete di casa o dal server); un altro amministratore può reimpostarla anche da Dashboard, Utenti.",
    },
    {
        "id": "arr", "name": "Radarr, Sonarr, Prowlarr",
        "where": "Nel database di ciascuno, non leggibile.",
        "recovery": "reimposta", "command": f"{SCRIPT} arr radarr",
        "note": "Toglie la richiesta di password (vale per quell'app: ripeti con sonarr o prowlarr) e la reimposti subito dal browser.",
    },
    {
        "id": "qbittorrent", "name": "qBittorrent",
        "where": "Nella sua configurazione, come hash.",
        "recovery": "reimposta", "command": f"{SCRIPT} qbittorrent",
        "note": "Ne crea una temporanea che vedi nel log; la cambi subito nelle opzioni.",
    },
    {
        "id": "ntfy", "name": "ntfy",
        "where": "Nel database di ntfy, come hash.",
        "recovery": "reimposta", "command": f"{SCRIPT} ntfy IL_TUO_NOME",
        "note": f"Senza nome elenca gli utenti: {SCRIPT} ntfy",
    },
    {
        "id": "kuma", "name": "Uptime Kuma",
        "where": "Nel suo database, come hash.",
        "recovery": "reimposta", "command": f"{SCRIPT} kuma",
        "note": "Chiede il nome utente e la nuova password.",
    },
    {
        "id": "portainer", "name": "Portainer",
        "where": "Nel suo database, come hash.",
        "recovery": "reimposta", "command": f"{SCRIPT} portainer",
        "note": "Lo ferma per un attimo e mostra una password nuova.",
    },
    {
        "id": "beszel", "name": "Beszel",
        "where": "Nel suo database, come hash.",
        "recovery": "reimposta", "command": f"{SCRIPT} beszel LA_TUA_EMAIL",
        "note": "Imposta una nuova password per quell'utente.",
    },
    {
        "id": "restic", "name": "Backup Restic, passphrase",
        "where": "In un file sul server (RESTIC_PASSWORD_FILE, di solito ~/.restic-pass).",
        "recovery": "mostra", "command": f"{SCRIPT} mostra restic",
        "note": "Senza questa frase i backup non si aprono e non c'è modo di rigenerarla: tienila anche fuori dal server.",
    },
    {
        "id": "backup-vaultwarden", "name": "Backup Vaultwarden, passphrase",
        "where": "In un file sul server (BACKUP_PASSPHRASE_FILE, di solito ~/.vw-backup-pass).",
        "recovery": "mostra", "command": f"{SCRIPT} mostra backup-vaultwarden",
        "note": "Come sopra: persa questa, i backup cifrati di Vaultwarden sono illeggibili.",
    },
    {
        "id": "tailscale", "name": "Tailscale",
        "where": "Nessuna password sul server: si entra con il tuo account Tailscale.",
        "recovery": "impossibile", "command": None,
        "note": "Se il server non è collegato, la sezione Rete mostra il link di accesso. L'account si recupera dal sito di Tailscale.",
    },
]


def _checks() -> dict[str, bool]:
    """Cio' che si puo' sapere senza leggere segreti. Mancante = nessun controllo possibile."""
    out: dict[str, bool] = {}
    out["pannello"] = bool(os.environ.get("API_TOKEN_HASH", "").strip() or os.environ.get("API_TOKEN", ""))
    try:
        out["restic"] = RESTIC_PASS.stat().st_size >= 20   # lo stesso minimo che pretende sync-env.sh
    except OSError:
        out["restic"] = False
    return out


@router.get("")
def access():
    checks = _checks()
    return {
        "script": SCRIPT,
        "items": [{**item, "ok": checks.get(item["id"])} for item in CATALOG],
    }
