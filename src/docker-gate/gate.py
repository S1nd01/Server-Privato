#!/usr/bin/env python3
"""docker-gate: filtro per il socket Docker, riservato al backend del pannello.

Perche' esiste: il backend deve (1) elencare, avviare, fermare e riavviare i container del pannello, (2) leggerne le statistiche,
(3) eseguire due comandi fissi dentro vaultwarden e tailscale e (4) lanciare il container "restic_job" per i backup. Un proxy
che filtra solo per percorso (tecnativa/docker-socket-proxy) non basta: per (4) dovrebbe lasciar passare `POST /containers/create`,
e chi puo' creare un container qualsiasi puo' montare `/` e diventare root sul computer. Questo filtro, invece, guarda anche
il CORPO delle richieste e decide caso per caso:

  * avvio/arresto/riavvio, statistiche, log: solo sui container elencati in GATE_CONTAINERS (e sul job di backup);
  * creazione di container: solo l'immagine di Restic, solo i montaggi previsti (percorsi presi dalle variabili d'ambiente),
    niente privilegi, niente rete diversa da quella di serie, niente comandi diversi da quelli di Restic;
  * exec: solo i comandi fissi di EXEC_RULES, solo nei container previsti; vale anche per l'avvio dell'exec gia' creato
    (lo si riconosce interrogando Docker, non fidandosi del chiamante);
  * tutto il resto (immagini, volumi, reti, eventi, swarm, build, ...) e' rifiutato con 403.

Resta un limite, da conoscere: la lettura dei dettagli di un container (`GET /containers/<nome>/json`) restituisce anche le sue
variabili d'ambiente. Il filtro non riscrive le risposte: chi controlla il backend le puo' leggere. Non puo' invece creare
container, entrare in altri container o toccare il resto di Docker.

Solo libreria standard. Configurazione tramite variabili d'ambiente (vedi Config).
"""
from __future__ import annotations

import http.client
import json
import os
import re
import select
import socket
import socketserver
import sys
import threading
from urllib.parse import parse_qs, urlsplit

HEX_ID = re.compile(r"[0-9a-f]{12,64}")
VERSION_PREFIX = re.compile(r"^/v\d+(\.\d+)?(?=/)")
NAME_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")

JOB_NAME = "restic_job"
JOB_LABEL = "hs.restic"
GATE_LABEL = "hs.gate"   # lo aggiunge il filtro a ogni container che crea: cosi' riconosce i "suoi" anche senza nome (es. snapshots)
RESTIC_SUBCOMMANDS = {"init", "backup", "forget", "check", "snapshots"}
CREATE_ENV_KEYS = {"RESTIC_PASSWORD_FILE", "RESTIC_CACHE_DIR", "TZ", "GOMAXPROCS"}
CREATE_LABEL_KEYS = {JOB_LABEL, "hs.kind"}
# Chiavi del corpo di creazione che devono essere vuote (nulle, false, stringa o struttura vuota)
CREATE_MUST_BE_EMPTY = (
    "Hostname", "Domainname", "ExposedPorts", "User", "Tty", "OpenStdin", "StdinOnce", "AttachStdin", "Entrypoint",
    "WorkingDir", "NetworkDisabled", "NetworkingConfig", "MacAddress", "StopSignal", "Healthcheck", "StopTimeout", "Runtime",
)
CREATE_KNOWN = set(CREATE_MUST_BE_EMPTY) | {"AttachStdout", "AttachStderr", "Env", "Cmd", "Image", "Volumes", "HostConfig", "Labels"}
HOSTCONFIG_KNOWN = {"NetworkMode", "Binds", "CpuShares"}
EXEC_KNOWN = {"Container", "User", "Privileged", "Tty", "AttachStdin", "AttachStdout", "AttachStderr", "Cmd", "Env", "detachKeys"}
EXEC_START_KNOWN = {"Detach", "Tty", "ConsoleSize"}
MAX_BODY = 64 * 1024


class Deny(Exception):
    """Richiesta non permessa: il messaggio finisce nella risposta 403 e nel log."""


def _empty(v) -> bool:
    return v in (None, False, "", [], {}, 0)


