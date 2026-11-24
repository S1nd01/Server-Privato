from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from docker.errors import APIError, NotFound
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def action_api(monkeypatch):
    token = "test-" + "x" * 40
    monkeypatch.delenv("API_TOKEN_HASH", raising=False)
    monkeypatch.setenv("API_TOKEN", token)
    lookup = Mock()
    record = Mock()
    monkeypatch.setattr(main, "_client", lambda: SimpleNamespace(containers=SimpleNamespace(get=lookup)))
    monkeypatch.setattr(main.desired, "record", record)
    return TestClient(main.app, headers={"X-API-Token": token}), lookup, record


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_rifiuto_docker_risponde_502(action_api, action):
    api, lookup, record = action_api
    getattr(lookup.return_value, action).side_effect = APIError("Operazione rifiutata")

    response = api.post(f"/api/services/jellyfin/{action}")

    assert response.status_code == 502
    assert "jellyfin" in response.json()["detail"]
    assert "Operazione rifiutata" in response.json()["detail"]
    record.assert_not_called()


@pytest.mark.parametrize("error, status", [(APIError("Errore Docker"), 502), (NotFound("Container assente"), 409)])
def test_errore_ricerca_container(action_api, error, status):
    api, lookup, record = action_api
    lookup.side_effect = error

    assert api.post("/api/services/jellyfin/start").status_code == status
    record.assert_not_called()
