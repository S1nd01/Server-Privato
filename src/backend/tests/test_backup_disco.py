"""Backup su disco esterno, solo su richiesta dell'admin. Senza Docker: il client e' finto.

Da src/backend:  python -m pytest tests -q      (servono fastapi, docker, httpx e pytest)
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from docker.errors import NotFound
from fastapi.testclient import TestClient

from app import backup
from app.main import app

HOST_PARENT = "/media/u"
HOST_DISK = "/media/u/BACKUP"
HOST_REPO = "/media/u/BACKUP/homeserver-restic"


class FakeContainer:
    def __init__(self, kind="backup", exit_code=0, finished="2026-11-07T17:03:12.123456789Z"):
        self.status, self.labels = "exited", {"hs.kind": kind}
        self.attrs = {"State": {"ExitCode": exit_code, "StartedAt": finished, "FinishedAt": finished}}

    def reload(self):
        pass

    def remove(self, force=False):
        pass


class FakeContainers:
    def __init__(self):
        self.runs, self.job = [], None

    def list(self, filters=None):
        return []

    def get(self, name):
        if name == backup.JOB_NAME and self.job:
            return self.job
        raise NotFound("no")

    def run(self, image, cmd, **kw):
        self.runs.append({"image": image, "cmd": cmd, **kw})
        return FakeContainer(kind=kw["labels"]["hs.kind"])


class FakeClient:
    def __init__(self):
        self.containers = FakeContainers()


@pytest.fixture
def env(tmp_path, monkeypatch):
    local_parent = tmp_path / "parent"
    (local_parent / "BACKUP").mkdir(parents=True)
    (tmp_path / "pass").write_text("x" * 40)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(backup, "LOCAL_PARENT", local_parent)
    monkeypatch.setattr(backup, "LOCAL_PASS", tmp_path / "pass")
    monkeypatch.setattr(backup, "LOCAL_DATA", tmp_path / "data")
    (tmp_path / "data" / "vaultwarden").mkdir()
    monkeypatch.setattr(backup, "LOCAL_PHOTOS", tmp_path / "nophotos")
    monkeypatch.setattr(backup, "STATE_FILE", tmp_path / "panel" / "backup.json")
    for k, v in {"HOST_DATA_DIR": "/srv/data", "HOST_PHOTOS_DIR": "/srv/data/photos", "RESTIC_REPO_DIR": HOST_REPO,
                 "RESTIC_PASSWORD_FILE": "/home/u/.restic-pass", "BACKUP_DISK_DIR": HOST_DISK,
                 "BACKUP_MOUNT_PARENT": HOST_PARENT}.items():
        monkeypatch.setenv(k, v)
    for k in ("API_TOKEN", "API_TOKEN_HASH", "BACKUP_WARN_DAYS", "RESTIC_SCHEDULE"):
        monkeypatch.delenv(k, raising=False)
    client = FakeClient()
    monkeypatch.setattr(backup, "get_client", lambda: client)
    return type("E", (), {"local": local_parent / "BACKUP", "client": client, "tmp": tmp_path, "mp": monkeypatch})


def plug(env, initialized=True):
    """Simula il disco collegato: marcatore, cartella dell'archivio e (se serve) il file config di restic."""
    (env.local / backup.MARKER).write_text("x")
    (env.local / "homeserver-restic").mkdir(exist_ok=True)
    if initialized:
        (env.local / "homeserver-restic" / "config").write_text("x")


api = TestClient(app)


def test_senza_disco_nessuna_operazione_e_docker_non_viene_toccato(env):
    for kind in ("init", "backup", "forget", "check"):
        r = api.post("/api/backup/jobs", json={"kind": kind})
        assert r.status_code == 409 and "non è collegato" in r.json()["detail"], (kind, r.text)
    assert env.client.containers.runs == []   # nessun container: Docker non ha potuto creare nulla sul disco di sistema


def test_cartella_vuota_senza_marcatore_non_vale_come_disco(env):
    """Docker crea la cartella vuota se il disco manca: la cartella c'e', il marcatore no."""
    (env.local / "homeserver-restic").mkdir()
    (env.local / "homeserver-restic" / "config").write_text("x")
    r = api.post("/api/backup/jobs", json={"kind": "backup"})
    assert r.status_code == 409 and env.client.containers.runs == []


def test_con_disco_il_backup_parte_con_i_percorsi_host(env):
    plug(env)
    r = api.post("/api/backup/jobs", json={"kind": "backup"})
    assert r.status_code == 202, r.text
    run = env.client.containers.runs[0]
    assert run["volumes"][HOST_REPO] == {"bind": "/repo", "mode": "rw"}       # percorso dell'HOST, non quello visto dal backend
    assert run["volumes"]["/srv/data"] == {"bind": "/source", "mode": "ro"}


def test_il_disco_si_puo_collegare_a_caldo(env):
    r = api.post("/api/backup/jobs", json={"kind": "backup"})
    assert r.status_code == 409
    plug(env)   # senza riavviare nulla
    assert api.post("/api/backup/jobs", json={"kind": "backup"}).status_code == 202


def test_stato_disco_scollegato(env):
    st = api.get("/api/backup/status").json()
    assert st["configured"] is True and st["problems"] == []
    assert st["disk"] == {"path": HOST_DISK, "present": False}
    assert st["initialized"] is None and st["manual_only"] is True
    assert "schedule" not in st


def test_stato_disco_collegato(env):
    plug(env)
    st = api.get("/api/backup/status").json()
    assert st["disk"]["present"] is True and st["initialized"] is True


