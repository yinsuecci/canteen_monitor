import pytest
from fastapi.testclient import TestClient

from canteen_monitor.api import create_app
from canteen_monitor.config import Config


@pytest.mark.parametrize("path", [
    "/api/devices", "/api/dashboard/summary?include_local=true",
    "/api/aps/02:00:00:00:00:01/history?collector_id=test",
])
@pytest.mark.parametrize("host,peer,headers", [
    ("localhost", "192.0.2.1", {"X-Forwarded-For": "127.0.0.1"}),
    ("attacker.example", "127.0.0.1", {}),
    ("localhost", "127.0.0.1", {"Origin": "https://attacker.example"}),
])
def test_private_reads_reject_remote_and_rebinding(tmp_path, path, host, peer, headers):
    with TestClient(create_app(Config(database_path=tmp_path / "test.db")),
                    base_url=f"http://{host}", client=(peer, 5000)) as client:
        assert client.get(path, headers=headers).status_code == 403
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/collector/observations", json={}).status_code == 401


def test_private_response_not_cached(tmp_path):
    with TestClient(create_app(Config(database_path=tmp_path / "test.db")),
                    base_url="http://localhost", client=("127.0.0.1", 5000)) as client:
        response = client.get("/api/devices")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-frame-options"] == "DENY"
