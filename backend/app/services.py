"""Catalogo dei servizi Docker gestiti dal pannello.

Ogni servizio e' un gruppo di container (nomi definiti in compose.yaml).
SteamCMD e Restic non sono qui: non sono servizi sempre attivi ma lavori a richiesta (steam.py, backup.py).

Campi opzionali:
  path        percorso aggiunto al link "Apri" (es. /admin)
  allow_stop  False = il pannello non lo ferma ne' lo riavvia (Tailscale: fermandolo perderesti l'accesso)
"""

SERVICES = {
    "immich": {
        "name": "Immich",
        "description": "Backup e galleria foto",
        "containers": [
            "immich_server",
            "immich_machine_learning",
            "immich_redis",
            "immich_postgres",
        ],
        "scheme": "http",
        "url_port": 2283,
    },
    "jellyfin": {
        "name": "Jellyfin",
        "description": "Film, serie e musica in streaming",
        "containers": ["jellyfin"],
        "scheme": "http",
        "url_port": 8096,
    },
    "vaultwarden": {
        "name": "Vaultwarden",
        "description": "Password manager compatibile con Bitwarden",
        "containers": ["vaultwarden", "caddy"],
        "scheme": "https",
        "url_port": 8443,
    },
    "pihole": {
        "name": "Pi-hole",
        "description": "Blocca pubblicità e tracker su tutta la rete",
        "containers": ["pihole"],
        "scheme": "http",
        "url_port": 8053,
        "path": "/admin",
    },
    "tailscale": {
        "name": "Tailscale",
        "description": "Accesso da fuori casa, in HTTPS",
        "containers": ["tailscale"],
        "scheme": "https",
        "url_port": None,
        "allow_stop": False,
    },
}
