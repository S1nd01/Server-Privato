from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import anyio.to_thread

from docker.errors import DockerException, NotFound
from fastapi import Depends, FastAPI, HTTPException

from . import access, backup, stats, tailscale
from .auth import require_token
from .dockerutil import get_client as _client
from .services import MODES, SERVICES


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Le funzioni sincrone girano in un pool di thread (40 di serie). Il client Docker condiviso ha 16 connessioni
    # (dockerutil.py): piu' thread di cosi' resterebbero solo in coda sulla stessa connessione.
    anyio.to_thread.current_default_thread_limiter().total_tokens = 16
    backup.start_scheduler()
    yield
    backup.stop_scheduler()


app = FastAPI(
    title="Homeserver API",
    version="0.5.0",
    dependencies=[Depends(require_token)],
    lifespan=lifespan,
)
app.include_router(access.router)
app.include_router(tailscale.router)
app.include_router(backup.router)


def _snapshot(client) -> dict[str, str]:
    """Stato di tutti i container con UNA sola chiamata a Docker (prima ne serviva una per container)."""
    try:
        rows = client.api.containers(all=True)
    except DockerException as exc:
        raise HTTPException(503, f"Docker non raggiungibile: {exc}")
    states: dict[str, str] = {}
    for row in rows:
        for n in row.get("Names") or []:
            states[n.lstrip("/")] = row.get("State") or "unknown"
    return states


def _service_status(states: dict[str, str], sid: str) -> dict:
    meta = SERVICES[sid]
    containers = [{"name": n, "status": states.get(n, "not_created")} for n in meta["containers"]]
    statuses = {c["status"] for c in containers}
    if statuses == {"running"}:
        overall = "running"
    elif statuses <= {"not_created"}:
        overall = "not_created"
    elif "running" in statuses:
        overall = "partial"
    else:
        overall = "stopped"
    return {
        "id": sid,
        "name": meta["name"],
        "description": meta["description"],
        "scheme": meta["scheme"],
        "url_port": meta["url_port"],
        "path": meta.get("path", ""),
        "ts_only": meta.get("ts_only", False),
        "group": meta.get("group", ""),
        "can_stop": meta.get("allow_stop", True),
        "status": overall,
        "containers": containers,
    }


def _get_or_404(sid: str):
    if sid not in SERVICES:
        raise HTTPException(404, f"Servizio sconosciuto: {sid}")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/services")
def list_services():
    states = _snapshot(_client())
    return [_service_status(states, sid) for sid in SERVICES]


@app.get("/api/stats")
def get_stats():
    """Risorse del server e dei servizi (CPU, RAM, dischi, tempo di attivita', salute)."""
    return stats.collect(_client())


@app.get("/api/services/{sid}")
def get_service(sid: str):
    _get_or_404(sid)
    return _service_status(_snapshot(_client()), sid)


def _act(sid: str, action: str):
    _get_or_404(sid)
    meta = SERVICES[sid]
    if action != "start" and not meta.get("allow_stop", True):
        raise HTTPException(
            409,
            f"{meta['name']} non si ferma dal pannello: se ti stai collegando tramite quel servizio "
            "perderesti l'accesso. Usa il terminale sul server.",
        )
    client = _client()
    for name in meta["containers"]:
        try:
            c = client.containers.get(name)
        except NotFound:
            raise HTTPException(
                409, f"Container '{name}' non esiste: avvia prima con docker compose up -d"
            )
        getattr(c, action)()
    return _service_status(_snapshot(client), sid)


@app.post("/api/services/{sid}/start")
def start(sid: str):
    return _act(sid, "start")


@app.post("/api/services/{sid}/stop")
def stop(sid: str):
    return _act(sid, "stop")


@app.post("/api/services/{sid}/restart")
def restart(sid: str):
    return _act(sid, "restart")


# ---------------------------------------------------------------- modalita'
@app.get("/api/modes")
def list_modes():
    """Le modalita' definite in services.py (nessuna chiamata a Docker: lo stato "attiva" lo ricava il pannello dai servizi)."""
    return [
        {"id": mid, "name": m["name"], "description": m["description"], "action": m["action"], "services": m["services"]}
        for mid, m in MODES.items()
    ]


@app.post("/api/modes/{mid}/apply")
def apply_mode(mid: str):
    """Accende o spegne in blocco i gruppi della modalita'. I container non ancora creati si saltano; gli altri si fermano
    (o si avviano) a 4 per volta, cosi' un gruppo grosso non aspetta i 10 secondi di arresto di ogni container uno dopo l'altro."""
    if mid not in MODES:
        raise HTTPException(404, f"Modalita' sconosciuta: {mid}")
    mode = MODES[mid]
    action = mode["action"]
    client = _client()
    targets: list[str] = []
    for sid in mode["services"]:
        meta = SERVICES[sid]
        if action == "stop" and not meta.get("allow_stop", True):
            continue  # Tailscale: fermarlo farebbe perdere l'accesso
        targets.extend(meta["containers"])

    def one(name: str):
        try:
            c = client.containers.get(name)
            getattr(c, action)()
            return name, "ok"
        except NotFound:
            return name, "skipped"
        except DockerException as exc:
            return name, f"error: {exc}"

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="mode") as pool:
        results = list(pool.map(one, targets))
    errors = [f"{n} ({r[7:]})" for n, r in results if r.startswith("error")]
    if errors:
        raise HTTPException(502, "Alcuni container non hanno risposto: " + ", ".join(errors))
    states = _snapshot(client)
    return {
        "mode": mid,
        "skipped": [n for n, r in results if r == "skipped"],
        "services": [_service_status(states, sid) for sid in SERVICES],
    }
