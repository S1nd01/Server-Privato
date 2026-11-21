#!/usr/bin/env python3
"""Controlla che le parti del progetto che devono restare allineate non divergano.

    python3 src/scripts/check-config.py

Legge compose.yaml (risolto da `docker compose config`: non serve Docker in funzione), tailscale/serve.json, il catalogo del
pannello (services.py), i backup (backup.py), l'elenco delle cartelle (sync-env.sh e stats.py) e docs/uptime-kuma.md.
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
    env.update(TZ="UTC", PIHOLE_PASSWORD="x", IMMICH_DB_PASSWORD="x")
try:
    r = subprocess.run(["docker", "compose", "--profile", "*", "config", "--format", "json"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
except (OSError, subprocess.TimeoutExpired) as exc:
    sys.exit(f"ERRORE: non riesco a eseguire docker compose: {exc}")
if r.returncode != 0:
    sys.exit("ERRORE: docker compose config non riesce a leggere il compose:\n" + r.stderr.strip()[:600])
cfg = json.loads(r.stdout)
svc, nets = cfg["services"], cfg.get("networks", {})
by_name = {(s.get("container_name") or n): n for n, s in svc.items()}


def key(x):
    return by_name.get(x) or (x if x in svc else None)


def nets_of(n):
    s = svc[n]
    return {"<host>"} if s.get("network_mode") == "host" else (set((s.get("networks") or {})) or {"default"})


def shares(a, b):
    ka, kb = key(a), key(b)
    return None if ka is None or kb is None else bool((nets_of(ka) & nets_of(kb)) - {"<host>"})


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
check(not (catalog - compose_names), f"services.py cita container che non esistono nel compose: {sorted(catalog - compose_names)}")
extra = compose_names - catalog - {"hs_frontend", "hs_backend", "restic"}
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
    ("radarr", "qbittorrent"), ("radarr", "prowlarr"), ("radarr", "jellyfin"), ("radarr", "ntfy"),
    ("sonarr", "qbittorrent"), ("sonarr", "prowlarr"), ("sonarr", "jellyfin"), ("sonarr", "ntfy"),
    ("prowlarr", "radarr"), ("prowlarr", "sonarr"), ("prowlarr", "flaresolverr"),
    ("bazarr", "radarr"), ("bazarr", "sonarr"), ("recyclarr", "radarr"), ("recyclarr", "sonarr"),
    ("pihole", "unbound"), ("diun", "ntfy"), ("ntfy-telegram", "ntfy"), ("diun", "docker-proxy-ro"), ("autoheal", "docker-proxy-rw"),
]
for a, b in needs:
    check(shares(a, b) is True, f"dipendenza rotta: {a} -> {b} non condividono nessuna rete")
for u in ("qbittorrent", "prowlarr", "flaresolverr", "bazarr", "recyclarr"):
    for p in ("vaultwarden", "jellyfin", "immich_server", "immich_postgres", "backend", "hs_frontend", "pihole", "docker-proxy-ro", "docker-proxy-rw"):
        check(shares(u, p) is not True, f"separazione rotta: {u} (contenuti non fidati) raggiunge {p}")
for who, allowed in (("vaultwarden", {"tailscale", "uptime-kuma"}), ("docker-proxy-ro", {"diun"}), ("docker-proxy-rw", {"autoheal"}),
                     ("immich_postgres", {"immich-server", "immich-redis"}), ("immich_redis", {"immich-server", "immich-postgres"})):
    k = key(who)
    got = {n for n in svc if n != k and nets_of(n) & nets_of(k)}
    check(got == allowed, f"{who} e' raggiungibile da {sorted(got)}, attesi {sorted(allowed)}")
for n in ("immich_db", "dockerproxy_ro", "dockerproxy_rw"):
    check(nets.get(n, {}).get("internal") is True, f"la rete {n} deve essere internal")
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
LAN_OK = {"jellyfin", "seerr", "pihole"}   # Jellyfin e Seerr seguono LAN_BIND_ADDR; Pi-hole ha PIHOLE_DNS_BIND / PIHOLE_WEB_BIND
for n, s in svc.items():
    for p in s.get("ports") or []:
        check(n in LAN_OK or p.get("host_ip") == "127.0.0.1",
              f"{n}: la porta {p.get('published')} e' pubblicata su {p.get('host_ip', '0.0.0.0')}, non su 127.0.0.1")
sock = sorted(n for n, s in svc.items() if any(v.get("source") == "/var/run/docker.sock" for v in (s.get("volumes") or [])))
expected_sock = ["backend", "beszel-agent", "docker-proxy-ro", "docker-proxy-rw", "portainer"]
check(sock == expected_sock, f"montano il socket Docker: {sock}; attesi {expected_sock} (se e' voluto aggiorna docs/security.md e questo script)")

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
check(len(rv) == 1 and (rv[0].get("bind") or {}).get("create_host_path") is False, "il servizio restic deve montare /repo con create_host_path: false (un disco scollegato non deve far creare la cartella sul disco di sistema)")
# ogni rotta di scrittura del backup richiede l'amministratore
tree = ast.parse(bk_src)
for fn in ast.walk(tree):
    if isinstance(fn, ast.FunctionDef):
        for d in fn.decorator_list:
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("post", "put", "delete", "patch"):
                check("require_admin" in ast.unparse(d), f"backup.py: la rotta {fn.name} scrive ma non dichiara dependencies=[Depends(require_admin)]")

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
