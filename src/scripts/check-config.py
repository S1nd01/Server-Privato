#!/usr/bin/env python3
"""Controlla che le parti del progetto che devono restare allineate non divergano.

    python3 src/scripts/check-config.py

Legge compose.yaml (risolto da `docker compose config`: non serve Docker in funzione), tailscale/serve.json, il catalogo del
pannello (services.py), i backup (backup.py), l'elenco delle cartelle (sync-env.sh e stats.py) e docs/uptime-kuma.md.
Controlla anche compose.vpn.yml (la VPN di qBittorrent) unito al compose, con valori finti per le variabili obbligatorie: il file
opzionale non deve poter rompere la separazione tra le reti ne' aggiungere privilegi fuori da gluetun.
Non modifica nulla e non si collega a Docker: esce con 0 se e' tutto coerente, con 1 se trova problemi.

Le regole sull'esposizione e sulle reti sono la politica del progetto (docs/security.md, docs/reti.md): se cambiarle e' voluto,
aggiorna sia la documentazione sia l'elenco qui sotto.
"""
import ast
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARK = "/__hs_data__"           # al posto di DATA_DIR: riconosce i montaggi dei dati senza dipendere dal .env
fails: list[str] = []
counts: dict[str, int] = {}
section = ""


def begin(name):
    global section
    section = name
    counts[name] = 0


def check(cond, msg):
    counts[section] += 1
    if not cond:
        fails.append(f"[{section}] {msg}")


