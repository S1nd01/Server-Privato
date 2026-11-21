"""Backup con Restic.

Ogni operazione (init, backup, forget, check) e' un container one-shot dell'immagine restic lanciato dal
backend via socket Docker. L'archivio e' cifrato da restic (AES-256 in modalita'
counter + Poly1305-AES) con la passphrase del file RESTIC_PASSWORD_FILE.

Dall'API non arriva nessun percorso ne' argomento: `kind` e' un valore di un elenco fisso, tutto il resto
viene dal .env.

Il backup parte SOLO su richiesta di un admin (POST /api/backup/jobs): non c'e' nessuna pianificazione.

Disco esterno (BACKUP_DISK_DIR): l'archivio sta su un disco che si collega solo quando serve. Un disco non collegato non
deve MAI far scrivere l'archivio sul disco di sistema (Docker crea da solo i percorsi che non esistono): prima di ogni
operazione si controlla il file marcatore `.homeserver-backup`, che sta solo sul disco e lo crea backup-disco.sh.
Il backend vede i montaggi fatti dopo il suo avvio perche' BACKUP_MOUNT_PARENT e' montata con propagazione rslave.
"""

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal

from docker.errors import APIError, ContainerError, NotFound
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require_admin
from .dockerutil import get_client

log = logging.getLogger("homeserver.backup")
router = APIRouter(prefix="/api/backup", tags=["backup"])

LABEL = "hs.restic"
JOB_NAME = "restic_job"
HOST_TAG = "homeserver"  # nome host fisso: l'hostname di un container cambia a ogni avvio e romperebbe forget
CACHE_VOLUME = "hs_restic_cache"

# Percorsi visti da dentro il backend (montati da compose.yaml)
LOCAL_DATA = Path("/data/datadir")
LOCAL_PARENT = Path("/data/backup-parent")   # BACKUP_MOUNT_PARENT dell'host, montata in sola lettura con propagazione rslave
LOCAL_PASS = Path("/data/restic-pass")
LOCAL_PHOTOS = Path("/data/photos")
STATE_FILE = Path("/data/panel/backup.json")   # ultima copia riuscita: a disco scollegato l'archivio non si puo' leggere
MARKER = ".homeserver-backup"                  # sta solo sul disco di backup (lo crea src/scripts/backup-disco.sh)

# Cosa si salva (relativo a DATA_DIR). Il database di Immich NON e' qui: la cartella di Postgres in uso non
# e' copiabile in modo coerente; Immich scrive da solo i dump del database in immich/upload/backups.
# Le cartelle che non esistono si saltano (_existing_sources). I database SQLite dei servizi si copiano "a caldo": solo per
# Vaultwarden c'e' la copia coerente (_vaultwarden_dump); per gli altri e' una copia di file in uso, di norma ripristinabile.
SOURCES = [
    "vaultwarden", "immich/upload", "pihole", "jellyfin/config",
    "seerr/config", "radarr/config", "sonarr/config", "prowlarr/config", "qbittorrent/config",
    "recyclarr/config", "maintainerr",
    "bazarr/config",    # impostazioni e cronologia dei sottotitoli
    "kuma",             # Uptime Kuma: monitor e notifiche
    "ntfy",             # utenti e argomenti (user.db); la cache dei messaggi e' esclusa sotto
    "beszel/data",      # hub Beszel: utenti, sistemi, avvisi
    "unmanic/config",   # regole di compressione (la cartella cache temporanea NON si salva)
    "panel",            # stato del pannello (servizi spenti, ultima copia; in futuro gli utenti)
    "tailscale",        # identita' del server nella rete Tailscale: ripristinarla tiene lo stesso indirizzo .ts.net
]
EXCLUDES = [
    "ntfy/cache.db*",                # messaggi in coda: si rigenerano
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
    "maintainerr/logs",
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
        "disk": os.environ.get("BACKUP_DISK_DIR", "").strip(),   # vuoto = archivio locale, senza disco da controllare
        "parent": os.environ.get("BACKUP_MOUNT_PARENT", "").strip() or (os.environ.get("HOST_DATA_DIR", "").rstrip("/") + "/backups"),
        "warn_days": _int_env("BACKUP_WARN_DAYS", 14),
        "keep": {
            "daily": _int_env("RESTIC_KEEP_DAILY", 7),
            "weekly": _int_env("RESTIC_KEEP_WEEKLY", 4),
            "monthly": _int_env("RESTIC_KEEP_MONTHLY", 6),
        },
    }


