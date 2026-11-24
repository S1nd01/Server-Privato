"""Ricorda quali container sono stati FERMATI di proposito dal pannello (file di testo, un nome per riga).

Perche': `restart: unless-stopped` tiene fermi i container spenti anche dopo un riavvio del computer, ma `docker compose up -d`
(aggiornamento, ricreazione) li riaccende tutti. Questo elenco permette di rimetterli come li avevi lasciati:
`./src/scripts/riapplica-stato.sh` (lo chiama anche start.sh) ferma quelli ancora in funzione. Il backend non riapplica nulla da solo
(un controllo periodico spegnerebbe di nuovo cio' che hai riacceso a mano con Portainer o `docker start`).

Solo cio' che passa dal pannello viene registrato: un container fermato con `docker stop` o da Portainer non compare qui.
Il file sta in data/panel (montato in scrittura) e si scrive in modo atomico: un'interruzione a meta' non lo lascia a pezzi.
Un errore di scrittura non blocca mai l'azione richiesta: si registra un avviso e basta.
"""

import logging
import os
import re
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("homeserver.desired")

FILE = Path("/data/panel/stopped.txt")
# Stessa regola che usa riapplica-stato.sh: solo nomi di container "normali" (mai opzioni o percorsi)
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")

_lock = threading.Lock()


def read() -> list[str]:
    """Container fermati di proposito, in ordine alfabetico. Righe non valide e file mancante si ignorano."""
    try:
        lines = FILE.read_text().splitlines()
    except OSError:
        return []
    return sorted({ln.strip() for ln in lines if NAME_RE.fullmatch(ln.strip())})


def _write(names: set[str]) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=FILE.parent, prefix=".stopped-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("".join(f"{n}\n" for n in sorted(names)))
        os.chmod(tmp, 0o644)  # lo legge lo script dell'utente sul computer, non solo root
        os.replace(tmp, FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record(names: list[str], action: str) -> None:
    """`stop` aggiunge i container all'elenco; `start` e `restart` li tolgono. Non solleva mai eccezioni."""
    if action not in ("stop", "start", "restart"):
        return
    valid = {n for n in names if NAME_RE.fullmatch(n)}
    if not valid:
        return
    try:
        with _lock:
            current = set(read())
            new = current | valid if action == "stop" else current - valid
            if new != current:
                _write(new)
    except OSError as exc:
        log.warning("Non riesco a salvare lo stato dei servizi spenti in %s: %s", FILE, exc)
