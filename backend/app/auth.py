import hmac
import os

from fastapi import HTTPException, Request


def require_token(request: Request) -> None:
    """Se API_TOKEN e' impostato, ogni chiamata /api (tranne health) richiede l'header X-API-Token."""
    token = os.environ.get("API_TOKEN", "")
    if not token or request.url.path == "/api/health":
        return
    given = request.headers.get("x-api-token", "")
    if not hmac.compare_digest(given, token):
        raise HTTPException(401, "Token mancante o errato")