def literal(rel, name):
    tree = ast.parse((ROOT / rel).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    sys.exit(f"ERRORE: {name} non trovato in {rel}")


# ---------------------------------------------------------------- sorgenti
SERVICES = literal("src/backend/app/services.py", "SERVICES")
MODES = literal("src/backend/app/services.py", "MODES")
SOURCES = literal("src/backend/app/backup.py", "SOURCES")
EXCLUDES = literal("src/backend/app/backup.py", "EXCLUDES")
EXPECTED = literal("src/backend/app/stats.py", "EXPECTED_DIRS")
m = re.search(r"^SUBDIRS=\((.*?)\)", (ROOT / "src/scripts/sync-env.sh").read_text(), re.M)
if not m:
    sys.exit("ERRORE: SUBDIRS non trovato in src/scripts/sync-env.sh")
SUBDIRS = shlex.split(m.group(1))

env = dict(os.environ, DATA_DIR=MARK)
if not (ROOT / ".env").exists():   # senza .env servono almeno le variabili obbligatorie del compose
    env.update(TZ="UTC", PIHOLE_PASSWORD="x", IMMICH_DB_PASSWORD="x", ROMM_DB_PASSWORD="x", ROMM_DB_ROOT_PASSWORD="x", ROMM_AUTH_SECRET_KEY="x")
BASE_FILES = ["compose.yaml"] + (["compose.override.yml"] if (ROOT / "compose.override.yml").exists() else [])   # come li carica compose di serie


def compose_config(files, extra_env=None):
    """`docker compose config` con file espliciti: la riga COMPOSE_FILE del .env (VPN o Tailscale kernel attivi) non deve cambiare il controllo."""
    cmd = ["docker", "compose"] + [x for f in files for x in ("-f", f)] + ["--profile", "*", "config", "--format", "json"]
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=dict(env, **(extra_env or {})), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.exit(f"ERRORE: non riesco a eseguire docker compose: {exc}")
    if r.returncode != 0:
        sys.exit(f"ERRORE: docker compose config non riesce a leggere {' + '.join(files)}:\n" + r.stderr.strip()[:600])
    return json.loads(r.stdout)


cfg = compose_config(BASE_FILES)
VPN_FILE = ROOT / "compose.vpn.yml"
# valori finti: servono solo perche' compose.vpn.yml li pretende (:?) e non vanno MAI usati altrove
cfg_vpn = compose_config(BASE_FILES + ["compose.vpn.yml"], dict(
    WIREGUARD_ADDRESSES="10.64.0.2/32", WIREGUARD_PUBLIC_KEY="x", WIREGUARD_ENDPOINT_IP="192.0.2.1", WIREGUARD_KEY_FILE=str(Path(__file__).resolve()),
)) if VPN_FILE.exists() else None
svc, nets = cfg["services"], cfg.get("networks", {})
by_name = {(s.get("container_name") or n): n for n, s in svc.items()}


def key(x):
    return by_name.get(x) or (x if x in svc else None)


def nets_of(n):
    s = svc[n]
    nm = s.get("network_mode") or ""
    if nm.startswith("service:"):   # usa la rete di un altro container (qBittorrent dietro gluetun): vale quella
        return nets_of(nm.split(":", 1)[1])
    return {"<host>"} if nm == "host" else (set((s.get("networks") or {})) or {"default"})


def shares(a, b):
    ka, kb = key(a), key(b)
    return None if ka is None or kb is None else bool((nets_of(ka) & nets_of(kb)) - {"<host>"})


def no_host_path(volume):
    # Compose v2 puo' omettere false dalla configurazione normalizzata.
    return volume.get("type") == "bind" and not (volume.get("bind") or {}).get("create_host_path", False)


def under(path, bases):
    return any(path == b or path.startswith(b + "/") for b in bases)


# ---------------------------------------------------------------- 1. cartelle dei dati
begin("cartelle")
check(set(SUBDIRS) == set(EXPECTED), f"SUBDIRS (sync-env.sh) e EXPECTED_DIRS (stats.py) differiscono: solo nello script {sorted(set(SUBDIRS) - set(EXPECTED))}, solo in stats.py {sorted(set(EXPECTED) - set(SUBDIRS))}")
for s in SOURCES:
    check(under(s, SUBDIRS), f"backup.py: la fonte '{s}' non e' tra le cartelle create da sync-env.sh (SUBDIRS)")
for e in EXCLUDES:
    base = e.split("*")[0]
    check(under(base.rstrip("/"), SOURCES) or any(base.startswith(s) for s in SOURCES), f"backup.py: l'esclusione '{e}' non cade in nessuna fonte")
for n, s in svc.items():
    for v in s.get("volumes") or []:
        src = v.get("source", "")
        if v.get("type") == "bind" and (src == MARK or src.startswith(MARK + "/")):
            rel = src[len(MARK):].lstrip("/")
            check(rel == "" or under(rel, SUBDIRS) or any(d.startswith(rel + "/") for d in SUBDIRS),
                  f"{n}: monta '${{DATA_DIR}}/{rel}' che sync-env.sh non crea (Docker la creerebbe come root)")

# ---------------------------------------------------------------- 2. catalogo del pannello
begin("pannello")
catalog = {c for meta in SERVICES.values() for c in meta["containers"]}
compose_names = set(by_name)
optional = {c for meta in SERVICES.values() for c in meta.get("optional", [])}
vpn_names = {(s.get("container_name") or n) for n, s in (cfg_vpn or {"services": {}})["services"].items()}
check(not (catalog - compose_names - optional), f"services.py cita container che non esistono nel compose: {sorted(catalog - compose_names - optional)}")
check(optional <= vpn_names, f"services.py dichiara opzionali dei container che nemmeno compose.vpn.yml crea: {sorted(optional - vpn_names)}")
check(optional <= set(literal("src/backend/app/services.py", "NETWORK_PROVIDERS")), "i container opzionali con rete condivisa devono stare in NETWORK_PROVIDERS (services.py): il pannello li avvia per primi")
extra = compose_names - catalog - {"hs_frontend", "hs_backend", "restic", "rclone", "docker-gate"}
check(not extra, f"container del compose che nessun gruppo del pannello gestisce: {sorted(extra)}")
for mid, mode in MODES.items():
    for sid in mode["services"]:
        check(sid in SERVICES, f"la modalita' '{mid}' cita un gruppo inesistente: {sid}")
for sid, meta in SERVICES.items():
    prof = meta.get("compose_profile")
    for c in meta["containers"]:
        if c in by_name:
            profiles = svc[by_name[c]].get("profiles") or []
            check((prof in profiles) if prof else not profiles,
                  f"{sid}/{c}: profili del compose {profiles} non coerenti con compose_profile={prof!r} di services.py")

# ---------------------------------------------------------------- 3. Tailscale serve
begin("tailscale")
serve = json.loads((ROOT / "tailscale/serve.json").read_text().replace("${TS_CERT_DOMAIN}", "x.ts.net"))
port_up: dict[int, str] = {}
for host, h in serve["Web"].items():
    port = int(host.rsplit(":", 1)[1])
    pm = re.match(r"https?(?:\+insecure)?://([^:/]+)", h["Handlers"]["/"]["Proxy"])
    port_up[port] = pm.group(1)
    check(str(port) in serve["TCP"], f"serve.json: la porta {port} e' in Web ma non in TCP")
    check(key(pm.group(1)) is not None, f"serve.json: l'upstream '{pm.group(1)}' (porta {port}) non e' un servizio del compose")
    check(shares("tailscale", pm.group(1)) is True, f"serve.json: tailscale non raggiunge '{pm.group(1)}' (nessuna rete in comune)")
for port, h in serve["TCP"].items():
    if "TCPForward" in h:
        up = h["TCPForward"].rsplit(":", 1)[0]
        check(key(up) is not None and shares("tailscale", up) is True, f"serve.json: l'inoltro TCP della porta {port} punta a '{up}', che tailscale non raggiunge")
        check(not any(str(pp.get("target")) == port and pp.get("host_ip") for pp in (svc.get(key(up) or "", {}).get("ports") or [])), f"serve.json: la porta {port} di '{up}' non deve essere anche pubblicata sul computer (si passa solo da Tailscale)")
for sid, meta in SERVICES.items():
    p = meta.get("url_port")
    if p is None:
        continue
    check(p in port_up, f"services.py: '{sid}' dichiara la porta {p} che serve.json non pubblica")
    if p in port_up:
        check(port_up[p] in meta["containers"], f"services.py: '{sid}' porta {p} punta a '{port_up[p]}', che non e' uno dei suoi container")

# ---------------------------------------------------------------- 4. monitor di Uptime Kuma
begin("kuma")
doc = (ROOT / "docs/uptime-kuma.md").read_text()
for mon in sorted(set(re.findall(r"`http://([A-Za-z0-9_\-]+):\d+", doc))):
    check(key(mon) is not None, f"docs/uptime-kuma.md: il monitor '{mon}' non e' un servizio del compose")
    check(shares("uptime-kuma", mon) is not False, f"uptime-kuma non raggiunge il monitor documentato '{mon}'")

# ---------------------------------------------------------------- 5. reti
begin("reti")
for n in svc:
    if n != "restic":
        check("default" not in nets_of(n), f"{n} e' sulla rete 'default' implicita: dichiara networks:")
needs = [
    ("hs_frontend", "backend"),
    ("immich_server", "immich_postgres"), ("immich_server", "immich_redis"), ("immich_server", "immich_machine_learning"),
    ("jellyfin", "seerr"), ("seerr", "jellyfin"), ("seerr", "radarr"), ("seerr", "sonarr"),
    ("maintainerr", "jellyfin"), ("maintainerr", "seerr"), ("maintainerr", "radarr"), ("maintainerr", "sonarr"),
    ("radarr", "qbittorrent"), ("radarr", "prowlarr"), ("radarr", "jellyfin"), ("radarr", "plex"), ("radarr", "ntfy"),
    ("sonarr", "qbittorrent"), ("sonarr", "prowlarr"), ("sonarr", "jellyfin"), ("sonarr", "plex"), ("sonarr", "ntfy"),
    ("prowlarr", "radarr"), ("prowlarr", "sonarr"), ("prowlarr", "flaresolverr"),
    ("bazarr", "radarr"), ("bazarr", "sonarr"), ("recyclarr", "radarr"), ("recyclarr", "sonarr"),
    ("pihole", "unbound"), ("diun", "ntfy"), ("ntfy-telegram", "ntfy"), ("diun", "docker-proxy-ro"), ("autoheal", "docker-proxy-rw"), ("backend", "docker-gate"),
]
for a, b in needs:
    check(shares(a, b) is True, f"dipendenza rotta: {a} -> {b} non condividono nessuna rete")
for u in ("qbittorrent", "prowlarr", "flaresolverr", "bazarr", "recyclarr"):
    for p in ("vaultwarden", "jellyfin", "plex", "romm", "romm-db", "immich_server", "immich_postgres", "backend", "hs_frontend", "pihole", "docker-proxy-ro", "docker-proxy-rw", "docker-gate"):
        check(shares(u, p) is not True, f"separazione rotta: {u} (contenuti non fidati) raggiunge {p}")
for who, allowed in (("vaultwarden", {"tailscale", "uptime-kuma"}), ("docker-proxy-ro", {"diun"}), ("docker-proxy-rw", {"autoheal"}), ("docker-gate", {"backend"}),
                     ("copyparty", {"tailscale"}), ("syncthing", {"tailscale"}), ("convertx", {"tailscale"}), ("rclone", set()),
                     ("romm", {"tailscale", "romm-db"}), ("romm-db", {"romm"}),
                     ("immich_postgres", {"immich-server", "immich-redis"}), ("immich_redis", {"immich-server", "immich-postgres"})):
    k = key(who)
    got = {n for n in svc if n != k and nets_of(n) & nets_of(k)}
    check(got == allowed, f"{who} e' raggiungibile da {sorted(got)}, attesi {sorted(allowed)}")
for n in ("immich_db", "dockerproxy_ro", "dockerproxy_rw", "dockerproxy_api", "convert", "romm_db"):
    check(nets.get(n, {}).get("internal") is True, f"la rete {n} deve essere internal")
check(nets.get("backup_out", {}).get("internal") is not True, "la rete backup_out deve avere accesso a Internet (rclone carica l'archivio fuori sede)")
subs = {}
for n, d in nets.items():
    for c in (d.get("ipam") or {}).get("config") or []:
        subs[n] = ipaddress.ip_network(c["subnet"])
for n in {x for s in svc for x in nets_of(s)} - {"<host>", "default"}:
    check(n in subs, f"la rete {n} non ha una subnet fissa (Docker potrebbe scegliere quella di casa)")
items = list(subs.items())
for i, (a, sa) in enumerate(items):
    check(not sa.overlaps(ipaddress.ip_network("192.168.0.0/16")), f"la subnet di {a} ({sa}) cade in 192.168.0.0/16")
    for b, sb in items[i + 1:]:
        check(not sa.overlaps(sb), f"subnet sovrapposte: {a} {sa} e {b} {sb}")

# ---------------------------------------------------------------- 6. esposizione e socket
begin("esposizione")
LAN_OK = {"jellyfin", "seerr", "pihole", "copyparty", "plex"}   # Jellyfin e Seerr seguono LAN_BIND_ADDR; Pi-hole ha PIHOLE_DNS_BIND / PIHOLE_WEB_BIND; Copyparty COPYPARTY_BIND_ADDR; Plex PLEX_BIND_ADDR
for n, s in svc.items():
    for p in s.get("ports") or []:
        check(n in LAN_OK or p.get("host_ip") == "127.0.0.1",
              f"{n}: la porta {p.get('published')} e' pubblicata su {p.get('host_ip', '0.0.0.0')}, non su 127.0.0.1")
sock = sorted(n for n, s in svc.items() if any(v.get("source") == "/var/run/docker.sock" for v in (s.get("volumes") or [])))
expected_sock = ["beszel-agent", "docker-gate", "docker-proxy-ro", "docker-proxy-rw", "portainer"]
check(sock == expected_sock, f"montano il socket Docker: {sock}; attesi {expected_sock} (se e' voluto aggiorna docs/security.md e questo script)")

# docker-gate: il backend non monta piu' il socket e parla solo col filtro; il filtro e' blindato e conosce esattamente i container del pannello
be = svc.get(key("hs_backend") or "")
gt = svc.get(key("docker-gate") or "")
check(gt is not None, "manca il servizio docker-gate")
if be and gt:
    check((be.get("environment") or {}).get("DOCKER_HOST") == "tcp://docker-gate:2375", "il backend deve avere DOCKER_HOST=tcp://docker-gate:2375")
    check("docker-gate" in (be.get("depends_on") or {}), "il backend deve dipendere da docker-gate")
    check(not gt.get("ports"), "docker-gate non deve pubblicare porte")
    check(nets_of("docker-gate") == {"dockerproxy_api"}, f"docker-gate deve stare solo nella rete dockerproxy_api, sta in {sorted(nets_of('docker-gate'))}")
    check(gt.get("read_only") is True and "ALL" in (gt.get("cap_drop") or []), "docker-gate deve essere read_only e con cap_drop ALL")
    gsock = [v for v in gt.get("volumes") or [] if v.get("source") == "/var/run/docker.sock"]
    check(len(gsock) == 1, "docker-gate deve montare il socket Docker (e solo quello)")
    svc_containers = sorted(c for m in literal("src/backend/app/services.py", "SERVICES").values() for c in m["containers"])
    gate_list = sorted(x.strip() for x in str((gt.get("environment") or {}).get("GATE_CONTAINERS", "")).split(",") if x.strip())
    check(gate_list == svc_containers, f"GATE_CONTAINERS e i container di services.py divergono: solo nel filtro {sorted(set(gate_list) - set(svc_containers))}, solo nel catalogo {sorted(set(svc_containers) - set(gate_list))}")
    gate_env = gt.get("environment") or {}
    be_env = be.get("environment") or {}
    for k_gate, k_be in (("RESTIC_IMAGE", "RESTIC_IMAGE"), ("RESTIC_REPO_DIR", "RESTIC_REPO_DIR"), ("RESTIC_PASSWORD_FILE", "RESTIC_PASSWORD_FILE"),
                         ("HOST_DATA_DIR", "HOST_DATA_DIR"), ("HOST_PHOTOS_DIR", "HOST_PHOTOS_DIR")):
        check(gate_env.get(k_gate) == be_env.get(k_be), f"{k_gate} deve avere lo stesso valore nel filtro e nel backend (altrimenti il job di backup viene rifiutato)")

# il ponte Telegram: solo in uscita, niente porte, niente socket, segreti in sola lettura
tg = svc.get(key("ntfy-telegram") or "")
check(tg is not None, "manca il servizio ntfy-telegram")
if tg:
    check(not tg.get("ports"), "ntfy-telegram non deve pubblicare porte")
    check(nets_of("ntfy-telegram") == {"notify"}, f"ntfy-telegram deve stare solo nella rete notify, sta in {sorted(nets_of('ntfy-telegram'))}")
    check(tg.get("read_only") is True and "ALL" in (tg.get("cap_drop") or []), "ntfy-telegram deve essere read_only e con cap_drop ALL")
    check(tg.get("profiles") == ["telegram"], "ntfy-telegram deve avere il profilo telegram")
    secrets_mount = [v for v in tg.get("volumes") or [] if v.get("target") == "/run/secrets"]
    check(len(secrets_mount) == 1 and secrets_mount[0].get("read_only") is True, "i segreti di ntfy-telegram devono essere montati in sola lettura")
    check(not any("telegram_bot_token" in str(e) or "ntfy_token" in str(e) for e in (tg.get("environment") or {}).values()), "i token non vanno nelle variabili d'ambiente")

# ---------------------------------------------------------------- schermata iniziale (src/hero)
begin("hero")
hero_src = "".join(f.read_text() for f in sorted((ROOT / "src/hero/src").glob("*.jsx")))
hero_code = re.sub(r"/\*.*?\*/|(?<!:)//[^\n]*", "", hero_src, flags=re.S)   # senza commenti: citare <nav> in un commento non e' usarlo
panel_css = re.sub(r"/\*.*?\*/", "", (ROOT / "src/frontend/style.css").read_text(), flags=re.S)
panel_classes = set(re.findall(r"\.([A-Za-z_][\w-]*)", panel_css))
# classi usate nell'hero: ogni parola dentro className="..." o className={`...`}. Quelle con variante (md:block, hover:...) hanno un
# nome diverso (`md\\:block`) e non possono scontrarsi con una classe del pannello: contano solo le altre.
used = set()
for a, b in re.findall(r'className=(?:"([^"]*)"|\{`([^`]*)`\})', hero_code):
    used |= {t for t in f"{a} {b}".split() if t and ":" not in t and "$" not in t and "{" not in t}
clash = sorted(used & panel_classes)
check(not clash, f"classi usate sia dall'hero (Tailwind) sia da src/frontend/style.css: {clash}. Lo stile del pannello le applicherebbe all'hero (e' gia' successo con 'block': +2rem di margine)")
# elementi che style.css stila in modo globale: nell'hero si usano div con role, non questi tag
for tag in ("nav", "main"):
    check(not re.search(rf"<{tag}[\s>]", hero_code), f"l'hero usa <{tag}>, che style.css stila in modo globale: usa <div role=\"{'navigation' if tag == 'nav' else 'main'}\">")
check((ROOT / "src/hero/package-lock.json").is_file(), "manca src/hero/package-lock.json (serve a `npm ci` nella build del frontend)")
fe = svc.get(key("hs_frontend") or "", {})
bld = fe.get("build") or {}
check(bld.get("dockerfile") == "Dockerfile.frontend" and str(bld.get("context", "")).endswith("/src"), "il frontend deve costruirsi da src/Dockerfile.frontend (contesto ./src)")
check(not any(v.get("target") == "/usr/share/nginx/html" for v in fe.get("volumes") or []), "src/frontend e' ancora montato su /usr/share/nginx/html e nasconderebbe l'hero compilato in /hero")
df = (ROOT / "src/Dockerfile.frontend").read_text()
check("COPY hero/package.json hero/package-lock.json" in df and "npm ci" in df and "/usr/share/nginx/html/hero/" in df, "src/Dockerfile.frontend: mancano `npm ci` con il lockfile o la copia della build in /hero")
# CSP: il video esterno e' consentito solo dove serve, e senza aprire altro
csp = re.search(r'Content-Security-Policy "([^"]*)"', (ROOT / "nginx/security-headers.conf").read_text())
check(csp is not None, "manca la Content-Security-Policy in nginx/security-headers.conf")
if csp:
    dirs = {d.split()[0]: d.split()[1:] for d in csp.group(1).split(";") if d.strip()}
    check("'unsafe-inline'" not in csp.group(1) and "'unsafe-eval'" not in csp.group(1), "la CSP non deve contenere 'unsafe-inline' o 'unsafe-eval'")
    check(dirs.get("script-src") == ["'self'"] and dirs.get("style-src") == ["'self'"] and dirs.get("worker-src") == ["'self'"], "script-src, style-src e worker-src devono restare 'self'")
    cfg_js = (ROOT / "src/hero/src/config.js").read_text()
    vm = re.search(r'VIDEO_SRC\s*=\s*"([^"]*)"', cfg_js)
    check(vm is not None, "VIDEO_SRC non trovato in src/hero/src/config.js")
    if vm:
        from urllib.parse import urlparse
        u = urlparse(vm.group(1))
        def allowed(directive):
            for src in dirs.get(directive, []):
                if src.startswith("https://"):
                    h = src[len("https://"):]
                    if u.hostname == h or (h.startswith("*.") and u.hostname.endswith(h[1:])):
                        return True
            return False
        if u.scheme == "https":
            check(allowed("media-src") and allowed("connect-src"), f"VIDEO_SRC ({u.hostname}) non e' ammesso da media-src e connect-src nella CSP")
        else:
            check(all(x.startswith("https://") or x in ("'self'", "blob:") for x in dirs.get("media-src", []) + dirs.get("connect-src", [])) and
                  not any(x.startswith("https://") for x in dirs.get("media-src", []) + dirs.get("connect-src", [])),
                  "VIDEO_SRC e' locale: togli da media-src e connect-src gli host esterni (https://*.mux.com) dalla CSP")
    ext = [x for d in ("media-src", "connect-src") for x in dirs.get(d, []) if x.startswith("http")]
    check(all(x == "https://*.mux.com" for x in ext) or not ext, f"la CSP ammette host esterni oltre a Mux: {ext}")

# ---------------------------------------------------------------- backup manuale su disco esterno
begin("backup")
bk_src = (ROOT / "src/backend/app/backup.py").read_text()
be_name = by_name.get("hs_backend")
be = svc.get(be_name or "", {})
be_env = be.get("environment") or {}
check(be_name is not None, "manca il servizio hs_backend")
check("RESTIC_SCHEDULE" not in be_env and "start_scheduler" not in bk_src, "il backup e' solo manuale: RESTIC_SCHEDULE o lo scheduler sono ricomparsi")
for var in ("BACKUP_DISK_DIR", "BACKUP_MOUNT_PARENT", "BACKUP_WARN_DAYS"):
    check(var in be_env, f"il backend non riceve {var}")
    check(re.search(rf"^{var}=", (ROOT / ".env.example").read_text(), re.M) is not None, f".env.example non documenta {var}")
pm = [v for v in be.get("volumes") or [] if v.get("target") == "/data/backup-parent"]
check(len(pm) == 1, "il backend deve montare la cartella madre del disco su /data/backup-parent")
if pm:
    check(pm[0].get("read_only") is True, "/data/backup-parent deve essere in sola lettura")
    check((pm[0].get("bind") or {}).get("propagation") == "rslave", "/data/backup-parent deve avere bind.propagation: rslave (altrimenti il backend non vede il disco collegato dopo l'avvio)")
rs = svc.get(by_name.get("restic") or "restic", {})
rv = [v for v in rs.get("volumes") or [] if v.get("target") == "/repo"]
check(len(rv) == 1 and no_host_path(rv[0]), "il servizio restic deve montare /repo con create_host_path: false (un disco scollegato non deve far creare la cartella sul disco di sistema)")
# ogni rotta di scrittura del backup richiede l'amministratore
tree = ast.parse(bk_src)
for fn in ast.walk(tree):
    if isinstance(fn, ast.FunctionDef):
        for d in fn.decorator_list:
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("post", "put", "delete", "patch"):
                check("require_admin" in ast.unparse(d), f"backup.py: la rotta {fn.name} scrive ma non dichiara dependencies=[Depends(require_admin)]")

# ---------------------------------------------------------------- scambio file, Syncthing, convertitore, copia fuori sede
begin("nuovi servizi")
compose_text = (ROOT / "compose.yaml").read_text()


def hardened(name, ro=True):
    s = svc.get(key(name) or "")
    check(s is not None, f"manca il servizio {name}")
    if s is None:
        return None
    check("ALL" in (s.get("cap_drop") or []), f"{name}: deve avere cap_drop ALL")
    check("no-new-privileges:true" in (s.get("security_opt") or []), f"{name}: deve avere no-new-privileges")
    if ro:
        check(s.get("read_only") is True, f"{name}: deve essere read_only")
    check(not s.get("privileged"), f"{name}: non deve essere privilegiato")
    check("/var/run/docker.sock" not in str(s.get("volumes")), f"{name}: non deve montare il socket Docker")
    return s


cp = hardened("copyparty")
if cp:
    check("${COPYPARTY_BIND_ADDR:-127.0.0.1}:3923:3923" in compose_text, "copyparty: la porta deve seguire COPYPARTY_BIND_ADDR con 127.0.0.1 come valore di serie")
    vols = {v.get("target"): v for v in cp.get("volumes") or []}
    check(set(vols) == {"/cfg", "/hist", "/w"}, f"copyparty: monta {sorted(vols)}, attesi /cfg, /hist, /w")
    check(vols.get("/w", {}).get("source", "").endswith("/scambio"), "copyparty: /w deve essere data/scambio (mai /media ne' altre cartelle)")
    check(vols.get("/cfg", {}).get("read_only") is True and no_host_path(vols.get("/cfg", {})),
          "copyparty: /cfg deve essere in sola lettura e con create_host_path: false (senza configurazione non deve partire con la cartella aperta a tutti)")
    check(nets_of("copyparty") == {"files"}, f"copyparty deve stare solo nella rete files, sta in {sorted(nets_of('copyparty'))}")
    check(cp.get("user"), "copyparty: deve girare con un utente non root (user:)")
sy = hardened("syncthing")
if sy:
    check(all(str(p.get("target")) == "8384" for p in sy.get("ports") or []), "syncthing: sul computer si pubblica solo l'interfaccia web (8384), mai la porta di sincronizzazione 22000")
    check(nets_of("syncthing") == {"sync"}, f"syncthing deve stare solo nella rete sync, sta in {sorted(nets_of('syncthing'))}")
    check(sy.get("user"), "syncthing: deve girare con un utente non root (user:)")
    check(str((sy.get("environment") or {}).get("STGUIADDRESS")) == "0.0.0.0:8384", "syncthing: STGUIADDRESS deve essere 0.0.0.0:8384 (l'interfaccia deve raggiungere Tailscale)")
px = svc.get(key("plex") or "")
check(px is not None, "manca il servizio plex")
if px:
    check(px.get("profiles") == ["plex"], "plex deve avere il profilo plex (non parte con `up`)")
    check("ALL" in (px.get("cap_drop") or []), "plex: deve avere cap_drop ALL")
    check(set(px.get("cap_add") or []) <= {"CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER"}, f"plex: capacita' extra non ammesse: {sorted(set(px.get('cap_add') or []) - {'CHOWN', 'SETUID', 'SETGID', 'DAC_OVERRIDE', 'FOWNER'})}")
    check("no-new-privileges:true" in (px.get("security_opt") or []), "plex: deve avere no-new-privileges")
    check(not px.get("privileged") and "/var/run/docker.sock" not in str(px.get("volumes")), "plex: ne' privilegiato ne' con il socket Docker")
    check("${PLEX_BIND_ADDR:-127.0.0.1}:32400:32400" in compose_text, "plex: la porta deve seguire PLEX_BIND_ADDR con 127.0.0.1 come valore di serie")
    check(nets_of("plex") == {"media"}, f"plex deve stare solo nella rete media, sta in {sorted(nets_of('plex'))}")
    check(all(px.get(k) for k in ("mem_limit", "cpus", "pids_limit")), "plex: servono mem_limit, cpus e pids_limit")
    pv = {v.get("target"): v for v in px.get("volumes") or []}
    check(set(pv) == {"/config", "/transcode", "/media"}, f"plex: monta {sorted(pv)}, attesi /config, /transcode, /media")
    check(pv.get("/media", {}).get("read_only") is True, "plex: /media deve essere in sola lettura (Radarr e Sonarr scrivono, Plex legge)")
    check(pv.get("/transcode", {}).get("type") == "tmpfs", "plex: /transcode deve essere tmpfs (niente scritture continue sulla SD)")


for rn in ("romm", "romm-db"):
    rs_ = hardened(rn, ro=False)
    if rs_:
        check(rs_.get("profiles") == ["romm"], f"{rn} deve avere il profilo romm (non parte con `up`)")
        check(not rs_.get("ports"), f"{rn} non deve pubblicare porte (si apre solo da Tailscale)")
        check(all(rs_.get(k) for k in ("mem_limit", "cpus", "pids_limit")), f"{rn}: servono mem_limit, cpus e pids_limit")
        check(set(rs_.get("cap_add") or []) <= {"CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER"}, f"{rn}: capacita' extra non ammesse")
rm_ = svc.get(key("romm") or "")
if rm_:
    check(nets_of("romm") == {"romm", "romm_db"}, f"romm deve stare nelle reti romm e romm_db, sta in {sorted(nets_of('romm'))}")
    check(nets_of("romm-db") == {"romm_db"}, f"romm-db deve stare solo nella rete romm_db, sta in {sorted(nets_of('romm-db'))}")
    rvol = {v.get("target"): v for v in rm_.get("volumes") or []}
    check(set(rvol) == {"/romm/resources", "/redis-data", "/romm/library", "/romm/assets", "/romm/config"}, f"romm: monta {sorted(rvol)}")
    check(all(str(v.get("source", "")).split("/romm/")[0].endswith("") and "/romm/" in str(v.get("source")) for v in rvol.values()), "romm: tutti i montaggi devono stare in data/romm (mai /media o altre cartelle)")
    rd = (rm_.get("depends_on") or {}).get("romm-db") or {}
    check(rd.get("condition") == "service_healthy", "romm deve aspettare che il database sia sano (service_healthy)")
    check("romm-db" in str(literal("src/backend/app/services.py", "SERVICES")["romm"]["containers"][0]), "services.py: il database di RomM deve partire prima di RomM")


cx = hardened("convertx", ro=False)
if cx:
    check(cx.get("profiles") == ["convertx"], "convertx deve avere il profilo convertx (non parte con `up`)")
    check(not cx.get("ports"), "convertx non deve pubblicare porte (rete interna: si apre solo da Tailscale)")
    check(nets_of("convertx") == {"convert"}, f"convertx deve stare solo nella rete convert, sta in {sorted(nets_of('convertx'))}")
    check(all(cx.get(k) for k in ("mem_limit", "cpus", "pids_limit")), "convertx: servono mem_limit, cpus e pids_limit")
    cxe = cx.get("environment") or {}
    check("JWT_SECRET" not in cxe, "convertx: JWT_SECRET non va impostato nel compose (se vuoto firmerebbe le sessioni con una chiave vuota)")
    check(str(cxe.get("ACCOUNT_REGISTRATION")) == "false" and str(cxe.get("ALLOW_UNAUTHENTICATED")) == "false" and str(cxe.get("HTTP_ALLOWED")) == "false",
          "convertx: ACCOUNT_REGISTRATION, ALLOW_UNAUTHENTICATED e HTTP_ALLOWED devono restare false")
    check(not any(v.get("target") != "/app/data" and v.get("type") == "bind" for v in cx.get("volumes") or []), "convertx: l'unico montaggio ammesso e' /app/data")
rc = svc.get(key("rclone") or "")
check(rc is not None, "manca il servizio rclone")
if rc:
    check(rc.get("profiles") == ["tools"], "rclone deve stare nel profilo tools (lo lancia backup-remoto.sh)")
    check(rc.get("read_only") is True and "ALL" in (rc.get("cap_drop") or []) and (rc.get("cap_add") or []) == ["DAC_OVERRIDE"],
          "rclone: read_only, cap_drop ALL e come unica capacita' DAC_OVERRIDE")
    rrepo = [v for v in rc.get("volumes") or [] if v.get("target") == "/repo"]
    check(len(rrepo) == 1 and rrepo[0].get("read_only") is True and no_host_path(rrepo[0]),
          "rclone: /repo deve essere in sola lettura e con create_host_path: false (rclone non deve poter modificare l'archivio locale)")
    check(nets_of("rclone") == {"backup_out"}, f"rclone deve stare solo nella rete backup_out, sta in {sorted(nets_of('rclone'))}")
    check(not rc.get("ports"), "rclone non deve pubblicare porte")
# NET_ADMIN e' un privilegio da concedere solo a chi fa da firewall/tunnel (gluetun) o, se attivato a mano, a Tailscale in modalita' kernel
check(not [n for n, c in svc.items() if "NET_ADMIN" in (c.get("cap_add") or []) or c.get("privileged")], "nel compose di serie nessun container deve avere NET_ADMIN o privilegi (e' per gluetun, in compose.vpn.yml)")
env_ex = (ROOT / ".env.example").read_text()
check(re.search(r"^COMPOSE_FILE=", env_ex, re.M) is None, ".env.example non deve contenere COMPOSE_FILE: lo scrive vpn-setup.sh solo se la VPN e' attiva")
for var in ("COPYPARTY_BIND_ADDR", "CONVERTX_CPUS", "CONVERTX_MEM", "RCLONE_REMOTE", "BACKUP_REMOTO_MAX_DELETE", "SMART_TEMP_WARN", "SMART_NTFY_TOPIC",
            "WIREGUARD_ADDRESSES", "WIREGUARD_PUBLIC_KEY", "WIREGUARD_ENDPOINT_IP", "WIREGUARD_KEY_FILE"):
    check(re.search(rf"^{var}=", env_ex, re.M) is not None, f".env.example non documenta {var}")
for sc in ("backup-remoto.sh", "copyparty-setup.sh", "syncthing-setup.sh", "smart-check.sh", "vpn-setup.sh", "vpn-test.sh"):
    f = ROOT / "src/scripts" / sc
    check(f.is_file() and os.access(f, os.X_OK), f"src/scripts/{sc} manca o non e' eseguibile")

# ---------------------------------------------------------------- VPN di qBittorrent (compose.vpn.yml)
begin("vpn")
check(cfg_vpn is not None, "manca compose.vpn.yml")
if cfg_vpn:
    vs = cfg_vpn["services"]
    vby = {(c.get("container_name") or n): n for n, c in vs.items()}
    gl, qb = vs.get(vby.get("gluetun", "")), vs.get(vby.get("qbittorrent", ""))
    check(gl is not None and qb is not None, "con compose.vpn.yml devono esistere gluetun e qbittorrent")
    if gl and qb:
        check(qb.get("network_mode") == f"service:{vby['gluetun']}", f"qbittorrent deve usare la rete di gluetun, ha network_mode={qb.get('network_mode')!r}")
        check(not qb.get("networks") and not qb.get("ports"), "qbittorrent con network_mode non puo' avere networks ne' ports (le porte si pubblicano su gluetun)")
        check(((qb.get("depends_on") or {}).get(vby["gluetun"]) or {}).get("condition") == "service_healthy" and ((qb.get("depends_on") or {}).get(vby["gluetun"]) or {}).get("restart") is True,
              "qbittorrent deve dipendere da gluetun con condition: service_healthy e restart: true")
        check(set(gl.get("networks") or {}) == {"arr"}, f"gluetun deve stare solo nella rete arr, sta in {sorted(gl.get('networks') or {})}")
        check("qbittorrent" in ((gl.get("networks") or {}).get("arr") or {}).get("aliases", []), "gluetun deve avere l'alias 'qbittorrent' sulla rete arr (Radarr, Sonarr e serve.json continuano a chiamarlo cosi')")
        check(gl.get("cap_add") == ["NET_ADMIN"] and not gl.get("privileged"), "gluetun: unica capacita' NET_ADMIN, senza privileged")
        check([n for n, c in vs.items() if "NET_ADMIN" in (c.get("cap_add") or []) or c.get("privileged")] == [vby["gluetun"]], "con la VPN solo gluetun puo' avere NET_ADMIN")
        check(all(str(p.get("host_ip")) == "127.0.0.1" and str(p.get("target")) == "8080" for p in gl.get("ports") or []) and gl.get("ports"),
              "gluetun: pubblica solo 127.0.0.1:8080 (il web di qBittorrent)")
        check(gl.get("secrets") and "wireguard_private_key" in str(gl["secrets"]) and cfg_vpn.get("secrets", {}).get("wireguard_private_key"), "la chiave WireGuard deve arrivare come segreto (file), non come variabile")
        genv = gl.get("environment") or {}
        check(not any("PRIVATE_KEY" in k and not k.endswith("_SECRETFILE") for k in genv), "gluetun: la chiave privata non deve stare nelle variabili d'ambiente (si vedrebbe con docker inspect)")
        check(genv.get("VPN_TYPE") == "wireguard" and genv.get("VPN_SERVICE_PROVIDER") == "custom", "gluetun: VPN_TYPE=wireguard e VPN_SERVICE_PROVIDER=custom (valgono per qualsiasi provider)")
        check("autoheal=true" not in (gl.get("labels") or {}).values() and "autoheal" not in (gl.get("labels") or {}),
              "gluetun non deve avere l'etichetta autoheal: un riavvio esterno lascerebbe qBittorrent senza rete")
        arr_sub = subs.get("arr")
        check(arr_sub is not None and genv.get("FIREWALL_OUTBOUND_SUBNETS") == str(arr_sub), f"FIREWALL_OUTBOUND_SUBNETS di gluetun ({genv.get('FIREWALL_OUTBOUND_SUBNETS')}) deve essere la subnet della rete arr ({arr_sub})")
        # chi NON deve passare dalla VPN
        for other in ("prowlarr", "flaresolverr", "radarr", "sonarr", "bazarr", "recyclarr"):
            o = vs.get(vby.get(other, ""))
            check(o is not None and not str(o.get("network_mode") or "").startswith("service:"), f"{other} non deve passare dalla VPN")
        # tutto cio' che e' in arr raggiunge qBittorrent per nome, e Tailscale pure
        arr_members = {n for n, c in vs.items() if "arr" in (c.get("networks") or {})}
        check({"radarr", "sonarr", "prowlarr"} <= {vs[n].get("container_name") or n for n in arr_members}, "Radarr, Sonarr e Prowlarr devono restare nella rete arr")
        check(any((vs[n].get("container_name") or n) == "tailscale" for n in arr_members), "Tailscale deve restare nella rete arr (serve.json pubblica qbittorrent:8080)")
    # gli stessi vincoli di esposizione del compose di serie, con la VPN attiva
    for n, c in vs.items():
        for p in c.get("ports") or []:
            check((c.get("container_name") or n) in LAN_OK or p.get("host_ip") == "127.0.0.1", f"con la VPN: {n} pubblica la porta {p.get('published')} fuori da 127.0.0.1")
    vsock = sorted(n for n, c in vs.items() if any(v.get("source") == "/var/run/docker.sock" for v in (c.get("volumes") or [])))
    check(vsock == expected_sock, f"con la VPN i container col socket Docker cambiano: {vsock}")

print("Controllo di coerenza:")
for name, n in counts.items():
    bad = sum(1 for f in fails if f.startswith(f"[{name}]"))
    print(f"  {'OK ' if not bad else 'KO '} {name:12} {n} controlli" + (f", {bad} problemi" if bad else ""))
if fails:
    print(f"\n{len(fails)} PROBLEMI:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("Tutto coerente.")