def _host_path(value: str) -> PurePosixPath | None:
    """Percorso assoluto, senza '..' e senza '//' strani; None se non e' accettabile."""
    path = PurePosixPath(value)
    if not value.startswith("/") or ".." in path.parts or str(path) == "/":
        return None
    return path


def _resolve(cfg: dict) -> dict:
    """Dove stanno, VISTI DAL BACKEND, l'archivio e (se c'e') il disco: error dice cosa non torna nel .env."""
    out = {"repo": None, "disk": None, "error": None}
    parent, repo, disk = _host_path(cfg["parent"]), _host_path(cfg["repo"]), (_host_path(cfg["disk"]) if cfg["disk"] else None)
    if parent is None:
        out["error"] = "BACKUP_MOUNT_PARENT non è un percorso assoluto valido"
        return out
    if repo is None:
        out["error"] = "RESTIC_REPO_DIR non è un percorso assoluto valido"
        return out
    if cfg["disk"] and disk is None:
        out["error"] = "BACKUP_DISK_DIR non è un percorso assoluto valido"
        return out
    try:
        out["repo"] = LOCAL_PARENT / repo.relative_to(parent)
        if repo == parent:
            raise ValueError
        if disk is not None:
            out["disk"] = LOCAL_PARENT / disk.relative_to(parent)
            if disk == parent:
                raise ValueError
            if repo == disk:
                raise ValueError
            repo.relative_to(disk)
    except ValueError:
        out["repo"] = out["disk"] = None
        out["error"] = ("RESTIC_REPO_DIR deve stare dentro BACKUP_DISK_DIR, e questo dentro BACKUP_MOUNT_PARENT: rilancia ./src/scripts/backup-disco.sh"
                        if disk is not None else "RESTIC_REPO_DIR deve stare dentro BACKUP_MOUNT_PARENT")
    return out


def _disk_present(res: dict) -> bool:
    """Con un disco configurato: c'e' il file marcatore? (Una cartella vuota creata da Docker NON lo ha.)"""
    return res["disk"] is not None and (res["disk"] / MARKER).is_file()


def _problems(cfg: dict) -> list[str]:
    """Cosa manca per poter usare il backup, in parole che dicono come rimediare."""
    p = []
    if not cfg["repo"]:
        p.append("RESTIC_REPO_DIR non è impostato nel .env")
    else:
        res = _resolve(cfg)
        if res["error"]:
            p.append(res["error"])
        elif res["disk"] is None or _disk_present(res):   # a disco scollegato la cartella e' assente per forza: non e' un errore di configurazione
            if not res["repo"].is_dir():
                p.append("La cartella dell'archivio non esiste" + (" sul disco: rilancia ./src/scripts/backup-disco.sh" if res["disk"] else ": creala e riavvia il backend"))
    if not cfg["password"]:
        p.append("RESTIC_PASSWORD_FILE non è impostato nel .env")
    elif not (LOCAL_PASS.is_file() and LOCAL_PASS.stat().st_size > 0):
        p.append("Il file della passphrase non esiste o è vuoto")
    if not cfg["data"]:
        p.append("HOST_DATA_DIR manca: controlla compose.yaml")
    return p


def _disk_info(cfg: dict) -> dict | None:
    """None = archivio locale. Altrimenti: dove deve stare il disco e se in questo momento c'e'."""
    if not cfg["disk"]:
        return None
    return {"path": cfg["disk"], "present": _disk_present(_resolve(cfg))}


def _require_disk(cfg: dict) -> None:
    info = _disk_info(cfg)
    if info is not None and not info["present"]:
        raise HTTPException(409, f"Il disco di backup non è collegato (lo cerco in {info['path']}): collegalo e riprova")


def _initialized(cfg: dict) -> bool:
    repo = _resolve(cfg)["repo"]
    return repo is not None and (repo / "config").is_file()


def _existing_sources() -> list[str]:
    return [s for s in SOURCES if (LOCAL_DATA / s).exists()]


