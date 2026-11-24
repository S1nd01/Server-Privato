"""Test di docker-gate.

    python3 -m pytest src/docker-gate/test_gate.py -q

Le prove "regole" non hanno bisogno di Docker. Quelle "reale" usano un demone Docker vero (saltate se manca) e l'SDK Python
con cui parla il backend, passando dal filtro: e' il test che conta, perche' controlla anche i corpi che l'SDK invia davvero.
Per le prove reali serve un'immagine locale: vedi la fixture `images` (si costruisce da sola con `docker import`).
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402
from gate import Config, Deny, Gate  # noqa: E402

IMG = "restic/restic:latest"
ENV = {
    "GATE_CONTAINERS": "vaultwarden,tailscale,jellyfin",
    "RESTIC_IMAGE": IMG,
    "RESTIC_REPO_DIR": "/mnt/disk/repo",
    "RESTIC_PASSWORD_FILE": "/home/u/.restic-pass",
    "HOST_DATA_DIR": "/srv/data",
    "HOST_PHOTOS_DIR": "/srv/data/photos",
}
CID = "a" * 64
JOBID = "b" * 64
EXECID = "c" * 64


def make_gate(containers=None, execs=None):
    containers = containers or {}
    execs = execs or {}

    def up(path):
        if path.startswith("/containers/"):
            return containers.get(path.split("/")[2])
        if path.startswith("/exec/"):
            return execs.get(path.split("/")[2])
        raise AssertionError(path)

    return Gate(Config(ENV), upstream_json=up)


def ok(g, method, target, body=None):
    g.decide(method, target, json.dumps(body).encode() if body is not None else b"")


def no(g, method, target, body=None):
    with pytest.raises(Deny):
        ok(g, method, target, body)


def good_create():
    return {
        "Hostname": None, "Domainname": None, "ExposedPorts": None, "User": None, "Tty": False, "OpenStdin": False,
        "StdinOnce": False, "AttachStdin": False, "AttachStdout": False, "AttachStderr": False,
        "Env": ["RESTIC_PASSWORD_FILE=/run/restic-pass", "TZ=Europe/Rome", "GOMAXPROCS=2"],
        "Cmd": ["-r", "/repo", "backup", "/source"], "Image": IMG,
        "Volumes": {"/repo": {}, "/cache": {}, "/run/restic-pass": {}, "/source": {}},
        "NetworkDisabled": False, "Entrypoint": None, "WorkingDir": None,
        "HostConfig": {"NetworkMode": "default", "CpuShares": 256, "Binds": [
            "/mnt/disk/repo:/repo:rw", "hs_restic_cache:/cache:rw", "/home/u/.restic-pass:/run/restic-pass:ro", "/srv/data:/source:ro"]},
        "NetworkingConfig": None, "MacAddress": None, "Labels": {"hs.restic": "1", "hs.kind": "backup"},
        "StopSignal": None, "Healthcheck": None, "StopTimeout": None, "Runtime": None,
    }


# ---------------------------------------------------------------- regole
def test_letture_e_azioni_sui_container_del_pannello():
    g = make_gate()
    ok(g, "GET", "/_ping")
    ok(g, "GET", "/v1.44/version")
    ok(g, "GET", "/v1.44/containers/json?all=1")
    for a in ("start", "stop", "restart"):
        ok(g, "POST", f"/v1.44/containers/jellyfin/{a}")
    ok(g, "GET", "/containers/vaultwarden/json")
    ok(g, "GET", "/containers/vaultwarden/stats?stream=false&one-shot=true")


def test_container_non_del_pannello_rifiutati():
    g = make_gate({CID: {"Name": "/hs_backend", "Config": {"Labels": {}, "Image": "x"}}})
    for name in ("hs_backend", "docker-gate", "portainer", "beszel-agent"):
        no(g, "POST", f"/containers/{name}/stop")
        no(g, "GET", f"/containers/{name}/json")
    no(g, "POST", f"/containers/{CID}/stop")     # per id: si risolve il nome e non e' ammesso


def test_id_di_un_container_del_pannello_ammesso():
    g = make_gate({CID: {"Name": "/jellyfin", "Config": {"Labels": {}, "Image": "j"}}})
    ok(g, "POST", f"/containers/{CID}/restart")


def test_id_inesistente_passa_e_docker_rispondera_404():
    ok(make_gate(), "GET", f"/containers/{CID}/json")


def test_endpoint_pericolosi_rifiutati():
    g = make_gate()
    for m, p in (("GET", "/images/json"), ("POST", "/containers/jellyfin/kill"), ("POST", "/containers/jellyfin/update"),
                 ("GET", "/volumes"), ("POST", "/networks/create"), ("GET", "/events"), ("POST", "/build"),
                 ("DELETE", "/containers/jellyfin"), ("GET", "/info"), ("POST", "/containers/jellyfin/attach"),
                 ("GET", "/containers/jellyfin/archive"), ("PUT", "/containers/jellyfin/archive"), ("POST", "/containers/prune"),
                 ("POST", "/exec/" + EXECID + "/resize"), ("GET", "/containers/jellyfin/changes"), ("POST", "/swarm/init")):
        no(g, m, p)


def test_wait_e_rimozione_solo_per_il_job():
    g = make_gate({JOBID: {"Name": "/restic_job", "Config": {"Labels": {"hs.gate": "1"}, "Image": IMG}}})
    ok(g, "POST", "/containers/restic_job/wait")
    ok(g, "POST", f"/containers/{JOBID}/wait")
    ok(g, "DELETE", f"/containers/{JOBID}?force=1")
    ok(g, "DELETE", "/containers/restic_job?force=1")
    no(g, "POST", "/containers/jellyfin/wait")
    no(g, "DELETE", "/containers/jellyfin?force=1")


def test_job_con_etichetta_ma_immagine_diversa_rifiutato():
    g = make_gate({JOBID: {"Name": "/altro", "Config": {"Labels": {"hs.gate": "1"}, "Image": "evil:1"}}})
    no(g, "DELETE", f"/containers/{JOBID}")


def test_creazione_valida_e_aggiunge_l_etichetta_del_filtro():
    g = make_gate()
    out = g.decide("POST", "/v1.44/containers/create?name=restic_job", json.dumps(good_create()).encode())
    assert json.loads(out)["Labels"]["hs.gate"] == "1" and json.loads(out)["Labels"]["hs.kind"] == "backup"
    assert g.decide("POST", "/v1.44/containers/create", json.dumps(good_create()).encode())


@pytest.mark.parametrize("mutate", [
    lambda b: b.update(Image="alpine:3"),
    lambda b: b.update(Entrypoint=["/bin/sh"]),
    lambda b: b.update(Cmd=["-c", "id"]),
    lambda b: b.update(Cmd=["-r", "/repo", "rewrite"]),
    lambda b: b.update(User="root"),
    lambda b: b.update(Tty=True),
    lambda b: b.update(Env=["LD_PRELOAD=/x"]),
    lambda b: b.update(Labels={"x": "y"}),
    lambda b: b.update(Labels={"hs.gate": "1"}),
    lambda b: b.update(Volumes={"/host": {}}),
    lambda b: b.update(Extra=1),
    lambda b: b["HostConfig"].update(Privileged=True),
    lambda b: b["HostConfig"].update(NetworkMode="host"),
    lambda b: b["HostConfig"].update(PidMode="host"),
    lambda b: b["HostConfig"].update(CapAdd=["ALL"]),
    lambda b: b["HostConfig"].update(Mounts=[{"Type": "bind", "Source": "/", "Target": "/h"}]),
    lambda b: b["HostConfig"].update(Devices=[{"PathOnHost": "/dev/sda"}]),
    lambda b: b["HostConfig"].update(Binds=["/:/source:ro"]),
    lambda b: b["HostConfig"].update(Binds=["/srv/data:/source:rw"]),         # modo diverso
    lambda b: b["HostConfig"].update(Binds=["/etc:/repo:rw"]),                # sorgente diversa
    lambda b: b["HostConfig"].update(Binds=["/mnt/disk/repo:/host:rw"]),      # destinazione non prevista
    lambda b: b["HostConfig"].update(Binds=["/mnt/disk/repo:/repo:rw:z"]),
])
def test_creazione_pericolosa_rifiutata(mutate):
    body = good_create()
    mutate(body)
    no(make_gate(), "POST", "/containers/create?name=restic_job", body)


def test_creazione_con_nome_o_parametri_diversi_rifiutata():
    g = make_gate()
    no(g, "POST", "/containers/create?name=altro", good_create())
    no(g, "POST", "/containers/create?name=restic_job&platform=x", good_create())


def test_pull_solo_immagine_di_restic():
    g = make_gate()
    ok(g, "POST", "/v1.44/images/create?fromImage=restic%2Frestic&tag=latest")
    ok(g, "POST", "/v1.44/images/create?fromImage=restic%2Frestic%3Alatest")
    no(g, "POST", "/images/create?fromImage=alpine&tag=3")
    no(g, "POST", "/images/create?fromImage=restic%2Frestic&tag=0.1")
    no(g, "POST", "/images/create?fromImage=restic%2Frestic&tag=latest&platform=x")


def test_exec_solo_comandi_fissi_nei_container_previsti():
    g = make_gate()
    base = {"Container": "vaultwarden", "User": "", "Privileged": False, "Tty": False, "AttachStdin": False,
            "AttachStdout": True, "AttachStderr": True, "Env": None}
    ok(g, "POST", "/containers/vaultwarden/exec", {**base, "Cmd": ["/vaultwarden", "backup"]})
    ok(g, "POST", "/containers/tailscale/exec", {**base, "Cmd": ["tailscale", "status", "--json"]})
    no(g, "POST", "/containers/vaultwarden/exec", {**base, "Cmd": ["sh"]})
    no(g, "POST", "/containers/vaultwarden/exec", {**base, "Cmd": ["tailscale", "status", "--json"]})
    no(g, "POST", "/containers/jellyfin/exec", {**base, "Cmd": ["/vaultwarden", "backup"]})
    no(g, "POST", "/containers/vaultwarden/exec", {**base, "Cmd": ["/vaultwarden", "backup"], "Privileged": True})
    no(g, "POST", "/containers/vaultwarden/exec", {**base, "Cmd": ["/vaultwarden", "backup"], "User": "root"})
    no(g, "POST", "/containers/vaultwarden/exec", {**base, "Cmd": ["/vaultwarden", "backup"], "Env": ["A=b"]})
    no(g, "POST", "/containers/vaultwarden/exec", {**base, "Cmd": ["/vaultwarden", "backup"], "WorkingDir": "/"})


def test_exec_start_si_verifica_interrogando_docker():
    vw = {CID: {"Name": "/vaultwarden", "Config": {"Labels": {}, "Image": "v"}}}
    good = {"ContainerID": CID, "ProcessConfig": {"entrypoint": "/vaultwarden", "arguments": ["backup"], "privileged": False, "user": "", "tty": False}}
    bad_cmd = {**good, "ProcessConfig": {**good["ProcessConfig"], "entrypoint": "sh", "arguments": ["-c", "id"]}}
    other = {CID: {"Name": "/jellyfin", "Config": {"Labels": {}, "Image": "j"}}}
    ok(make_gate(vw, {EXECID: good}), "POST", f"/exec/{EXECID}/start", {"Detach": False, "Tty": False})
    ok(make_gate(vw, {EXECID: good}), "GET", f"/exec/{EXECID}/json")
    no(make_gate(vw, {EXECID: bad_cmd}), "POST", f"/exec/{EXECID}/start", {"Detach": False, "Tty": False})
    no(make_gate(other, {EXECID: good}), "POST", f"/exec/{EXECID}/start", {"Detach": False, "Tty": False})
    no(make_gate(vw, {EXECID: good}), "POST", f"/exec/{EXECID}/start", {"Detach": False, "Tty": False, "Env": ["A=b"]})
    ok(make_gate(), "POST", f"/exec/{EXECID}/start", {"Detach": False, "Tty": False})   # inesistente: 404 da Docker


def test_configurazione_con_nomi_non_validi():
    with pytest.raises(SystemExit):
        Config({**ENV, "GATE_CONTAINERS": "a b"})
    with pytest.raises(SystemExit):
        Config({**ENV, "GATE_CONTAINERS": "a" * 12})   # sembra un id


# ---------------------------------------------------------------- reale (demone Docker + SDK)
def _docker_ok():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


docker_needed = pytest.mark.skipif(not _docker_ok(), reason="nessun demone Docker raggiungibile")
IMG_REAL = "hs-gate-test/restic:1"
IMG_SVC = "hs-gate-test/svc:1"


def _build_image(tag, files, entrypoint=None):
    """Immagine minima con le sole librerie dei comandi indicati, via `docker import` (nessun accesso a registri)."""
    root = Path("/tmp") / ("rootfs-" + tag.replace("/", "-").replace(":", "-"))
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    for b in ("/usr/bin/sh", "/usr/bin/sleep", "/usr/bin/cat", "/usr/bin/echo", "/usr/bin/env", "/usr/bin/id"):
        for src in [b] + [w for w in subprocess.run(["ldd", b], capture_output=True, text=True).stdout.split() if w.startswith("/")]:
            dst = root / src.lstrip("/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy(os.path.realpath(src), dst)
                dst.chmod(0o755)
    (root / "bin").mkdir(exist_ok=True)
    if not (root / "bin/sh").exists():
        (root / "bin/sh").symlink_to("/usr/bin/sh")
    for rel, text in files.items():
        p = root / rel.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        p.chmod(0o755)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        t.add(root, arcname=".")
    cmd = ["docker", "import"]
    if entrypoint:
        cmd += ["--change", f"ENTRYPOINT {json.dumps(entrypoint)}"]
    subprocess.run(cmd + ["-", tag], input=buf.getvalue(), capture_output=True, check=True)


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    import docker

    _build_image(IMG_REAL, {"/restic": "#!/usr/bin/sh\necho \"restic $@\"\ncat /run/restic-pass\n"}, ["/restic"])
    _build_image(IMG_SVC, {"/vaultwarden": "#!/usr/bin/sh\necho backup-ok\n", "/usr/bin/tailscale": "#!/usr/bin/sh\necho '{\"x\":1}'\n"})
    work = tmp_path_factory.mktemp("gate")
    (work / "repo").mkdir()
    (work / "pass").write_text("segreto\n")
    env = {**os.environ, "GATE_CONTAINERS": "vaultwarden,tailscale,jellyfin", "RESTIC_IMAGE": IMG_REAL,
           "RESTIC_REPO_DIR": str(work / "repo"), "RESTIC_PASSWORD_FILE": str(work / "pass"),
           "HOST_DATA_DIR": str(work), "HOST_PHOTOS_DIR": str(work / "photos"), "LISTEN_PORT": "12375"}
    proc = subprocess.Popen([sys.executable, str(Path(gate.__file__))], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1.0)
    raw = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    names = ("vaultwarden", "tailscale", "jellyfin", "hs_backend", "restic_job")
    for n in names:
        try:
            raw.containers.get(n).remove(force=True)
        except docker.errors.NotFound:
            pass
    for n in ("vaultwarden", "tailscale", "jellyfin", "hs_backend"):
        raw.containers.run(IMG_SVC, ["/usr/bin/sleep", "300"], name=n, detach=True)
    client = docker.DockerClient(base_url="tcp://127.0.0.1:12375")
    yield client, raw, work
    proc.terminate()
    for n in names:
        try:
            raw.containers.get(n).remove(force=True)
        except docker.errors.NotFound:
            pass


@docker_needed
def test_reale_azioni_del_pannello(real):
    client, raw, _ = real
    rows = client.api.containers(all=True)
    assert {"vaultwarden", "hs_backend"} <= {n.lstrip("/") for r in rows for n in r["Names"]}
    c = client.containers.get("jellyfin")
    c.restart(timeout=1)
    c.stop(timeout=1)
    c.start()
    assert client.containers.get("jellyfin").status == "running"
    stats = client.containers.get("jellyfin").stats(stream=False, one_shot=True)
    assert "cpu_stats" in stats
    import docker
    with pytest.raises(docker.errors.APIError) as ei:
        client.containers.get("hs_backend").stop()
    assert ei.value.status_code == 403
    assert raw.containers.get("hs_backend").status == "running"


@docker_needed
def test_reale_exec_fissi(real):
    client, _, _ = real
    import docker
    res = client.containers.get("vaultwarden").exec_run(["/vaultwarden", "backup"])
    assert res.exit_code == 0 and b"backup-ok" in res.output
    res = client.containers.get("tailscale").exec_run(["tailscale", "status", "--json"], demux=True)
    assert res.exit_code == 0 and b'"x":1' in res.output[0]
    with pytest.raises(docker.errors.APIError) as ei:
        client.containers.get("vaultwarden").exec_run(["sh", "-c", "id"])
    assert ei.value.status_code == 403
    with pytest.raises(docker.errors.APIError):
        client.containers.get("jellyfin").exec_run(["/vaultwarden", "backup"])


@docker_needed
def test_reale_job_di_backup_come_fa_il_backend(real):
    client, raw, work = real
    import docker
    cfg = {"repo": str(work / "repo"), "password": str(work / "pass")}
    vols = {cfg["repo"]: {"bind": "/repo", "mode": "rw"}, cfg["password"]: {"bind": "/run/restic-pass", "mode": "ro"},
            "hs_restic_cache": {"bind": "/cache", "mode": "rw"}, str(work): {"bind": "/source", "mode": "ro"}}
    env = {"RESTIC_PASSWORD_FILE": "/run/restic-pass", "RESTIC_CACHE_DIR": "/cache", "TZ": "Europe/Rome", "GOMAXPROCS": "2"}
    # come backup.start_job
    c = client.containers.run(IMG_REAL, ["-r", "/repo", "backup", "/source"], name="restic_job", detach=True,
                              labels={"hs.restic": "1", "hs.kind": "backup"}, environment=env, volumes=vols, cpu_shares=256, use_config_proxy=False)
    c.wait(timeout=30)
    assert "restic -r /repo backup /source" in client.containers.get("restic_job").logs(tail=20).decode()
    assert client.containers.list(filters={"label": "hs.restic", "status": "running"}) == []
    client.containers.get("restic_job").remove(force=True)
    # come backup.snapshots (non detach, remove=True)
    out = client.containers.run(IMG_REAL, ["-r", "/repo", "snapshots", "--json"], detach=False, remove=True, stdout=True,
                                stderr=False, environment=env, use_config_proxy=False, volumes={k: v for k, v in vols.items() if v["bind"] in ("/repo", "/run/restic-pass", "/cache")})
    assert b"restic -r /repo snapshots --json" in out and b"segreto" in out
    # tentativi di evasione tramite l'SDK
    for kwargs in (
        dict(image=IMG_REAL, command=["-r", "/repo", "check"], volumes={"/": {"bind": "/repo", "mode": "rw"}}),
        dict(image=IMG_REAL, command=["-r", "/repo", "check"], volumes=vols, privileged=True),
        dict(image=IMG_REAL, command=["-r", "/repo", "check"], volumes=vols, network_mode="host"),
        dict(image=IMG_SVC, command=["/usr/bin/id"], volumes=vols),
        dict(image=IMG_REAL, command=["-r", "/repo", "check"], volumes=vols, entrypoint="/usr/bin/sh"),
    ):
        with pytest.raises(docker.errors.APIError) as ei:
            client.containers.run(detach=True, **kwargs)
        assert ei.value.status_code == 403, kwargs
    for img in ("alpine:3", "restic/restic:0.1"):
        with pytest.raises(docker.errors.APIError):
            client.images.pull(img)
    assert not any(c.name == "restic_job" for c in raw.containers.list(all=True))
