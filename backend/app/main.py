from docker.errors import NotFound
from fastapi import Depends, FastAPI, HTTPException

from . import steam, wireguard
from .auth import require_token
from .dockerutil import get_client as _client
from .services import SERVICES

app = FastAPI(
    title="Homeserver API",
    version="0.2.0",
    dependencies=[Depends(require_token)],
)
app.include_router(steam.router)
app.include_router(wireguard.router)


def _container_state(client, name: str) -> dict:
    try:
        c = client.containers.get(name)
        return {"name": name, "status": c.status}
    except NotFound:
        return {"name": name, "status": "not_created"}


def _service_status(client, sid: str) -> dict:
    meta = SERVICES[sid]
    containers = [_container_state(client, n) for n in meta["containers"]]
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
    client = _client()
    return [_service_status(client, sid) for sid in SERVICES]


@app.get("/api/services/{sid}")
def get_service(sid: str):
    _get_or_404(sid)
    return _service_status(_client(), sid)


def _act(sid: str, action: str):
    _get_or_404(sid)
    client = _client()
    for name in SERVICES[sid]["containers"]:
        try:
            c = client.containers.get(name)
        except NotFound:
            raise HTTPException(
                409, f"Container '{name}' non esiste: avvia prima con docker compose up -d"
            )
        getattr(c, action)()
    return _service_status(client, sid)


@app.post("/api/services/{sid}/start")
def start(sid: str):
    return _act(sid, "start")


@app.post("/api/services/{sid}/stop")
def stop(sid: str):
    return _act(sid, "stop")


@app.post("/api/services/{sid}/restart")
def restart(sid: str):
    return _act(sid, "restart")