class Config:
    def __init__(self, env=os.environ):
        self.upstream = env.get("UPSTREAM", "/var/run/docker.sock")
        self.port = int(env.get("LISTEN_PORT", "2375"))
        self.panel = {n.strip() for n in env.get("GATE_CONTAINERS", "").split(",") if n.strip()}
        for n in self.panel:
            if not NAME_OK.fullmatch(n) or HEX_ID.fullmatch(n):
                raise SystemExit(f"GATE_CONTAINERS: nome non valido: {n!r}")
        self.image = env.get("RESTIC_IMAGE") or "restic/restic:latest"
        # bind consentiti: percorso nel container -> (sorgente sull'host, modo). Una sorgente vuota non e' ammessa.
        self.binds: dict[str, tuple[str, str]] = {}
        for target, key, mode in (
            ("/repo", "RESTIC_REPO_DIR", "rw"),
            ("/run/restic-pass", "RESTIC_PASSWORD_FILE", "ro"),
            ("/source", "HOST_DATA_DIR", "ro"),
            ("/photos", "HOST_PHOTOS_DIR", "ro"),
        ):
            src = env.get(key, "").strip()
            if src.startswith("/"):
                self.binds[target] = (src, mode)
        self.binds["/cache"] = (env.get("RESTIC_CACHE_VOLUME", "hs_restic_cache"), "rw")
        # exec consentiti: container -> elenco di comandi esatti
        self.exec_rules: dict[str, list[list[str]]] = {
            "vaultwarden": [["/vaultwarden", "backup"]],
            "tailscale": [["tailscale", "status", "--json"]],
        }


