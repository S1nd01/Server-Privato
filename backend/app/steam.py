"""Download remoto con SteamCMD.

Ogni download e' un container one-shot (immagine steamcmd) lanciato dal backend via socket Docker.
Il login Steam (account con Steam Guard) si fa UNA volta a mano, vedi docs/steamcmd.md:
il token resta nel volume di config e i download successivi usano solo il nome utente.
"""

import os
import re
from pathlib import Path

from docker.errors import APIError, NotFound
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .dockerutil import get_client

router = APIRouter(prefix="/api/steam", tags=["steam"])

IMAGE = os.environ.get("STEAMCMD_IMAGE", "steamcmd/steamcmd:latest")
# Percorsi sul HOST (servono al demone Docker per i bind mount dei container figli)
HOST_CONFIG = os.environ.get("HOST_STEAM_CONFIG_DIR", "")
HOST_GAMES = os.environ.get("HOST_STEAM_GAMES_DIR", "")
# Gli stessi percorsi visti da dentro il backend
LOCAL_GAMES = Path("/data/games")
LOCAL_CONFIG = Path("/data/steamcmd")

LABEL = "hs.steamcmd"
LOGIN_RE = re.compile(r"^[A-Za-z0-9_]{2,64}$")


class DownloadRequest(BaseModel):
    appid: int = Field(gt=0, description="AppID Steam (si vede nell'URL dello store)")
    platform: str = Field("windows", pattern="^(windows|linux|macos)$")
    login: str = Field("anonymous", description="'anonymous' o il tuo username Steam (login gia' fatto)")
    validate_files: bool = True


def _info(c) -> dict:
    c.reload()
    state = c.attrs["State"]
    return {
        "appid": int(c.labels.get("hs.appid", 0)),
        "platform": c.labels.get("hs.platform"),
        "status": c.status,
        "exit_code": state.get("ExitCode"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
    }


def _find(client, appid: int):
    try:
        return client.containers.get(f"steamcmd_{appid}")
    except NotFound:
        raise HTTPException(404, f"Nessun download per l'app {appid}")


@router.post("/downloads", status_code=202)
def start_download(req: DownloadRequest):
    if not HOST_CONFIG or not HOST_GAMES:
        raise HTTPException(500, "HOST_STEAM_CONFIG_DIR / HOST_STEAM_GAMES_DIR non configurati")
    if req.login != "anonymous" and not LOGIN_RE.match(req.login):
        raise HTTPException(400, "Username Steam non valido")

    client = get_client()
    # SteamCMD condivide la cartella di config: un solo download alla volta
    if client.containers.list(filters={"label": LABEL, "status": "running"}):
        raise HTTPException(409, "C'e' gia' un download in corso")

    name = f"steamcmd_{req.appid}"
    try:
        client.containers.get(name).remove(force=True)
    except NotFound:
        pass

    (LOCAL_GAMES / str(req.appid)).mkdir(parents=True, exist_ok=True)
    LOCAL_CONFIG.mkdir(parents=True, exist_ok=True)

    cmd = [
        "+@sSteamCmdForcePlatformType", req.platform,  # deve venire PRIMA del login
        "+force_install_dir", f"/data/games/{req.appid}",
        "+login", req.login,
        "+app_update", str(req.appid),
    ]
    if req.validate_files:
        cmd.append("validate")
    cmd.append("+quit")

    try:
        c = client.containers.run(
            IMAGE,
            cmd,
            name=name,
            detach=True,
            labels={LABEL: "1", "hs.appid": str(req.appid), "hs.platform": req.platform},
            volumes={
                HOST_CONFIG: {"bind": "/root/.local/share/Steam", "mode": "rw"},
                HOST_GAMES: {"bind": "/data/games", "mode": "rw"},
            },
        )
    except APIError as exc:
        raise HTTPException(502, f"Docker: {exc.explanation or exc}")
    return _info(c)


@router.get("/downloads")
def list_downloads():
    client = get_client()
    items = [_info(c) for c in client.containers.list(all=True, filters={"label": LABEL})]
    return sorted(items, key=lambda i: i["started_at"] or "", reverse=True)


@router.get("/downloads/{appid}")
def get_download(appid: int):
    return _info(_find(get_client(), appid))


@router.get("/downloads/{appid}/logs")
def download_logs(appid: int, tail: int = 40):
    c = _find(get_client(), appid)
    text = c.logs(tail=max(1, min(tail, 500))).decode(errors="replace")
    return {"appid": appid, "logs": text.replace("\r", "\n")}


@router.delete("/downloads/{appid}")
def cancel_download(appid: int):
    """Ferma (se in corso) e rimuove il container. I file gia' scaricati restano."""
    _find(get_client(), appid).remove(force=True)
    return {"ok": True}


@router.get("/library")
def library():
    """Giochi presenti sul disco, letti dai manifest di Steam (steamapps/appmanifest_*.acf)."""
    games = []
    if not LOCAL_GAMES.is_dir():
        return games
    for d in sorted(LOCAL_GAMES.iterdir()):
        if not (d.is_dir() and d.name.isdigit()):
            continue
        entry = {"appid": int(d.name), "name": None, "size_bytes": None, "installed": False}
        manifest = d / "steamapps" / f"appmanifest_{d.name}.acf"
        if manifest.is_file():
            text = manifest.read_text(errors="replace")
            if m := re.search(r'"name"\s+"([^"]*)"', text):
                entry["name"] = m.group(1)
            if m := re.search(r'"SizeOnDisk"\s+"(\d+)"', text):
                entry["size_bytes"] = int(m.group(1))
            if m := re.search(r'"StateFlags"\s+"(\d+)"', text):
                entry["installed"] = bool(int(m.group(1)) & 4)  # 4 = FullyInstalled
        games.append(entry)
    return games