def _parse_ts(value) -> datetime | None:
    """Data/ora di Docker ('2026-11-07T17:03:12.123456789Z') o ISO: sempre con fuso, frazione di secondo troncata."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().replace("Z", "+00:00")
    m = re.match(r"^(.*?\.\d{1,6})\d*(.*)$", v)
    if m:
        v = m.group(1) + m.group(2)
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _repo_last_backup(cfg: dict) -> datetime | None:
    """Data dell'ultimo snapshot, dalla data dei file in <archivio>/snapshots (senza avviare restic)."""
    repo = _resolve(cfg)["repo"]
    if repo is None:
        return None
    try:
        newest = max((p.stat().st_mtime for p in (repo / "snapshots").rglob("*") if p.is_file()), default=None)
    except OSError:
        return None
    return datetime.fromtimestamp(newest, tz=timezone.utc) if newest else None


def _remember_last(job: dict | None) -> None:
    """Annota l'ultimo backup riuscito: dopo un'operazione di pulizia il lavoro precedente sparisce, e a disco
    scollegato non c'e' l'archivio da cui leggere la data."""
    if not job or job.get("kind") != "backup" or job.get("result") not in ("ok", "warning"):
        return
    finished = _parse_ts(job.get("finished_at"))
    if finished is None or finished.year < 2000:   # Docker mette 0001-01-01 se non e' ancora finito
        return
    state = _load_state()
    known = _parse_ts(state.get("last_backup_at"))
    if known is None or finished > known:
        state["last_backup_at"] = finished.isoformat()
        _save_state(state)


def _last_backup_at(cfg: dict) -> datetime | None:
    cands = [_parse_ts(_load_state().get("last_backup_at"))]
    info = _disk_info(cfg)
    if info is None or info["present"]:
        cands.append(_repo_last_backup(cfg))
    cands = [c for c in cands if c]
    return max(cands) if cands else None


# ---------- comandi restic ----------

def build_backup_cmd(paths: list[str], photos: bool) -> list[str]:
    # --read-concurrency 2: legge meno file in parallelo (il valore predefinito carica di piu' disco e CPU)
    cmd = ["-r", "/repo", "backup", "--host", HOST_TAG, "--tag", HOST_TAG, "--exclude-caches", "--read-concurrency", "2"]
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
    # GOMAXPROCS: restic usa al massimo 2 core, il resto resta ai servizi
    return {"RESTIC_PASSWORD_FILE": "/run/restic-pass", "RESTIC_CACHE_DIR": "/cache", "TZ": os.environ.get("TZ") or "UTC", "GOMAXPROCS": "2"}


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
        _require_disk(cfg)   # PRIMA di qualunque cosa: senza disco Docker creerebbe il percorso dell'archivio sul disco di sistema
        initialized = _initialized(cfg)
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
                cpu_shares=256,  # priorita' bassa: se il server e' occupato i servizi passano avanti (default 1024)
            )
        except APIError as exc:
            raise HTTPException(502, f"Docker: {exc.explanation or exc}")
        return {**_job_info(c), "warnings": warnings}


class JobRequest(BaseModel):
    kind: Literal["init", "backup", "forget", "check"]


@router.post("/jobs", status_code=202, dependencies=[Depends(require_admin)])   # solo l'admin: init, backup, pulizia, controllo
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
    _remember_last(job)
    disk = _disk_info(cfg)
    usable = not problems and (disk is None or disk["present"])
    sources = [{"path": s, "exists": (LOCAL_DATA / s).exists()} for s in SOURCES]
    if cfg["photos"]:
        sources.append({"path": "Foto esterne", "exists": LOCAL_PHOTOS.is_dir()})
    last = None if problems else _last_backup_at(cfg)
    age = (datetime.now(timezone.utc) - last).days if last else None
    initialized = _initialized(cfg) if usable else None   # a disco scollegato non si sa
    return {
        "configured": not problems,
        "problems": problems,
        "initialized": initialized,
        "repo": cfg["repo"] or None,
        "disk": disk,
        "manual_only": True,
        "keep": cfg["keep"],
        "last_backup_at": last.isoformat() if last else None,
        "age_days": age,
        "stale": bool(cfg["warn_days"] and not problems and initialized is not False and (age is None or age >= cfg["warn_days"])),
        "warn_days": cfg["warn_days"],
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
    _require_disk(cfg)
    if not _initialized(cfg):
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


# ---------- stato (ultima copia riuscita) ----------

def _load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(STATE_FILE)
    except OSError:
        log.warning("Non riesco a salvare lo stato del backup in %s", STATE_FILE)