def test_archivio_non_inizializzato_con_disco_collegato(env):
    plug(env, initialized=False)
    st = api.get("/api/backup/status").json()
    assert st["initialized"] is False and st["stale"] is False   # prima si prepara l'archivio
    assert api.post("/api/backup/jobs", json={"kind": "backup"}).status_code == 409


def test_snapshots_richiedono_il_disco(env):
    r = api.get("/api/backup/snapshots")
    assert r.status_code == 409 and "non è collegato" in r.json()["detail"]   # proprio per il disco, non per l'archivio da preparare
    assert env.client.containers.runs == []


def test_modalita_locale_senza_disco_funziona_come_prima(env):
    env.mp.delenv("BACKUP_DISK_DIR")
    env.mp.setenv("BACKUP_MOUNT_PARENT", "/srv/data/backups")
    env.mp.setenv("RESTIC_REPO_DIR", "/srv/data/backups/restic")
    (env.local.parent / "restic").mkdir()
    (env.local.parent / "restic" / "config").write_text("x")
    st = api.get("/api/backup/status").json()
    assert st["disk"] is None and st["initialized"] is True
    assert api.post("/api/backup/jobs", json={"kind": "backup"}).status_code == 202


@pytest.mark.parametrize("repo,disk,parent", [
    ("/altrove/restic", HOST_DISK, HOST_PARENT),                  # archivio fuori dal disco
    (HOST_REPO, "/altrove/BACKUP", HOST_PARENT),                  # disco fuori dalla cartella madre
    (HOST_DISK, HOST_DISK, HOST_PARENT),                          # archivio = disco (niente sottocartella)
    (HOST_REPO, HOST_PARENT, HOST_PARENT),                        # disco = cartella madre
    ("/media/u/BACKUP/../../etc/restic", HOST_DISK, HOST_PARENT), # '..'
    ("relativo/restic", HOST_DISK, HOST_PARENT),                  # non assoluto
    (HOST_REPO, HOST_DISK, "/"),                                  # madre = radice
    ("/media/u/ALTRO/restic", HOST_DISK, HOST_PARENT),            # archivio nella cartella madre ma su un altro disco
])
def test_configurazione_incoerente_e_un_problema_non_un_percorso_scritto(env, repo, disk, parent):
    env.mp.setenv("RESTIC_REPO_DIR", repo)
    env.mp.setenv("BACKUP_DISK_DIR", disk)
    env.mp.setenv("BACKUP_MOUNT_PARENT", parent)
    plug(env)
    st = api.get("/api/backup/status").json()
    assert st["configured"] is False and st["problems"], st
    assert any("dentro" in x or "assoluto" in x for x in st["problems"]), st["problems"]   # respinta per la configurazione, non per una cartella mancante
    assert api.post("/api/backup/jobs", json={"kind": "backup"}).status_code == 409
    assert env.client.containers.runs == []


def test_ultima_copia_ricordata_a_disco_scollegato(env):
    env.client.containers.job = FakeContainer(kind="backup", finished="2026-11-07T17:03:12.123456789Z")
    st = api.get("/api/backup/status").json()
    assert st["last_backup_at"].startswith("2026-11-07T17:03:12")
    env.client.containers.job = FakeContainer(kind="forget", finished="2026-11-08T10:00:00Z")   # la pulizia sostituisce il lavoro
    st = api.get("/api/backup/status").json()
    assert st["last_backup_at"].startswith("2026-11-07T17:03:12")   # ma la data della copia resta


def test_una_copia_fallita_non_aggiorna_la_data(env):
    env.client.containers.job = FakeContainer(kind="backup", exit_code=1)
    assert api.get("/api/backup/status").json()["last_backup_at"] is None


@pytest.mark.parametrize("days,warn,stale", [(3, None, False), (20, None, True), (13, None, False), (14, None, True), (400, "0", False)])
def test_promemoria_se_l_ultima_copia_e_vecchia(env, days, warn, stale):
    if warn is not None:
        env.mp.setenv("BACKUP_WARN_DAYS", warn)
    when = datetime.now(timezone.utc) - timedelta(days=days, minutes=5)
    env.client.containers.job = FakeContainer(kind="backup", finished=when.isoformat())
    st = api.get("/api/backup/status").json()
    assert st["stale"] is stale and st["age_days"] == days


def test_mai_fatta_una_copia_e_da_segnalare(env):
    assert api.get("/api/backup/status").json()["stale"] is True


def test_data_di_docker_non_finita_non_conta(env):
    env.client.containers.job = FakeContainer(kind="backup", finished="0001-01-01T00:00:00Z")
    assert api.get("/api/backup/status").json()["last_backup_at"] is None


def test_solo_l_admin_ogni_rotta_di_scrittura_dichiara_require_admin():
    from app.auth import require_admin
    writes = [r for r in backup.router.routes if r.methods - {"GET", "HEAD"}]
    assert writes, "non trovo le rotte di scrittura"
    for r in writes:
        assert require_admin in [d.dependency for d in r.dependencies], f"{r.methods} {r.path} non dichiara require_admin"


def test_la_pianificazione_non_esiste_piu(env):
    assert not hasattr(backup, "start_scheduler") and not hasattr(backup, "should_run")
    env.mp.setenv("RESTIC_SCHEDULE", "03:30")   # un .env vecchio non fa partire nulla
    assert [t.name for t in __import__("threading").enumerate() if t.name == "backup-scheduler"] == []


def test_un_solo_backup_alla_volta(env):
    plug(env)
    env.client.containers.list = lambda filters=None: [object()]
    r = api.post("/api/backup/jobs", json={"kind": "backup"})
    assert r.status_code == 409 and "in corso" in r.json()["detail"]
