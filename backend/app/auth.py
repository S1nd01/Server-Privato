"""Autenticazione del pannello con token nell'header X-API-Token.

- In `.env` si conserva solo l'HASH del token (API_TOKEN_HASH=sha256:<hex>), mai il token in chiaro.
  Il token e' casuale a 256 bit: per questo basta SHA-256 (lo "stretching" serve per password umane,
  qui costerebbe solo CPU a chi manda richieste sbagliate). Si genera con scripts/gen-api-token.sh.
- Il token viene letto SOLO dall'header: mai da URL/query (finirebbe in log e cronologia).
- Formato rigido (solo [A-Za-z0-9_-], 32-128 caratteri): qualsiasi altra cosa e' rifiutata
  senza essere elaborata ne' riportata nei messaggi d'errore.
- Confronto a tempo costante; dopo troppi errori da uno stesso client risposta 429.
- Compatibilita': se c'e' solo API_TOKEN (vecchio, in chiaro) viene confrontato comunque come hash.
"""

import hashlib
import hmac
import os
import re
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32,128}")
HASH_RE = re.compile(r"[0-9a-f]{64}")
MAX_FAILS = 10
WINDOW_S = 60.0

_fails: dict[str, deque] = defaultdict(deque)


def _expected_digest() -> str | None:
    """None = autenticazione disattivata. Configurazione non valida => errore (si chiude, non si apre)."""
    configured = os.environ.get("API_TOKEN_HASH", "").strip()
    if configured:
        algo, _, digest = configured.partition(":")
        if algo != "sha256" or not HASH_RE.fullmatch(digest):
            raise HTTPException(503, "API_TOKEN_HASH non valido: rigenera con scripts/gen-api-token.sh")
        return digest
    legacy = os.environ.get("API_TOKEN", "")
    if legacy:
        return hashlib.sha256(legacy.encode()).hexdigest()
    return None


def _client_key(request: Request) -> str:
    # X-Real-IP lo imposta nginx (che sovrascrive quello del client); il backend non e' pubblicato.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def require_token(request: Request) -> None:
    if request.url.path == "/api/health":
        return
    expected = _expected_digest()
    if expected is None:
        return

    key = _client_key(request)
    now = time.monotonic()
    recent = _fails[key]
    while recent and now - recent[0] > WINDOW_S:
        recent.popleft()
    if len(recent) >= MAX_FAILS:
        raise HTTPException(429, "Troppi tentativi, riprova tra un minuto", headers={"Retry-After": "60"})

    given = request.headers.get("x-api-token", "")
    ok = bool(TOKEN_RE.fullmatch(given)) and hmac.compare_digest(
        hashlib.sha256(given.encode()).hexdigest(), expected
    )
    if not ok:
        recent.append(now)
        raise HTTPException(401, "Token mancante o errato")
    if not recent:
        _fails.pop(key, None)
