"""Stato della VPN e accesso (opzionale) alle configurazioni dei peer.

linuxserver/wireguard salva, per ogni peer, una cartella /config/peer_<nome>/ con:
  peer_<nome>.conf   (contiene la CHIAVE PRIVATA del client)
  peer_<nome>.png    (QR code della conf)
  publickey-<nome>   (chiave pubblica del client, serve per associare nome <-> `wg show`)
"""

import os
import re
from pathlib import Path

from docker.errors import NotFound
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .dockerutil import get_client

router = APIRouter(prefix="/api/wireguard", tags=["wireguard"])

WG_DIR = Path("/data/wireguard")
CONTAINER = "wireguard"
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _peer_dirs() -> dict[str, Path]:
    if not WG_DIR.is_dir():
        return {}
    out = {}
    for d in sorted(WG_DIR.iterdir()):
        if d.is_dir() and d.name.startswith("peer"):
            name = d.name[len("peer_"):] if d.name.startswith("peer_") else d.name
            out[name] = d
    return out


def _pubkey(d: Path) -> str | None:
    for f in d.glob("publickey-*"):
        return f.read_text().strip()
    return None


def _exposed() -> bool:
    return os.environ.get("WG_EXPOSE_PEERS", "false").lower() == "true"


@router.get("/peers")
def peers():
    return {
        "exposed": _exposed(),
        "peers": [{"name": n, "public_key": _pubkey(d)} for n, d in _peer_dirs().items()],
    }


def _peer_file(name: str, pattern: str) -> Path:
    if not _exposed():
        raise HTTPException(403, "Esposizione dei peer disattivata (WG_EXPOSE_PEERS=false)")
    if not NAME_RE.match(name) or name not in _peer_dirs():
        raise HTTPException(404, "Peer sconosciuto")
    files = list(_peer_dirs()[name].glob(pattern))
    if not files:
        raise HTTPException(404, "File non trovato")
    return files[0]


@router.get("/peers/{name}/qr")
def peer_qr(name: str):
    return FileResponse(_peer_file(name, "*.png"), media_type="image/png")


@router.get("/peers/{name}/conf")
def peer_conf(name: str):
    return FileResponse(
        _peer_file(name, "*.conf"),
        media_type="text/plain",
        filename=f"{name}.conf",
    )


@router.get("/status")
def status():
    client = get_client()
    try:
        c = client.containers.get(CONTAINER)
    except NotFound:
        raise HTTPException(409, "Container wireguard non esiste")
    if c.status != "running":
        raise HTTPException(409, f"Container wireguard: {c.status}")

    code, out = c.exec_run(["wg", "show", "wg0", "dump"])
    text = out.decode(errors="replace").strip()
    if code != 0:
        raise HTTPException(502, f"wg show fallito: {text}")

    lines = text.splitlines()
    iface = lines[0].split("\t")  # privkey, pubkey, listen-port, fwmark (la privata NON viene esposta)
    names = {_pubkey(d): n for n, d in _peer_dirs().items()}
    result = []
    for line in lines[1:]:
        # pubkey, psk, endpoint, allowed-ips, latest-handshake, rx, tx, keepalive
        f = line.split("\t")
        handshake = int(f[4])
        result.append({
            "name": names.get(f[0], "?"),
            "public_key": f[0],
            "endpoint": None if f[2] == "(none)" else f[2],
            "allowed_ips": f[3],
            "last_handshake": handshake or None,  # epoch secondi
            "rx_bytes": int(f[5]),
            "tx_bytes": int(f[6]),
        })
    return {
        "interface": "wg0",
        "public_key": iface[1],
        "listen_port": int(iface[2]),
        "peers": result,
    }
