"""Uso di risorse: server (CPU, RAM, dischi, temperatura) e servizi (CPU, RAM, tempo di attivita', salute).

I numeri dei container vengono dal demone Docker (come `docker stats`). La CPU si calcola come differenza
tra due letture successive (si ricorda l'ultima di ogni container): Docker risponde subito, senza il secondo di
campionamento di `docker stats`. Solo la prima lettura di ogni container aspetta quel secondo. Il risultato resta valido
per qualche secondo e, mentre un thread lo rinnova, gli altri ricevono l'ultimo disponibile: piu' schede aperte non
moltiplicano il carico sul server.
"""
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from docker.errors import DockerException, NotFound

from .services import SERVICES

TTL = 4.0  # secondi in cui una lettura resta valida
_refresh = threading.Lock()  # un solo thread alla volta rinnova la lettura
_cache: dict = {"at": 0.0, "data": None}
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stats")
_prev: dict[str, tuple[int, int]] = {}  # nome container -> (CPU del container, CPU di sistema) dell'ultima lettura

# Cartelle viste da dentro il backend (montate da compose.yaml). Quelle sullo stesso disco vengono unite.
DISK_PATHS = [("Dati", "/data/datadir"), ("Foto", "/data/photos")]

_HEALTH_ORDER = {"unhealthy": 3, "starting": 2, "healthy": 1}


# ---------------------------------------------------------------- container
def cpu_sample(raw: dict) -> tuple[int, int] | None:
    """(CPU usata dal container, CPU totale di sistema) in questo istante, per la lettura successiva."""
    try:
        cpu = raw["cpu_stats"]
        return cpu["cpu_usage"]["total_usage"], cpu["system_cpu_usage"]
    except (KeyError, TypeError):
        return None


def cpu_percent(raw: dict, host_cores: int, prev: tuple[int, int] | None = None) -> float | None:
    """CPU come `docker stats`: 100 = un core intero (puo' superare 100 con piu' core).

    Con `prev` (la lettura precedente) confronta con quella; senza, usa il campione "precpu" che Docker allega
    quando ha aspettato un secondo.
    """
    try:
        cpu = raw["cpu_stats"]
        if prev is None:
            pre = raw["precpu_stats"]
            before = (pre["cpu_usage"]["total_usage"], pre["system_cpu_usage"])
        else:
            before = prev
        cpu_delta = cpu["cpu_usage"]["total_usage"] - before[0]
        sys_delta = cpu["system_cpu_usage"] - before[1]
    except (KeyError, TypeError):
        return None
    if sys_delta <= 0 or cpu_delta < 0:
        return None
    cores = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or []) or host_cores
    return round(cpu_delta / sys_delta * cores * 100, 1)


def mem_used(raw: dict) -> int | None:
    """RAM usata senza la cache dei file (come `docker stats`)."""
    try:
        m = raw["memory_stats"]
        usage = m["usage"]
    except (KeyError, TypeError):
        return None
    st = m.get("stats") or {}
    cache = st.get("inactive_file", st.get("total_inactive_file", 0)) or 0
    return max(0, usage - cache)


def uptime_seconds(started_at: str | None) -> int | None:
    if not started_at or started_at.startswith("0001"):
        return None
    s = started_at.rstrip("Z")
    s = re.sub(r"\.(\d{1,6})\d*$", r".\1", s)  # Docker scrive i nanosecondi, Python legge fino ai microsecondi
    try:
        t = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - t).total_seconds()))


