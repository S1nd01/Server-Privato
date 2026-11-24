"""Storico breve di CPU e RAM, per il grafico della pagina «Dettagli» di ogni servizio.

Non c'e' nessun processo che campiona in continuazione: ogni volta che stats.collect() produce una lettura nuova (cioe' solo
quando qualcuno ha il pannello aperto) ne ricorda i numeri qui, in memoria. Cosi' a pannello chiuso il costo e' zero, anche su un
Raspberry; il rovescio e' che il grafico mostra solo il periodo in cui il pannello e' stato aperto (i buchi restano buchi). Per uno
storico continuo, giorno e notte, c'e' Beszel (docs/beszel.md).

Si perde a ogni riavvio del backend. Memoria: al massimo WINDOW_S / MIN_GAP_S campioni per servizio (720 x ~35 servizi, qualche
centinaio di KB).
"""
import threading
import time
from collections import deque

WINDOW_S = 3600      # quanto indietro si ricorda
MIN_GAP_S = 5.0      # due letture piu' vicine di cosi' contano come una
MAX_POINTS = 160     # punti restituiti al grafico (oltre, si dirada)

_lock = threading.Lock()
_host: dict[float, tuple[float | None, float | None]] = {}      # istante -> (CPU %, RAM %)
_svc: dict[str, deque] = {}                                     # id servizio -> (istante, CPU % del server, RAM in byte)
_mem_total: int | None = None
_last_at = 0.0


def _trim(dq: deque, now: float) -> None:
    while dq and dq[0][0] < now - WINDOW_S:
        dq.popleft()


def record(data: dict, now: float | None = None) -> None:
    """Ricorda una lettura di stats.collect(). Non solleva mai eccezioni: lo storico e' un di piu'."""
    global _last_at, _mem_total
    try:
        now = time.time() if now is None else now
        with _lock:
            if now - _last_at < MIN_GAP_S:
                return
            _last_at = now
            host = data.get("host") or {}
            total, used = host.get("mem_total"), host.get("mem_used")
            _mem_total = total or _mem_total
            mem_pct = round(used / total * 100, 1) if total and used is not None else None
            _host[now] = (host.get("cpu_percent"), mem_pct)
            for t in [t for t in _host if t < now - WINDOW_S]:
                del _host[t]
            for sid, s in (data.get("services") or {}).items():
                dq = _svc.setdefault(sid, deque())
                dq.append((now, s.get("cpu_host_percent"), s.get("mem_bytes")))
                _trim(dq, now)
    except Exception:   # noqa: BLE001 - mai bloccare le statistiche per colpa dello storico
        pass


def _thin(rows: list, n: int) -> list:
    if len(rows) <= n:
        return rows
    step = len(rows) / n
    out = [rows[int(i * step)] for i in range(n)]
    out[-1] = rows[-1]
    return out


def series(sid: str, window_s: int, now: float | None = None) -> dict:
    """I punti dell'ultimo `window_s` secondi per un servizio, dal piu' vecchio al piu' recente."""
    now = time.time() if now is None else now
    window_s = max(60, min(int(window_s), WINDOW_S))
    with _lock:
        rows = [r for r in _svc.get(sid, ()) if r[0] >= now - window_s]
        host = dict(_host)
        total = _mem_total
    points = []
    for t, cpu, mem in _thin(rows, MAX_POINTS):
        h_cpu, h_mem = host.get(t, (None, None))
        points.append({
            "t": round(t, 1),
            "cpu": cpu,                                                              # CPU del servizio, % del server
            "mem": mem,                                                              # RAM del servizio, byte
            "mem_pct": round(mem / total * 100, 2) if mem is not None and total else None,   # ... e in % della RAM del server
            "host_cpu": h_cpu,
            "host_mem": h_mem,
        })
    return {"window_s": window_s, "now": round(now, 1), "mem_total": total, "points": points}


def reset() -> None:
    """Svuota tutto (per le prove)."""
    global _last_at, _mem_total
    with _lock:
        _host.clear()
        _svc.clear()
        _last_at = 0.0
        _mem_total = None
