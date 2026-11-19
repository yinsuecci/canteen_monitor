from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from canteen_monitor.api import create_app
from canteen_monitor.config import Config
from canteen_monitor.models import Observation
from canteen_monitor.scanner import ScanResult
from canteen_monitor.storage import Store

BSSID = "aa:bb:cc:dd:ee:01"


def insert(store, timestamp, collector="one", count=0, failed=False, absent=False):
    session = store.begin_scan(timestamp, collector, "")
    rows = [] if failed or absent else [Observation(timestamp=timestamp, collector_id=collector, ssid="test", bssid=BSSID, station_count=count)]
    store.finish_scan(session, ScanResult(returncode=1 if failed else 0), "", rows, "test failure" if failed else None)


def test_empty_and_validation(tmp_path):
    with TestClient(create_app(Config(database_path=tmp_path / "db"))) as client:
        assert client.get('/api/health').json() == {"status": "ok"}
        assert client.get('/api/dashboard/summary').json()['aps'] == []
        assert client.get('/api/aps/bad/history?collector_id=one').status_code == 422
        assert client.get(f'/api/aps/{BSSID}/history?collector_id=one&hours=999').status_code == 422
        assert client.get(f'/api/aps/{BSSID}/history').status_code == 422
        assert client.post('/api/dashboard/summary', json={}).status_code == 405


def test_latest_zero_and_stale(tmp_path):
    config = Config(database_path=tmp_path / "db")
    store = Store(config.database_path)
    insert(store, datetime.now(UTC)-timedelta(hours=2), count=10)
    insert(store, datetime.now(UTC)-timedelta(hours=1), count=0)
    with TestClient(create_app(config)) as client:
        result = client.get('/api/dashboard/summary').json()
        assert len(result['aps']) == 1
        assert result['aps'][0]['station_count'] == 0
        assert result['aps'][0]['channel_utilization_percent'] is None
        assert result['collectors'][0]['fresh'] is False
        assert len(result['registry']) == 1
    store.close()


def test_latest_failure_and_history_gaps(tmp_path):
    config = Config(database_path=tmp_path / "db")
    store = Store(config.database_path)
    now = datetime.now(UTC)
    insert(store, now-timedelta(minutes=3), count=7)
    insert(store, now-timedelta(minutes=2), absent=True)
    insert(store, now-timedelta(minutes=1), failed=True)
    with TestClient(create_app(config)) as client:
        result = client.get('/api/dashboard/summary').json()
        assert result['aps'] == []
        assert result['collectors'][0]['status'] == 'failed'
        points = client.get(f'/api/aps/{BSSID}/history?collector_id=one').json()['points']
        assert [p['station_count'] for p in points] == [7, None, None]
    store.close()


def test_multiple_collectors_deduplicate_and_filter_history(tmp_path):
    config = Config(database_path=tmp_path / "db")
    store = Store(config.database_path)
    insert(store, datetime.now(UTC)-timedelta(minutes=1), count=5)
    insert(store, datetime.now(UTC), collector="two", count=9)
    with TestClient(create_app(config)) as client:
        result = client.get('/api/dashboard/summary').json()
        assert len(result['collectors']) == 2
        assert len(result['aps']) == 1
        assert result['aps'][0]['station_count'] == 9
        points = client.get(f'/api/aps/{BSSID}/history?collector_id=one').json()['points']
        assert [p['station_count'] for p in points] == [5]
    store.close()


def test_static(tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html>Dashboard</html>", encoding="utf-8")
    with TestClient(create_app(Config(database_path=tmp_path / "db"), static_dir=static)) as client:
        assert "Dashboard" in client.get('/').text
        assert client.get('/api/health').json()['status'] == 'ok'