def _one(client, name: str, host_cores: int):
    try:
        c = client.containers.get(name)
    except NotFound:
        return name, None
    except DockerException:
        return name, None
    state = c.attrs.get("State") or {}
    running = c.status == "running"
    info = {
        "running": running,
        "health": (state.get("Health") or {}).get("Status"),
        "restarts": int(c.attrs.get("RestartCount") or 0),
        "uptime_s": uptime_seconds(state.get("StartedAt")) if running else None,
        "cpu_percent": None,
        "mem_bytes": None,
    }
    if running:
        try:
            prev = _prev.get(name)
            if prev is None:
                raw = c.stats(stream=False)  # prima lettura: Docker campiona per un secondo e da' gia' la CPU
            else:
                raw = c.stats(stream=False, one_shot=True)  # risposta immediata, la CPU si ricava dalla lettura precedente
            info["cpu_percent"] = cpu_percent(raw, host_cores, prev)
            info["mem_bytes"] = mem_used(raw)
            sample = cpu_sample(raw)
            if sample:
                _prev[name] = sample
        except DockerException:
            pass
    else:
        _prev.pop(name, None)  # al prossimo avvio i contatori ripartono da zero
    return name, info


def _service(meta: dict, infos: dict, cores: int) -> dict:
    present = {n: infos[n] for n in meta["containers"] if infos.get(n)}
    running = [i for i in present.values() if i["running"]]
    cpu = sum(i["cpu_percent"] or 0 for i in running) if running else None
    mem = sum(i["mem_bytes"] or 0 for i in running) if running else None
    ups = [i["uptime_s"] for i in running if i["uptime_s"] is not None]
    health = max((i["health"] for i in running if i["health"]), key=lambda h: _HEALTH_ORDER.get(h, 0), default=None)
    return {
        "cpu_percent": cpu,
        "cpu_host_percent": round(cpu / cores, 1) if cpu is not None else None,
        "mem_bytes": mem,
        "uptime_s": min(ups) if ups else None,  # il piu' recente: se un pezzo si e' riavviato lo si vede
        "health": health,
        "restarts": sum(i["restarts"] for i in present.values()),
        "containers": {n: {k: i[k] for k in ("running", "health", "cpu_percent", "mem_bytes")} for n, i in present.items()},
    }


# ---------------------------------------------------------------- server
_last_cpu: tuple[int, int] | None = None