class Gate:
    def __init__(self, cfg: Config, upstream_json=None):
        self.cfg = cfg
        self._upstream_json = upstream_json or self._http_json

    # ------------------------------------------------------------ colloquio con Docker (solo letture)
    def _http_json(self, path: str):
        conn = _UnixHTTPConnection(self.cfg.upstream)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            data = resp.read(1024 * 1024)
            if resp.status == 404:
                return None
            if resp.status != 200:
                raise Deny(f"Docker ha risposto {resp.status} a una verifica interna")
            return json.loads(data)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise Deny(f"verifica interna non riuscita: {exc}")
        finally:
            conn.close()

    # ------------------------------------------------------------ identificazione dei container
    def identify(self, ref: str) -> tuple[str, str]:
        """(tipo, nome): tipo 'panel' = container del pannello, 'job' = job di backup, 'missing' = non esiste (Docker rispondera' 404)."""
        if ref in self.cfg.panel:
            return "panel", ref
        if ref == JOB_NAME:
            return "job", ref
        if HEX_ID.fullmatch(ref):
            info = self._upstream_json(f"/containers/{ref}/json")
            if info is None:
                return "missing", ref
            name = str(info.get("Name", "")).lstrip("/")
            if name in self.cfg.panel:
                return "panel", name
            conf = info.get("Config") or {}
            if (conf.get("Labels") or {}).get(GATE_LABEL) == "1" and conf.get("Image") == self.cfg.image:
                return "job", name
        raise Deny(f"container non ammesso: {ref}")

    # ------------------------------------------------------------ regole
    def decide(self, method: str, target: str, body: bytes) -> bytes | None:
        """Lascia passare (None) o ritorna il corpo riscritto; rifiuta con Deny."""
        parts = urlsplit(target)
        path = VERSION_PREFIX.sub("", parts.path)
        query = parse_qs(parts.query, keep_blank_values=True)
        seg = [s for s in path.split("/") if s]

        if method in ("GET", "HEAD") and path in ("/_ping", "/version"):
            return
        if method == "GET" and path == "/containers/json":
            return
        if len(seg) == 3 and seg[0] == "containers":
            return self._container_action(method, seg[1], seg[2], body)
        if len(seg) == 2 and seg[0] == "containers" and method == "DELETE":
            kind, _ = self.identify(seg[1])
            if kind in ("job", "missing"):
                return
            raise Deny("si puo' rimuovere solo il job di backup")
        if method == "POST" and path == "/containers/create":
            return self._create(query, body)   # unico caso in cui il corpo cambia: si aggiunge l'etichetta del filtro
        if method == "POST" and path == "/images/create":
            return self._pull(query)
        if len(seg) == 3 and seg[0] == "exec" and ((method == "GET" and seg[2] == "json") or (method == "POST" and seg[2] == "start")):
            if seg[2] == "start":
                self._json_keys(body, EXEC_START_KNOWN, "exec start")
            return self._exec_allowed(seg[1])
        raise Deny(f"{method} {path} non e' permesso")

    def _container_action(self, method: str, ref: str, action: str, body: bytes) -> None:
        kind, name = self.identify(ref)
        if kind == "missing":
            return
        if method == "GET" and action in ("json", "stats", "logs"):
            return
        if method == "POST" and action in ("start", "stop", "restart"):
            return
        if method == "POST" and action == "wait" and kind == "job":
            return
        if method == "POST" and action == "exec":
            return self._exec_create(name, body)
        raise Deny(f"{method} /containers/<{kind}>/{action} non e' permesso")

    def _json_keys(self, body: bytes, known: set[str], what: str) -> dict:
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            raise Deny(f"{what}: corpo non valido")
        if not isinstance(data, dict):
            raise Deny(f"{what}: corpo non valido")
        extra = set(data) - known
        if extra:
            raise Deny(f"{what}: campi non ammessi: {sorted(extra)}")
        return data

    def _exec_create(self, name: str, body: bytes) -> None:
        rules = self.cfg.exec_rules.get(name)
        if not rules:
            raise Deny(f"exec non permesso nel container {name}")
        data = self._json_keys(body, EXEC_KNOWN, "exec")
        if data.get("Privileged") or data.get("User") or data.get("Env") or data.get("Tty") or data.get("AttachStdin"):
            raise Deny("exec: privilegi, utente, variabili, tty e stdin non sono ammessi")
        if data.get("Cmd") not in rules:
            raise Deny(f"exec: comando non ammesso in {name}")

    def _exec_allowed(self, exec_id: str) -> None:
        if not HEX_ID.fullmatch(exec_id):
            raise Deny("identificativo exec non valido")
        info = self._upstream_json(f"/exec/{exec_id}/json")
        if info is None:
            return   # non esiste: Docker rispondera' 404
        pc = info.get("ProcessConfig") or {}
        cmd = [pc.get("entrypoint", "")] + list(pc.get("arguments") or [])
        kind, name = self.identify(str(info.get("ContainerID", "")))
        if kind != "panel" or cmd not in self.cfg.exec_rules.get(name, []) or pc.get("privileged") or pc.get("user") or pc.get("tty"):
            raise Deny("exec: non e' uno di quelli ammessi")

    def _pull(self, query: dict) -> None:
        def split(img: str) -> tuple[str, str]:
            if ":" in img.rsplit("/", 1)[-1]:
                repo, _, tag = img.rpartition(":")
                return repo, tag
            return img, "latest"

        from_image = (query.get("fromImage") or [""])[0]
        tag = (query.get("tag") or [""])[0]
        want = split(self.cfg.image)
        got = split(from_image) if not tag else (from_image, tag)
        if got != want or any(k not in ("fromImage", "tag") for k in query):
            raise Deny("si puo' scaricare solo l'immagine di Restic")

    def _create(self, query: dict, body: bytes) -> bytes:
        name = (query.get("name") or [None])[0]
        if name not in (None, "", JOB_NAME) or any(k != "name" for k in query):
            raise Deny("si puo' creare solo il job di backup")
        data = self._json_keys(body, CREATE_KNOWN, "create")
        if data.get("Image") != self.cfg.image:
            raise Deny("create: immagine non ammessa")
        for k in CREATE_MUST_BE_EMPTY:
            if not _empty(data.get(k)):
                raise Deny(f"create: il campo {k} deve essere vuoto")
        cmd = data.get("Cmd")
        if not (isinstance(cmd, list) and len(cmd) >= 3 and all(isinstance(c, str) for c in cmd)
                and cmd[:2] == ["-r", "/repo"] and cmd[2] in RESTIC_SUBCOMMANDS):
            raise Deny("create: comando non ammesso (solo Restic su /repo)")
        for e in data.get("Env") or []:
            if not isinstance(e, str) or e.split("=", 1)[0] not in CREATE_ENV_KEYS:
                raise Deny("create: variabile d'ambiente non ammessa")
        labels = data.get("Labels") or {}
        if not isinstance(labels, dict) or set(labels) - CREATE_LABEL_KEYS:
            raise Deny("create: etichetta non ammessa")
        for t in (data.get("Volumes") or {}):
            if t not in self.cfg.binds:
                raise Deny(f"create: volume non ammesso: {t}")
        hc = data.get("HostConfig") or {}
        if not isinstance(hc, dict) or set(hc) - HOSTCONFIG_KNOWN:
            raise Deny(f"create: HostConfig con campi non ammessi: {sorted(set(hc) - HOSTCONFIG_KNOWN) if isinstance(hc, dict) else hc}")
        if hc.get("NetworkMode") not in (None, "", "default", "bridge"):
            raise Deny("create: rete non ammessa")
        if not isinstance(hc.get("CpuShares", 0), int) or isinstance(hc.get("CpuShares"), bool):
            raise Deny("create: CpuShares non valido")
        mounts = []
        for b in hc.pop("Binds", None) or []:
            if not isinstance(b, str):
                raise Deny("create: bind non valido")
            bits = b.split(":")
            if len(bits) != 3:
                raise Deny(f"create: bind non ammesso: {b}")
            src, target, mode = bits
            if target not in self.cfg.binds or self.cfg.binds[target] != (src, mode):
                raise Deny(f"create: montaggio non ammesso: {b}")
            # Docker crea directory mancanti con Binds. Mounts fallisce per
            # i bind assenti, anche se il disco sparisce dopo il controllo.
            mounts.append({
                "Type": "bind" if src.startswith("/") else "volume",
                "Source": src, "Target": target, "ReadOnly": mode == "ro",
            })
        if mounts:
            hc["Mounts"] = mounts
        data["Labels"] = {**labels, GATE_LABEL: "1"}
        return json.dumps(data).encode()


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 10):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


