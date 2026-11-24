"""Stato dei dischi (SMART) per il pannello.

Il controllo vero lo fa ./src/scripts/smart-check.sh SUL COMPUTER (non in un container, vedi docs/smart.md). A ogni esecuzione
vera (cioe' senza --stampa e --test) lo script scrive l'esito in data/panel/smart-status.json; il backend lo legge da
/data/panel (cartella gia' montata) e lo mostra nella schermata Servizi. Qui non si esegue nulla e non si tocca nessun disco.

Un esito vecchio vale come un avviso: se il controllo smette di girare (cron tolto, smartctl rimosso) il pannello lo dice,
invece di continuare a mostrare «tutto bene» per sempre.
"""
import json
import time
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/smart", tags=["smart"])

FILE = Path("/data/panel/smart-status.json")
STALE_S = 36 * 3600     # lo script gira una volta al giorno: oltre un giorno e mezzo qualcosa non va
MAX_ITEMS = 20
MAX_LEN = 300


def _lines(v) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x)[:MAX_LEN] for x in v[:MAX_ITEMS] if isinstance(x, (str, int, float))]


def read_status(now: float | None = None, path: Path | None = None) -> dict:
    now = time.time() if now is None else now
    try:
        raw = json.loads((path or FILE).read_text())
        if not isinstance(raw, dict):
            raise ValueError("non e' un oggetto")
    except FileNotFoundError:
        return {"configured": False, "level": "unknown", "at": None, "age_s": None, "stale": False,
                "checked": 0, "problems": [], "warnings": [], "errors": []}
    except (OSError, ValueError):
        return {"configured": True, "level": "warn", "at": None, "age_s": None, "stale": True, "checked": 0,
                "problems": [], "warnings": [], "errors": ["Il file con l'esito dei dischi non si legge: rilancia smart-check.sh"]}
    at = raw.get("at") if isinstance(raw.get("at"), (int, float)) and not isinstance(raw.get("at"), bool) else None
    age = max(0, int(now - at)) if at else None
    stale = age is None or age > STALE_S
    problems, warnings, errors = _lines(raw.get("problems")), _lines(raw.get("warnings")), _lines(raw.get("errors"))
    checked = raw.get("checked") if isinstance(raw.get("checked"), int) and not isinstance(raw.get("checked"), bool) else 0
    level = "bad" if problems else "warn" if (warnings or errors or stale) else "ok"
    return {"configured": True, "level": level, "at": at, "age_s": age, "stale": stale, "checked": checked,
            "problems": problems, "warnings": warnings, "errors": errors}


@router.get("")
def smart_status():
    return read_status()