def _read_cpu() -> tuple[int, int]:
    with open("/proc/stat") as f:
        vals = [int(x) for x in f.readline().split()[1:9]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return idle, sum(vals)


def _host_cpu_percent() -> float | None:
    global _last_cpu
    try:
        cur = _read_cpu()
        if _last_cpu is None:
            time.sleep(0.3)
            prev, cur = cur, _read_cpu()
        else:
            prev = _last_cpu
        _last_cpu = cur
    except (OSError, ValueError):
        return None
    d_total, d_idle = cur[1] - prev[1], cur[0] - prev[0]
    return round(100 * (1 - d_idle / d_total), 1) if d_total > 0 else None


def _meminfo() -> tuple[int | None, int | None]:
    try:
        vals = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, rest = line.partition(":")
                if k in ("MemTotal", "MemAvailable"):
                    vals[k] = int(rest.split()[0]) * 1024
        total = vals["MemTotal"]
        return total, total - vals["MemAvailable"]
    except (OSError, KeyError, ValueError, IndexError):
        return None, None


def _temperature() -> float | None:
    """Temperatura della CPU (Raspberry e PC con sensori). Nella WSL di solito non c'e'."""
    try:
        for d in sorted(os.listdir("/sys/class/thermal")):
            if d.startswith("thermal_zone"):
                with open(f"/sys/class/thermal/{d}/temp") as f:
                    v = int(f.read().strip())
                if v > 0:
                    return round(v / 1000, 1)
    except (OSError, ValueError):
        pass
    return None


def _uptime() -> int | None:
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return None


def _disks() -> list[dict]:
    groups: dict[int, dict] = {}
    for label, path in DISK_PATHS:
        try:
            dev = os.stat(path).st_dev
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        g = groups.setdefault(dev, {"labels": [], "total": usage.total, "used": usage.used})
        g["labels"].append(label)
    def name(labels: list[str]) -> str:
        return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " e " + labels[-1]

    return [{"label": name(g["labels"]), "total": g["total"], "used": g["used"]} for g in groups.values()]


def _host() -> dict:
    total, used = _meminfo()
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        load = None
    return {
        "cores": os.cpu_count() or 1,
        "cpu_percent": _host_cpu_percent(),
        "load": load,
        "mem_total": total,
        "mem_used": used,
        "disks": _disks(),
        "temp_c": _temperature(),
        "uptime_s": _uptime(),
    }


# ---------------------------------------------------------------- cartelle dei dati
DATA_ROOT = "/data/datadir"
# Le crea src/scripts/sync-env.sh col tuo utente: tienile uguali a SUBDIRS di quello script.
EXPECTED_DIRS = [
    "jellyfin/config",
    "jellyfin/cache",
    "media",
    "media/Film",
    "media/Serie TV",
    "media/Discoveries",
    "media/downloads",
    "seerr/config",
    "radarr/config",
    "sonarr/config",
    "prowlarr/config",
    "qbittorrent/config",
    "bazarr/config",
    "unmanic/config",
    "unmanic/cache",
    "recyclarr/config",
    "maintainerr",
    "beszel/data",
    "beszel/socket",
    "beszel/agent",
    "diun",
    "kuma",
    "ntfy",
    "photos",
    "panel",
    "pihole",
    "tailscale",
    "restore",
    "immich/upload",
    "immich/postgres",
    "immich/model-cache",
    "vaultwarden",
    "portainer",
    "backups/restic",
    "backups/vaultwarden",
]


def _setup() -> dict | None:
    """Cartelle dei dati mancanti o di root (le ha create Docker): il pannello consiglia di lanciare sync-env.sh."""
    if not os.path.isdir(DATA_ROOT):
        return None
    missing = [d for d in EXPECTED_DIRS if not os.path.isdir(os.path.join(DATA_ROOT, d))]
    root_owned = []
    # Jellyfin e gli strumenti di download girano col tuo utente, non come root: se la cartella e' di root
    # (l'ha creata Docker) non riescono a scriverci. media/Discoveries e' dove scrive JellyBridge.
    # Si controllano anche le sottocartelle: spesso e' la cartella di primo livello a essere dell'utente
    # e quella interna (config, log) di root, per un avvio precedente senza "user:".
    for d in ("jellyfin", "jellyfin/config", "jellyfin/config/log", "jellyfin/cache",
              "seerr", "seerr/config", "seerr/config/logs",
              "radarr", "radarr/config", "sonarr", "sonarr/config", "prowlarr", "prowlarr/config", "bazarr/config",
              "qbittorrent", "qbittorrent/config", "unmanic", "unmanic/config", "unmanic/cache",
              "recyclarr", "recyclarr/config", "maintainerr",
              "media/Discoveries", "media/downloads"):
        try:
            if os.stat(os.path.join(DATA_ROOT, d)).st_uid == 0:
                root_owned.append(d)
        except OSError:
            pass
    return {"missing": missing, "root_owned": root_owned}


# ---------------------------------------------------------------- insieme
def _fresh() -> bool:
    return _cache["data"] is not None and time.monotonic() - _cache["at"] < TTL


def collect(client) -> dict:
    if _fresh():
        return _cache["data"]
    # Un solo thread rinnova la lettura. Gli altri ricevono l'ultima disponibile senza aspettare; se non ce n'e'
    # ancora nessuna (primo accesso) aspettano il risultato.
    stale = _cache["data"]
    if not _refresh.acquire(blocking=stale is None):
        return stale
    try:
        if _fresh():
            return _cache["data"]
        host = _host()
        names = sorted({n for s in SERVICES.values() for n in s["containers"]})
        futures = [_pool.submit(_one, client, n, host["cores"]) for n in names]
        infos = dict(f.result() for f in futures)
        data = {
            "host": host,
            "setup": _setup(),
            "services": {sid: _service(meta, infos, host["cores"]) for sid, meta in SERVICES.items()},
        }
        _cache["data"], _cache["at"] = data, time.monotonic()
        return data
    finally:
        _refresh.release()
