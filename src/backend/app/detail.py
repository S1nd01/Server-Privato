"""Pagina «Dettagli» di un servizio: contenitori (immagine, porte, cartelle, limiti), log e storico delle risorse.

Tre letture, tutte in sola lettura su Docker (il docker-gate lascia passare `GET /containers/<nome>/json` e `/logs` per i
container del pannello):

  GET /api/services/<id>/detail   informazioni statiche di ogni contenitore del gruppo
  GET /api/services/<id>/logs     ultime righe di log di un contenitore del gruppo (con le chiavi/password mascherate)
  GET /api/services/<id>/history  CPU e RAM nel tempo, dallo storico in memoria (history.py)

Non restituisce MAI le variabili d'ambiente dei container (contengono password e chiavi): da `attrs` si copiano solo i campi
elencati qui sotto.
"""
import re

from docker.errors import DockerException, NotFound
from fastapi import APIRouter, HTTPException, Query

from . import history
from .dockerutil import get_client
from .services import SERVICES

router = APIRouter(prefix="/api/services", tags=["dettagli"])

LOG_MAX_CHARS = 30000
MAX_MOUNTS = 25

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# chiave=valore, "chiave": "valore", Authorization: Bearer ... -> il valore diventa ***  (euristica: non sostituisce la prudenza)
_SECRET = re.compile(
    r"""(?ix)
    (\b(?:api[_-]?key|apikey|x-api-key|token|access[_-]?token|auth[_-]?token|password|passwd|pwd|secret|authkey|claim)\b
       ["']?\s*[:=]\s*["']?)
    ([^\s"'&,;}]+)
    """
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{8,})")


def mask_secrets(text: str) -> str:
    text = _SECRET.sub(lambda m: m.group(1) + "***", text)
    return _BEARER.sub(lambda m: m.group(1) + "***", text)


def _meta(sid: str) -> dict:
    if sid not in SERVICES:
        raise HTTPException(404, f"Servizio sconosciuto: {sid}")
    return SERVICES[sid]


def _ports(attrs: dict) -> list[dict]:
    out = []
    for container_port, binds in ((attrs.get("NetworkSettings") or {}).get("Ports") or {}).items():
        hosts = sorted({f"{b.get('HostIp') or '0.0.0.0'}:{b.get('HostPort')}" for b in (binds or []) if b.get("HostPort")})
        if hosts:
            out.append({"container": container_port, "host": hosts})
    return sorted(out, key=lambda p: p["container"])


def _mounts(attrs: dict) -> list[dict]:
    out = []
    for m in (attrs.get("Mounts") or [])[:MAX_MOUNTS]:
        kind = m.get("Type") or "?"
        out.append({
            "type": kind,
            "source": m.get("Source") if kind == "bind" else m.get("Name"),
            "destination": m.get("Destination"),
            "rw": bool(m.get("RW")),
        })
    return out


def container_detail(name: str, optional: bool, client=None) -> dict:
    client = client or get_client()
    try:
        c = client.containers.get(name)
    except NotFound:
        return {"name": name, "exists": False, "optional": optional}
    except DockerException as exc:
        raise HTTPException(503, f"Docker non raggiungibile: {exc}")
    a = c.attrs or {}
    state = a.get("State") or {}
    host_cfg = a.get("HostConfig") or {}
    health = state.get("Health") or {}
    restart = host_cfg.get("RestartPolicy") or {}
    image_id = str(a.get("Image") or "")
    return {
        "name": name,
        "exists": True,
        "optional": optional,
        "status": state.get("Status") or c.status,
        "image": (a.get("Config") or {}).get("Image"),
        "image_id": image_id.replace("sha256:", "")[:12] or None,
        "created": a.get("Created"),
        "started_at": state.get("StartedAt") if state.get("Running") else None,
        "finished_at": state.get("FinishedAt") if not state.get("Running") else None,
        "exit_code": state.get("ExitCode") if not state.get("Running") else None,
        "oom_killed": bool(state.get("OOMKilled")),
        "health": health.get("Status"),
        "health_failing": health.get("FailingStreak"),
        "restarts": int(a.get("RestartCount") or 0),
        "restart_policy": restart.get("Name") or None,
        "network_mode": host_cfg.get("NetworkMode"),
        "limit_mem": host_cfg.get("Memory") or None,                      # byte; None = nessun limite
        "limit_cpus": round((host_cfg.get("NanoCpus") or 0) / 1e9, 2) or None,
        "ports": _ports(a),
        "mounts": _mounts(a),
    }


@router.get("/{sid}/detail")
def detail(sid: str):
    meta = _meta(sid)
    optional = set(meta.get("optional", ()))
    client = get_client()
    containers = [container_detail(n, n in optional, client) for n in meta["containers"]]
    return {
        "id": sid,
        "compose_profile": meta.get("compose_profile"),
        "containers": [c for c in containers if c["exists"] or not c["optional"]],
    }


@router.get("/{sid}/logs")
def logs(sid: str, container: str | None = Query(None, max_length=128), tail: int = Query(100, ge=10, le=300)):
    meta = _meta(sid)
    name = container or meta["containers"][0]
    if name not in meta["containers"]:
        raise HTTPException(404, f"{name} non fa parte di questo servizio")
    try:
        raw = get_client().containers.get(name).logs(tail=tail, stdout=True, stderr=True, timestamps=False)
    except NotFound:
        raise HTTPException(409, f"Il container {name} non esiste ancora: niente log")
    except DockerException as exc:
        raise HTTPException(503, f"Docker non raggiungibile: {exc}")
    text = mask_secrets(_ANSI.sub("", raw.decode("utf-8", "replace")))
    truncated = len(text) > LOG_MAX_CHARS
    if truncated:
        text = text[-LOG_MAX_CHARS:]
    return {"container": name, "tail": tail, "truncated": truncated, "logs": text}


@router.get("/{sid}/history")
def history_series(sid: str, window: int = Query(900, ge=60, le=history.WINDOW_S)):
    _meta(sid)
    return history.series(sid, window)
