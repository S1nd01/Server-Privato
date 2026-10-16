"""Backup con Restic.

Ogni operazione (init, backup, forget, check) e' un container one-shot dell'immagine restic lanciato dal
backend via socket Docker, come per SteamCMD. L'archivio e' cifrato da restic (AES-256 in modalita'
counter + Poly1305-AES) con la passphrase del file RESTIC_PASSWORD_FILE.

Dall'API non arriva nessun percorso ne' argomento: `kind` e' un valore di un elenco fisso, tutto il resto
viene dal .env. Una pianificazione giornaliera (RESTIC_SCHEDULE=HH:MM) gira in un thread del backend.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import docker
from docker.errors import APIError, ContainerError, NotFound
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .dockerutil import get_client

log = logging.getLogger("homeserver.backup")
router = APIRouter(prefix="/api/backup", tags=["backup"])

LABEL = "hs.restic"
JOB_NAME = "restic_job"
HOST_TAG = "homeserver"  # nome host fisso: l'hostname di un container cambia a ogni avvio e romperebbe forget
CACHE_VOLUME = "hs_restic_cache"

# Percorsi visti da dentro il backend (montati da compose.yaml)
LOCAL_DATA = Path("/data/datadir")
LOCAL_REPO = Path("/data/restic-repo")
LOCAL_PASS = Path("/data/restic-pass")
LOCAL_PHOTOS = Path("/data/photos")
STATE_FILE = Path("/data/panel/state.json")

# Cosa si salva (relativo a DATA_DIR). Il database di Immich NON e' qui: la cartella di Postgres in uso non
# e' copiabile in modo coerente; Immich scrive da solo i dump del database in immich/upload/backups.
SOURCES = [
    "vaultwarden", "immich/upload", "pihole", "jellyfin/config",
    "seerr/config", "radarr/config", "sonarr/config", "prowlarr/config", "qbittorrent/config",
]
EXCLUDES = [
    "seerr/config/logs",
    "radarr/config/logs",
    "radarr/config/MediaCover",      # locandine: si riscaricano
    "sonarr/config/logs",
    "sonarr/config/MediaCover",
    "prowlarr/config/logs",
    "qbittorrent/config/qBittorrent/logs",
    "immich/upload/thumbs",          # rigenerabili
    "immich/upload/encoded-video",   # rigenerabili
    "vaultwarden/icon_cache",
    "vaultwarden/tmp",
    "jellyfin/config/log",
]

_lock = threading.Lock()


class Busy(HTTPException):
    def __init__(self):
        super().__init__(409, "C'è già un'operazione di backup in corso")


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "")))
    except ValueError:
        return default


def _cfg() -> dict:
    return {
        "image": os.environ.get("RESTIC_IMAGE") or "restic/restic:latest",
        "repo": os.environ.get("RESTIC_REPO_DIR", ""),
        "password": os.environ.get("RESTIC_PASSWORD_FILE", ""),
        "data": os.environ.get("HOST_DATA_DIR", ""),
        "photos": os.environ.get("HOST_PHOTOS_DIR", ""),
        "schedule": os.environ.get("RESTIC_SCHEDULE", "").strip(),
        "keep": {
            "daily": _int_env("RESTIC_KEEP_DAILY", 7),
            "weekly": _int_env("RESTIC_KEEP_WEEKLY", 4),
            "monthly": _int_env("RESTIC_KEEP_MONTHLY", 6),
        },
    }


def _problems(cfg: dict) -> list[str]:
    """Cosa manca per poter usare il backup, in parole che dicono come rimediare."""
    p = []
    if not cfg["repo"]:
        p.append("RESTIC_REPO_DIR non è impostato nel .env")
    elif not LOCAL_REPO.is_dir():
        p.append("La cartella dell'archivio non esiste: creala e riavvia il backend")
    if not cfg["password"]:
        p.append("RESTIC_PASSWORD_FILE non è impostato nel .env")
    elif not (LOCAL_PASS.is_file() and LOCAL_PASS.stat().st_size > 0):
        p.append("Il file della passphrase non esiste o è vuoto")
    if not cfg["data"]:
        p.append("HOST_DATA_DIR manca: controlla compose.yaml")
    return p


def _initialized() -> bool:
    return (LOCAL_REPO / "config").is_file()


def _existing_sources() -> list[str]:
    return [s for s in SOURCES if (LOCAL_DATA / s).exists()]


def _last_backup_at() -> str | None:
    """Data dell'ultimo snapshot, dalla data dei file in <archivio>/snapshots (senza avviare restic)."""
    try:
        newest = max((p.stat().st_mtime for p in (LOCAL_REPO / "snapshots").rglob("*") if p.is_file()), default=None)
    except OSError:
        return None
    return datetime.fromtimestamp(newest, tz=timezone.utc).isoformat() if newest else None


# ---------- comandi restic ----------