# ---------------------------------------------------------------- server
def _read_request(rfile):
    """Legge riga, intestazioni e corpo (solo con Content-Length). Ritorna (metodo, target, versione, intestazioni, corpo)."""
    line = rfile.readline(8192)
    if not line:
        return None
    try:
        method, target, version = line.decode("latin-1").rstrip("\r\n").split(" ", 2)
    except ValueError:
        raise Deny("richiesta malformata")
    headers: list[tuple[str, str]] = []
    total = 0
    while True:
        h = rfile.readline(8192)
        total += len(h)
        if total > 32 * 1024 or len(headers) > 64:
            raise Deny("intestazioni troppo grandi")
        if h in (b"\r\n", b"\n", b""):
            break
        name, _, value = h.decode("latin-1").partition(":")
        headers.append((name.strip(), value.strip()))
    lower = {k.lower(): v for k, v in headers}
    if "chunked" in lower.get("transfer-encoding", "").lower():
        raise Deny("Transfer-Encoding: chunked non supportato")
    try:
        length = int(lower.get("content-length", "0") or 0)
    except ValueError:
        raise Deny("Content-Length non valido")
    if length < 0 or length > MAX_BODY:
        raise Deny("corpo troppo grande")
    body = rfile.read(length) if length else b""
    return method.upper(), target, version, headers, body


def _respond(sock: socket.socket, status: int, message: str) -> None:
    payload = json.dumps({"message": f"docker-gate: {message}"}).encode()
    reason = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway"}.get(status, "Error")
    head = f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
    try:
        sock.sendall(head.encode() + payload)
    except OSError:
        pass


def _relay(client: socket.socket, upstream: socket.socket, idle: float = 900.0) -> None:
    """Passa i byte nei due sensi finche' Docker chiude (vale anche per exec con Upgrade e per i log in diretta)."""
    client_open = True
    while True:
        r, _, _ = select.select([upstream] + ([client] if client_open else []), [], [], idle)
        if not r:
            return
        for s in r:
            try:
                data = s.recv(65536)
            except OSError:
                return
            if s is upstream:
                if not data:
                    return
                try:
                    client.sendall(data)
                except OSError:
                    return
            else:
                if not data:
                    client_open = False
                    try:
                        upstream.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                else:
                    upstream.sendall(data)


def make_handler(gate: Gate):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            sock = self.request
            sock.settimeout(30)
            try:
                req = _read_request(self.rfile)
                if req is None:
                    return
                method, target, version, headers, body = req
                new_body = gate.decide(method, target, body)
                if new_body is not None:
                    body = new_body
                    headers = [(k, v) for k, v in headers if k.lower() != "content-length"] + [("Content-Length", str(len(body)))]
            except Deny as exc:
                print(f"NEGATO {exc}", flush=True)
                _respond(sock, 403, str(exc))
                return
            except (OSError, ValueError):
                return
            upgrade = any(k.lower() == "upgrade" for k, _ in headers)
            out = [f"{method} {target} HTTP/1.1"]
            for k, v in headers:
                if not upgrade and k.lower() in ("connection", "proxy-connection", "keep-alive"):
                    continue
                out.append(f"{k}: {v}")
            if not upgrade:
                out.append("Connection: close")
            raw = ("\r\n".join(out) + "\r\n\r\n").encode("latin-1") + body
            up = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                up.settimeout(10)
                up.connect(gate.cfg.upstream)
                up.settimeout(None)
                up.sendall(raw)
                sock.settimeout(None)
                _relay(sock, up)
            except OSError as exc:
                _respond(sock, 502, f"Docker non raggiungibile: {exc}")
            finally:
                up.close()

    return Handler


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32


def main() -> None:
    cfg = Config()
    if not cfg.panel:
        raise SystemExit("GATE_CONTAINERS e' vuoto: nessun container ammesso")
    srv = _Server(("0.0.0.0", cfg.port), make_handler(Gate(cfg)))
    print(f"docker-gate in ascolto sulla porta {cfg.port}: {len(cfg.panel)} container, immagine {cfg.image}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
