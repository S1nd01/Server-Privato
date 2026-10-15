"""Uso di risorse: server (CPU, RAM, dischi, temperatura) e servizi (CPU, RAM, tempo di attivita', salute).

I numeri dei container vengono dal demone Docker (come `docker stats`). Ogni lettura costa circa un secondo
per container, quindi si fanno in parallelo e il risultato resta valido per qualche secondo: piu' schede aperte
non moltiplicano il carico sul server.
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
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "data": None}
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="stats")

# Cartelle viste da dentro il backend (montate da compose.yaml). Quelle sullo stesso disco vengono unite.
DISK_PATHS = [("Dati", "/data/datadir"), ("Giochi", "/data/games"), ("Foto", "/data/photos")]

_HEALTH_ORDER = {"unhealthy": 3, "starting": 2, "healthy": 1}


# ---------------------------------------------------------------- container
def cpu_percent(raw: dict, host_cores: int) -> float | None:
    """CPU come `docker stats`: 100 = un core intero (puo' superare 100 con piu' core)."""
    try:
        cpu, pre = raw["cpu_stats"], raw["precpu_stats"]
        cpu_delta = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
        sys_delta = cpu["system_cpu_usage"] - pre["system_cpu_usage"]
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
            raw = c.stats(stream=False)
            info["cpu_percent"] = cpu_percent(raw, host_cores)
            info["mem_bytes"] = mem_used(raw)
        except DockerException:
            pass
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
    "photos",
    "panel",
    "pihole",
    "tailscale",
    "restore",
    "steamcmd",
    "steam-games",
    "immich/upload",
    "immich/postgres",
    "immich/model-cache",
    "vaultwarden",
    "caddy/data",
    "caddy/config",
    "backups/restic",
    "backups/vaultwarden",
]


def _setup() -> dict | None:
    """Cartelle dei dati mancanti o di root (le ha create Docker): il pannello consiglia di lanciare sync-env.sh."""
    if not os.path.isdir(DATA_ROOT):
        return None
    missing = [d for d in EXPECTED_DIRS if not os.path.isdir(os.path.join(DATA_ROOT, d))]
    root_owned = []
    try:
        if os.stat(os.path.join(DATA_ROOT, "jellyfin")).st_uid == 0:  # Jellyfin gira col tuo utente, non come root
            root_owned.append("jellyfin")
    except OSError:
        pass
    return {"missing": missing, "root_owned": root_owned}


# ---------------------------------------------------------------- insieme
def collect(client) -> dict:
    with _lock:
        if _cache["data"] is not None and time.monotonic() - _cache["at"] < TTL:
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