def build_backup_cmd(paths: list[str], photos: bool) -> list[str]:
    cmd = ["-r", "/repo", "backup", "--host", HOST_TAG, "--tag", HOST_TAG, "--exclude-caches"]
    for e in EXCLUDES:
        cmd += ["--exclude", f"/source/{e}"]
    cmd += [f"/source/{p}" for p in paths]
    if photos:
        cmd.append("/photos")
    return cmd


def build_forget_cmd(keep: dict) -> list[str]:
    return [
        "-r", "/repo", "forget", "--prune",
        "--host", HOST_TAG, "--tag", HOST_TAG, "--group-by", "host",
        "--keep-daily", str(keep["daily"]),
        "--keep-weekly", str(keep["weekly"]),
        "--keep-monthly", str(keep["monthly"]),
    ]


def _env() -> dict:
    return {"RESTIC_PASSWORD_FILE": "/run/restic-pass", "RESTIC_CACHE_DIR": "/cache", "TZ": os.environ.get("TZ") or "UTC"}


def _base_volumes(cfg: dict) -> dict:
    return {
        cfg["repo"]: {"bind": "/repo", "mode": "rw"},
        cfg["password"]: {"bind": "/run/restic-pass", "mode": "ro"},
        CACHE_VOLUME: {"bind": "/cache", "mode": "rw"},
    }


# ---------- lavori ----------

def _result(kind: str | None, status: str, code: int | None) -> str:
    if status == "running":
        return "running"
    if status == "exited":
        if code == 0:
            return "ok"
        if code == 3 and kind == "backup":
            return "warning"  # snapshot creato, ma alcuni file non erano leggibili
        return "failed"
    return "failed"


