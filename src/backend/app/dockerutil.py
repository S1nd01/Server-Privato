import threading

import docker
from docker.errors import DockerException
from fastapi import HTTPException

_client: docker.DockerClient | None = None
_lock = threading.Lock()


def get_client() -> docker.DockerClient:
    """Un solo client per tutto il backend (le richieste lo condividono: e' pensato per i thread).

    Prima ne nasceva uno a ogni richiesta e non veniva mai chiuso. Se Docker non risponde non si memorizza nulla:
    la richiesta dopo riprova.
    """
    global _client
    with _lock:
        if _client is None:
            try:
                _client = docker.from_env(max_pool_size=16)
            except DockerException as exc:
                raise HTTPException(503, f"Docker non raggiungibile: {exc}")
        return _client
