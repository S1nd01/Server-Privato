"""Catalogo dei servizi Docker gestiti dal pannello.

Ogni servizio e' un gruppo di container (nomi definiti in compose.yaml).
Restic non e' qui: non e' un servizio sempre attivo ma un lavoro a richiesta (backup.py).

Campi opzionali:
  path        percorso aggiunto al link "Apri" (es. /admin)
  allow_stop  False = il pannello non lo ferma ne' lo riavvia (Tailscale: fermandolo perderesti l'accesso)
  ts_only     True = si apre solo dall'indirizzo Tailscale (https://<nome>.ts.net:porta): niente link "Apri" da localhost
  group       "utility" = la scheda sta nel blocco Utility del pannello (manutenzione, compressione...), non tra i servizi
  compose_profile  profilo di compose.yaml che lo crea (non parte con un `up` normale): il pannello lo scrive nel suggerimento
              quando il container non esiste (Portainer: --profile admin-tools)
  optional    container del gruppo che puo' non esistere (lo crea un file compose opzionale, per esempio compose.vpn.yml): se manca
              il pannello lo ignora, invece di segnare il gruppo "parziale" o rifiutare l'avvio
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
    # Plex (docs/plex.md): opzionale, sulla stessa libreria di Jellyfin; di solito spento
    "plex": {
        "name": "Plex",
        "description": "Film e serie in streaming (alternativa o complemento a Jellyfin, stessa cartella media). Richiede un account plex.tv",
        "containers": ["plex"],
        "scheme": "http",
        "url_port": 32400,
        "compose_profile": "plex",   # su richiesta: docker compose --profile plex up -d plex
    },
    # RomM (docs/romm.md): libreria di ROM con il suo database MariaDB; di solito spento. Il database PRIMA di RomM.
    "romm": {
        "name": "RomM (ROM)",
        "description": "Libreria delle ROM dei tuoi giochi, con copertine e gioco dal browser. Include il suo database",
        "containers": ["romm-db", "romm"],
        "scheme": "https",
        "url_port": 8085,
        "ts_only": True,
        "compose_profile": "romm",   # su richiesta: docker compose --profile romm up -d romm
    },
    "seerr": {
        "name": "Seerr",
        "description": "Richieste di film e serie (con JellyBridge in Jellyfin)",
        "containers": ["seerr"],
        "scheme": "http",
        "url_port": 5055,
    },
    # Pulizia della libreria: collezioni in Jellyfin con ciò che non guardi piu' (docs/maintainerr.md)
    "maintainerr": {
        "name": "Maintainerr",
        "description": "Propone cosa togliere dalla libreria (film e serie non guardati) e cancella solo dopo i giorni che scegli tu",
        "containers": ["maintainerr"],
        "scheme": "http",
        "url_port": 6246,
    },
    "download": {
        "name": "Download automatici",
        "description": "Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr, FlareSolverr e Recyclarr: scaricano ciò che chiedi in Seerr. Con la VPN attiva, anche gluetun",
        # gluetun (VPN di qBittorrent, compose.vpn.yml, docs/vpn.md) PRIMA di qBittorrent: ne condivide la rete, quindi deve partire per primo.
        # Se la VPN non e' attiva il container non esiste e il pannello lo ignora (optional).
        "containers": ["gluetun", "qbittorrent", "prowlarr", "radarr", "sonarr", "bazarr", "flaresolverr", "recyclarr"],
        "optional": ["gluetun"],
        "scheme": "http",
        "url_port": None,  # piu' interfacce, nessun link unico: porte in docs/seerr.md e docs/bazarr.md
    },
    # Scambio di file tra i dispositivi di casa (docs/scambio-file.md): condivide solo la cartella data/scambio
    "scambio": {
        "name": "Scambio file",
        "description": "Copyparty: carica e scarica file da telefono e PC (web e WebDAV). Condivide solo la cartella «scambio»",
        "containers": ["copyparty"],
        "scheme": "http",
        "url_port": 3923,
    },
    # Sincronizzazione tra dispositivi (docs/syncthing.md)
    "syncthing": {
        "name": "Syncthing",
        "description": "Sincronizza cartelle tra i tuoi dispositivi, cifrato e senza server centrale (solo via Tailscale)",
        "containers": ["syncthing"],
        "scheme": "http",
        "url_port": 8384,
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
        "description": "Blocca pubblicità e tracker su tutta la rete (con Unbound come DNS ricorsivo)",
        "containers": ["pihole", "unbound"],   # Unbound e' il DNS ricorsivo dietro Pi-hole (docs/unbound.md): senza Pi-hole non serve
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
    # Storico delle risorse del server e dei container (docs/beszel.md): hub e agente hanno un solo interruttore
    "beszel": {
        "name": "Beszel",
        "description": "Storico di CPU, RAM, dischi, rete e container del server, con grafici e avvisi",
        "containers": ["beszel", "beszel-agent"],
        "scheme": "http",
        "url_port": 8090,
    },
    "portainer": {
        "name": "Portainer",
        "description": "Gestione grafica di Docker: container, log, volumi e aggiornamenti",
        "containers": ["portainer"],
        "scheme": "https",
        "url_port": 9443,
        "compose_profile": "admin-tools",   # su richiesta: docker compose --profile admin-tools up -d portainer
    },
    # ---- blocco Utility del pannello (group: "utility") ----
    "manutenzione": {
        "name": "Manutenzione",
        "description": "Diun avvisa quando escono nuove versioni delle immagini, Autoheal riavvia ciò che smette di rispondere",
        # I proxy del socket prima (si avviano per primi) e Diun/Autoheal dopo: senza proxy non si connettono (docs/security.md)
        "containers": ["docker-proxy-ro", "docker-proxy-rw", "diun", "autoheal"],
        "scheme": "http",
        "url_port": None,  # nessuna interfaccia: le notifiche arrivano su ntfy (docs/manutenzione.md)
        "group": "utility",
    },
    "telegram": {
        "name": "Notifiche Telegram",
        "description": "Inoltra le notifiche di ntfy al tuo Telegram. Si attiva con ./src/scripts/telegram-setup.sh (docs/telegram.md)",
        "containers": ["ntfy-telegram"],
        "scheme": "http",
        "url_port": None,  # nessuna interfaccia ne' porta
        "group": "utility",
        "compose_profile": "telegram",   # su richiesta: lo crea telegram-setup.sh
    },
    "compressione": {
        "name": "Compressione video",
        "description": "Unmanic ricodifica film e serie in HEVC per liberare spazio. Pesa molto sulla CPU: accendilo solo quando serve",
        "containers": ["unmanic"],
        "scheme": "http",
        "url_port": 8888,
        "group": "utility",
    },
    # Convertitore di file (docs/convertx.md): su rete interna, senza porte sul computer; di solito spento
    "convertx": {
        "name": "Convertitore di file",
        "description": "ConvertX converte immagini, documenti, audio e video dal browser. Elabora file non fidati: accendilo solo quando serve",
        "containers": ["convertx"],
        "scheme": "https",
        "url_port": 3000,
        "ts_only": True,
        "group": "utility",
        "compose_profile": "convertx",   # su richiesta: docker compose --profile convertx up -d convertx
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


# Container la cui rete e' usata da altri (network_mode: "service:..."): in un gruppo partono per primi e si fermano per ultimi
# (il pannello li ordina da solo nelle modalita'; nei gruppi vale l'ordine dell'elenco "containers").
NETWORK_PROVIDERS = {"gluetun"}


# Modalita' del pannello: con un tocco accendono o spengono piu' gruppi di servizi (id di SERVICES).
#   action    "stop" = li spegne, "start" = li accende
#   services  gruppi toccati; tutti gli altri restano come sono
# La modalita' e' "attiva" se tutti i suoi gruppi (quelli creati) sono gia' nello stato che lei produce.
MODES = {
    "risparmio": {
        "name": "Risparmio",
        "description": "Spegne Immich (con il riconoscimento) e i download automatici",
        "action": "stop",
        "services": ["immich-ml", "immich", "download"],
    },
    "normale": {
        "name": "Normale",
        "description": "Riaccende Immich e i download automatici (il riconoscimento resta com'è)",
        "action": "start",
        "services": ["immich", "download"],
    },
}
