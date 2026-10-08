"""Catalogo dei servizi Docker gestiti dal pannello.

Ogni servizio e' un gruppo di container (nomi definiti in compose.yaml).
SteamCMD non e' qui: non e' un servizio sempre attivo ma un download a richiesta (vedi steam.py).
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
    "vaultwarden": {
        "name": "Vaultwarden",
        "description": "Password manager self-hosted (dietro Caddy, solo HTTPS)",
        "containers": ["vaultwarden", "caddy"],
        "scheme": "https",
        "url_port": 8443,
    },
    "wireguard": {
        "name": "WireGuard",
        "description": "VPN per raggiungere il server da fuori casa",
        "containers": ["wireguard"],
        "scheme": "http",
        "url_port": None,
    },
}
