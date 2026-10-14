"""Stato di Tailscale, letto con `tailscale status --json` dentro il container `tailscale`.

Il comando e' fisso (nessun argomento arriva dall'API) e il pannello non puo' fermare Tailscale:
vedi services.py (allow_stop).
"""

import json

from docker.errors import APIError, NotFound
from fastapi import APIRouter, HTTPException

from .dockerutil import get_client

router = APIRouter(prefix="/api/tailscale", tags=["tailscale"])

CONTAINER = "tailscale"


def _clean_time(value):
    # Tailscale scrive "0001-01-01T00:00:00Z" per "mai"
    if not value or str(value).startswith("0001-"):
        return None
    return value


def _dns(value) -> str | None:
    return (value or "").rstrip(".") or None


def _peer(p: dict) -> dict:
    dns = _dns(p.get("DNSName"))
    return {
        "name": p.get("HostName") or (dns or "?").split(".")[0],
        "dns": dns,
        "os": p.get("OS") or None,
        "online": bool(p.get("Online")),
        "last_seen": _clean_time(p.get("LastSeen")),
        "ips": p.get("TailscaleIPs") or [],
        "rx_bytes": p.get("RxBytes") or 0,
        "tx_bytes": p.get("TxBytes") or 0,
    }


def parse_status(data: dict) -> dict:
    """Riduce l'output di `tailscale status --json` ai campi usati dal pannello."""
    me = data.get("Self") or {}
    dns = _dns(me.get("DNSName"))
    cert_domains = data.get("CertDomains") or []
    peers = [_peer(p) for p in (data.get("Peer") or {}).values()]
    peers.sort(key=lambda p: (not p["online"], p["name"].lower()))
    return {
        "state": data.get("BackendState") or "Unknown",
        "login_url": data.get("AuthURL") or None,
        "tailnet": ((data.get("CurrentTailnet") or {}).get("Name")) or data.get("MagicDNSSuffix") or None,
        "self": {
            "name": me.get("HostName") or None,
            "dns": dns,
            "ips": me.get("TailscaleIPs") or data.get("TailscaleIPs") or [],
            "online": bool(me.get("Online")),
        },
        # I certificati HTTPS sono attivi solo se la tailnet ha abilitato HTTPS (CertDomains non vuoto)
        "https_enabled": bool(cert_domains),
        "https_url": f"https://{cert_domains[0].rstrip('.')}" if cert_domains else None,
        "health": [str(h) for h in (data.get("Health") or [])][:5],
        "peers": peers,
    }


@router.get("/status")
def status():
    client = get_client()
    try:
        c = client.containers.get(CONTAINER)
    except NotFound:
        raise HTTPException(409, "Il container tailscale non esiste: avvialo con docker compose up -d tailscale")
    if c.status != "running":
        raise HTTPException(409, f"Il container tailscale e' {c.status}")

    try:
        res = c.exec_run(["tailscale", "status", "--json"], demux=True)
    except APIError as exc:
        raise HTTPException(502, f"Docker: {exc.explanation or exc}")

    stdout, stderr = res.output if isinstance(res.output, tuple) else (res.output, None)
    try:
        data = json.loads((stdout or b"").decode(errors="replace"))
    except ValueError:
        msg = (stderr or stdout or b"").decode(errors="replace").strip()[:200]
        raise HTTPException(502, f"tailscale non risponde ancora: {msg or 'nessun output'}")
    if not isinstance(data, dict):
        raise HTTPException(502, "Risposta di tailscale non valida")
    return parse_status(data)