def _job_info(c) -> dict:
    c.reload()
    state = c.attrs["State"]
    kind = c.labels.get("hs.kind")
    return {
        "kind": kind,
        "status": c.status,
        "result": _result(kind, c.status, state.get("ExitCode")),
        "exit_code": state.get("ExitCode"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
    }


def _current_job(client) -> dict | None:
    try:
        return _job_info(client.containers.get(JOB_NAME))
    except NotFound:
        return None


def _vaultwarden_dump(client) -> list[str]:
    """Copia coerente del database di Vaultwarden prima del backup. Se non riesce, il backup parte lo stesso."""
    try:
        c = client.containers.get("vaultwarden")
        if c.status != "running":
            return ["Vaultwarden è fermo: salvo i file così come sono"]
        code = c.exec_run(["/vaultwarden", "backup"]).exit_code
        if code != 0:
            return ["Copia coerente di Vaultwarden non riuscita: salvo i file così come sono"]
    except Exception:  # noqa: BLE001 - e' un passaggio facoltativo
        return ["Vaultwarden non raggiungibile: salvo i file così come sono"]
    return []


def start_job(client, kind: str) -> dict:
    cfg = _cfg()
    with _lock:
        problems = _problems(cfg)
        if problems:
            raise HTTPException(409, "Backup non configurato: " + "; ".join(problems))
        initialized = _initialized()
        if kind == "init" and initialized:
            raise HTTPException(409, "L'archivio esiste già")
        if kind != "init" and not initialized:
            raise HTTPException(409, "Prepara prima l'archivio")
        if client.containers.list(filters={"label": LABEL, "status": "running"}):
            raise Busy()

        warnings: list[str] = []
        with_data = photos = False
        if kind == "init":
            cmd = ["-r", "/repo", "init"]
        elif kind == "backup":
            paths = _existing_sources()
            photos = bool(cfg["photos"]) and LOCAL_PHOTOS.is_dir()
            if not paths and not photos:
                raise HTTPException(409, "Non c'è ancora nulla da salvare: avvia prima almeno un servizio")
            with_data = bool(paths)
            warnings = _vaultwarden_dump(client)
            cmd = build_backup_cmd(paths, photos)
        elif kind == "forget":
            cmd = build_forget_cmd(cfg["keep"])
        else:
            cmd = ["-r", "/repo", "check"]

        vols = _base_volumes(cfg)
        if with_data:
            vols[cfg["data"]] = {"bind": "/source", "mode": "ro"}
        if photos:
            vols[cfg["photos"]] = {"bind": "/photos", "mode": "ro"}

        try:
            client.containers.get(JOB_NAME).remove(force=True)
        except NotFound:
            pass
        try:
            c = client.containers.run(
                cfg["image"], cmd, name=JOB_NAME, detach=True,
                labels={LABEL: "1", "hs.kind": kind}, environment=_env(), volumes=vols,
            )
        except APIError as exc:
            raise HTTPException(502, f"Docker: {exc.explanation or exc}")
        return {**_job_info(c), "warnings": warnings}


class JobRequest(BaseModel):
    kind: Literal["init", "backup", "forget", "check"]


@router.post("/jobs", status_code=202)
def create_job(req: JobRequest):
    return start_job(get_client(), req.kind)


@router.get("/jobs/current/logs")
def job_logs(tail: int = 60):
    try:
        c = get_client().containers.get(JOB_NAME)
    except NotFound:
        raise HTTPException(404, "Nessuna operazione di backup finora")
    text = c.logs(tail=max(1, min(tail, 500))).decode(errors="replace")
    return {"logs": text.replace("\r", "\n")}


@router.get("/status")
def status():
    cfg = _cfg()
    problems = _problems(cfg)
    job = None
    try:
        job = _current_job(get_client())
    except Exception:  # noqa: BLE001 - lo stato si mostra anche se Docker non risponde
        pass
    sources = [{"path": s, "exists": (LOCAL_DATA / s).exists()} for s in SOURCES]
    if cfg["photos"]:
        sources.append({"path": "Foto esterne", "exists": LOCAL_PHOTOS.is_dir()})
    return {
        "configured": not problems,
        "problems": problems,
        "initialized": not problems and _initialized(),
        "repo": cfg["repo"] or None,
        "schedule": cfg["schedule"] or None,
        "keep": cfg["keep"],
        "last_backup_at": None if problems else _last_backup_at(),
        "job": job,
        "sources": sources,
    }


def _text(value) -> str:
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    return (value or "").strip()


def parse_snapshots(raw) -> list[dict]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        raise HTTPException(502, "Risposta di restic non valida")
    if not isinstance(data, list):
        data = []
    snaps = []
    for s in data:
        summary = s.get("summary") or {}
        snaps.append({
            "id": s.get("short_id") or (s.get("id") or "")[:8],
            "time": s.get("time"),
            "paths": s.get("paths") or [],
            "tags": s.get("tags") or [],
            "added_bytes": summary.get("data_added"),
            "total_bytes": summary.get("total_bytes_processed"),
        })
    snaps.sort(key=lambda x: x["time"] or "", reverse=True)
    return snaps[:20]


@router.get("/snapshots")
def snapshots():
    cfg = _cfg()
    problems = _problems(cfg)
    if problems:
        raise HTTPException(409, "Backup non configurato: " + "; ".join(problems))
    if not _initialized():
        raise HTTPException(409, "Prepara prima l'archivio")
    client = get_client()
    if _current_job(client) and _current_job(client)["status"] == "running":
        raise HTTPException(409, "C'è un'operazione in corso: riprova quando finisce")
    try:
        out = client.containers.run(
            cfg["image"], ["-r", "/repo", "snapshots", "--json", "--host", HOST_TAG],
            detach=False, remove=True, stdout=True, stderr=False,
            environment=_env(), volumes=_base_volumes(cfg),
        )
    except ContainerError as exc:
        raise HTTPException(502, f"restic: {_text(exc.stderr)[-300:] or 'errore sconosciuto'}")
    except APIError as exc:
        raise HTTPException(502, f"Docker: {exc.explanation or exc}")
    return parse_snapshots(out)


# ---------- pianificazione ----------

def should_run(now: datetime, schedule: str, last_run_date: str | None) -> bool:
    """True se e' passata l'ora pianificata di oggi e oggi il backup non e' ancora partito.

    Se il server era spento all'ora indicata, il backup parte appena torna acceso (stesso giorno).
    """
    try:
        hh, mm = (int(x) for x in schedule.split(":"))
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    except ValueError:
        return False
    return now >= due and last_run_date != now.date().isoformat()


def _load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except OSError:
        log.warning("Non riesco a salvare lo stato della pianificazione in %s", STATE_FILE)


_stop = threading.Event()
_thread: threading.Thread | None = None


def _wait_job(client, max_hours: float = 12) -> dict | None:
    for _ in range(int(max_hours * 360)):  # controllo ogni 10 s
        if _stop.is_set():
            return None
        info = _current_job(client)
        if info is None or info["status"] != "running":
            return info
        _stop.wait(10)
    return None


def _tick(now: datetime | None = None) -> None:
    cfg = _cfg()
    if _problems(cfg) or not _initialized():
        return
    now = now or datetime.now()
    state = _load_state()
    if not should_run(now, cfg["schedule"], state.get("last_run_date")):
        return
    client = docker.from_env()
    try:
        start_job(client, "backup")
    except Busy:
        return  # riprovo al prossimo controllo
    except HTTPException as exc:
        log.warning("Backup pianificato non avviato: %s", exc.detail)
    state["last_run_date"] = now.date().isoformat()  # in ogni altro caso non ritento fino a domani
    _save_state(state)
    info = _wait_job(client)
    if info and info["result"] in ("ok", "warning"):
        try:
            start_job(client, "forget")
            _wait_job(client)
        except HTTPException as exc:
            log.warning("Pulizia pianificata non avviata: %s", exc.detail)


def _loop() -> None:
    if _stop.wait(60):  # lascio il tempo a Docker di essere pronto
        return
    while not _stop.is_set():
        try:
            _tick()
        except Exception:  # noqa: BLE001
            log.exception("Errore nella pianificazione del backup")
        if _stop.wait(60):
            return


def start_scheduler() -> None:
    global _thread
    if not _cfg()["schedule"]:
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="backup-scheduler", daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()
