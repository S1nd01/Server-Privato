import json, sys, time, types
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
from docker.errors import NotFound

from app import history, smart, detail
from app.services import SERVICES


def sample(cpu, mem, host_cpu=10.0):
    return {"host": {"mem_total": 8_000_000_000, "mem_used": 4_000_000_000, "cpu_percent": host_cpu},
            "services": {"jellyfin": {"cpu_host_percent": cpu, "mem_bytes": mem}}}


def test_history_record_series_and_gap():
    history.reset()
    history.record(sample(1.0, 100), now=1000.0)
    history.record(sample(2.0, 200), now=1002.0)      # troppo vicino: ignorato
    history.record(sample(3.0, 300), now=1010.0)
    s = history.series("jellyfin", 900, now=1020.0)
    assert [p["cpu"] for p in s["points"]] == [1.0, 3.0]
    assert s["points"][0]["host_mem"] == 50.0
    assert s["points"][1]["mem_pct"] == round(300 / 8e9 * 100, 2)
    assert history.series("jellyfin", 900, now=5000.0)["points"] == []   # fuori finestra
    assert history.series("nonesiste", 900, now=1020.0)["points"] == []


def test_history_thin_and_trim():
    history.reset()
    for i in range(400):
        history.record(sample(float(i), i), now=10000.0 + i * 6)
    s = history.series("jellyfin", 3600, now=10000.0 + 400 * 6)
    assert len(s["points"]) <= history.MAX_POINTS
    assert s["points"][-1]["cpu"] == 399.0
    history.record(sample(0.0, 0), now=10000.0 + 400 * 6 + 4000)
    assert len(history._svc["jellyfin"]) == 1       # tutto il resto e' oltre un'ora


def test_history_never_raises():
    history.record(None)          # dati rotti: nessuna eccezione
    history.record({"host": 5})


def test_smart_states(tmp_path):
    f = tmp_path / "s.json"
    assert smart.read_status(path=f)["configured"] is False
    now = 2_000_000.0
    f.write_text(json.dumps({"at": now - 3600, "checked": 2, "problems": [], "warnings": [], "errors": []}))
    r = smart.read_status(now=now, path=f); assert r["level"] == "ok" and r["checked"] == 2
    f.write_text(json.dumps({"at": now - 3600, "checked": 2, "problems": ["sda: guasto"], "warnings": [], "errors": []}))
    assert smart.read_status(now=now, path=f)["level"] == "bad"
    f.write_text(json.dumps({"at": now - 40 * 3600, "checked": 2, "problems": [], "warnings": [], "errors": []}))
    r = smart.read_status(now=now, path=f); assert r["stale"] and r["level"] == "warn"
    f.write_text("non json"); assert smart.read_status(now=now, path=f)["level"] == "warn"
    f.write_text(json.dumps({"at": True, "checked": "x", "problems": "no", "warnings": [{"a": 1}, "ok"]}))
    r = smart.read_status(now=now, path=f); assert r["warnings"] == ["ok"] and r["checked"] == 0


def test_mask_secrets():
    t = 'GET /x?apikey=abc123&y=1\n"token": "s3cr3t-value"\nAuthorization: Bearer abcdefghijkl\npassword=hunter2 ok'
    m = detail.mask_secrets(t)
    for leak in ("abc123", "s3cr3t-value", "abcdefghijkl", "hunter2"):
        assert leak not in m
    assert "y=1" in m and "ok" in m


class FakeContainer:
    def __init__(self, name, running=True):
        self.status = "running" if running else "exited"
        self.attrs = {"Image": "sha256:" + "a" * 64, "Created": "2026-01-01T00:00:00Z", "RestartCount": 2,
                      "Config": {"Image": "x/y:1", "Env": ["PASSWORD=zzz"]},
                      "State": {"Status": self.status, "Running": running, "StartedAt": "2026-11-01T00:00:00Z",
                                "Health": {"Status": "healthy", "FailingStreak": 0}},
                      "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}, "NetworkMode": "media", "Memory": 10**9, "NanoCpus": 0},
                      "NetworkSettings": {"Ports": {"8096/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8096"}], "1/udp": None}},
                      "Mounts": [{"Type": "bind", "Source": "/srv/a", "Destination": "/a", "RW": False}]}
    def logs(self, **kw): return b"\x1b[31mrosso\x1b[0m apikey=SEGRETO\nfine"


class FakeClient:
    def __init__(self): self.containers = types.SimpleNamespace(get=self.get)
    def get(self, name):
        if name.startswith("manca"): raise NotFound("x")
        return FakeContainer(name)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False); monkeypatch.delenv("API_TOKEN_HASH", raising=False)
    monkeypatch.setattr(detail, "get_client", lambda: FakeClient())
    from app.main import app
    return TestClient(app)


def test_detail_endpoint(client):
    sid = "jellyfin"
    r = client.get(f"/api/services/{sid}/detail")
    assert r.status_code == 200, r.text
    c = r.json()["containers"][0]
    assert c["image"] == "x/y:1" and c["restarts"] == 2 and c["health"] == "healthy" and c["limit_mem"] == 10**9
    assert c["ports"] == [{"container": "8096/tcp", "host": ["0.0.0.0:8096"]}]
    assert "PASSWORD" not in r.text and "zzz" not in r.text           # mai le variabili d'ambiente
    assert client.get("/api/services/nonesiste/detail").status_code == 404


def test_logs_endpoint(client):
    r = client.get("/api/services/jellyfin/logs?tail=50")
    assert r.status_code == 200
    j = r.json(); assert "SEGRETO" not in j["logs"] and "\x1b" not in j["logs"] and "fine" in j["logs"]
    assert client.get("/api/services/jellyfin/logs?container=immich_server").status_code == 404
    assert client.get("/api/services/jellyfin/logs?tail=9999").status_code == 422


def test_history_and_smart_endpoints(client):
    assert client.get("/api/services/jellyfin/history?window=900").status_code == 200
    assert client.get("/api/services/jellyfin/history?window=99999").status_code == 422
    assert client.get("/api/smart").status_code == 200


def test_auth_still_required(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "x" * 40)
    from app.main import app
    c = TestClient(app)
    for u in ("/api/services/jellyfin/detail", "/api/services/jellyfin/logs", "/api/services/jellyfin/history", "/api/smart"):
        assert c.get(u).status_code in (401, 403), u
