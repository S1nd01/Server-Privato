"""Catalogo dei servizi gestiti dal pannello.

Ogni servizio e' un gruppo di container Docker (nomi definiti in compose.yaml).
Per aggiungere un servizio: aggiungi una voce qui e il relativo blocco nel compose.
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
        "url_port": 2283,
    },
    "vaultwarden": {
        "name": "Vaultwarden",
        "description": "Password manager self-hosted (compatibile Bitwarden)",
        "containers": ["vaultwarden"],
        "url_port": 8080,
    },
    "wireguard": {
        "name": "WireGuard",
        "description": "VPN / tunneling",
        "containers": ["wireguard"],
        "url_port": None,
    },
    "steam": {
        "name": "Steam",
        "description": "Download remoto giochi (linuxserver/steam)",
        "containers": ["steam"],
        "url_port": 3000,
    },
}
