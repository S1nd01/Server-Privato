"""Catalogo dei servizi Docker gestiti dal pannello.

Ogni servizio e' un gruppo di container (nomi definiti in compose.yaml).
Restic non e' qui: non e' un servizio sempre attivo ma un lavoro a richiesta (backup.py).

Campi opzionali:
  path        percorso aggiunto al link "Apri" (es. /admin)
  allow_stop  False = il pannello non lo ferma ne' lo riavvia (Tailscale: fermandolo perderesti l'accesso)
  ts_only     True = si apre solo dall'indirizzo Tailscale (https://<nome>.ts.net:porta): niente link "Apri" da localhost
"""

SERVICES = {
    "immich": {
        "name": "Immich",
        "description": "Backup e galleria foto",
        "containers": [
            "immich_server",
            "immich_redis",
            "immich_postgres",
        ],
        "scheme": "http",
        "url_port": 2283,
    },
    # Il container piu' pesante di Immich ha un interruttore a parte: serve solo per riconoscere volti e oggetti
    # nelle foto nuove (docs/immich.md). Da spento Immich funziona, ma quei lavori restano in coda.
    "immich-ml": {
        "name": "Immich, riconoscimento",
        "description": "Volti, oggetti e ricerca per contenuto. Occupa molta RAM: spegnilo quando non carichi foto",
        "containers": ["immich_machine_learning"],
        "scheme": "http",
        "url_port": None,
    },
    "jellyfin": {
        "name": "Jellyfin",
        "description": "Film, serie e musica in streaming",
        "containers": ["jellyfin"],
        "scheme": "http",
        "url_port": 8096,
    },
    "seerr": {
        "name": "Seerr",
        "description": "Richieste di film e serie (con JellyBridge in Jellyfin)",
        "containers": ["seerr"],
        "scheme": "http",
        "url_port": 5055,
    },
    "download": {
        "name": "Download automatici",
        "description": "Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr e FlareSolverr: scaricano ciò che chiedi in Seerr",
        "containers": ["qbittorrent", "prowlarr", "radarr", "sonarr", "bazarr", "flaresolverr"],
        "scheme": "http",
        "url_port": None,  # piu' interfacce, nessun link unico: porte in docs/seerr.md e docs/bazarr.md
    },
    "vaultwarden": {
        "name": "Vaultwarden",
        "description": "Password manager compatibile con Bitwarden",
        "containers": ["vaultwarden"],
        "scheme": "https",
        "url_port": 8443,
        "ts_only": True,
    },
    "pihole": {
        "name": "Pi-hole",
        "description": "Blocca pubblicità e tracker su tutta la rete",
        "containers": ["pihole"],
        "scheme": "http",
        "url_port": 8053,
        "path": "/admin",
    },
    "uptime-kuma": {
        "name": "Uptime Kuma",
        "description": "Controlla che i servizi rispondano e ti avvisa se si fermano",
        "containers": ["uptime-kuma"],
        "scheme": "http",
        "url_port": 3001,
    },
    "ntfy": {
        "name": "ntfy",
        "description": "Notifiche push sul telefono (usate da Uptime Kuma, Radarr e Sonarr)",
        "containers": ["ntfy"],
        "scheme": "http",
        "url_port": 2586,
    },
    "portainer": {
        "name": "Portainer",
        "description": "Gestione grafica di Docker: container, log, volumi e aggiornamenti",
        "containers": ["portainer"],
        "scheme": "https",
        "url_port": 9443,
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
