from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from threading import Event
from unittest.mock import patch
import pytest
from sqlalchemy import select
from canteen_monitor.collector import collect_once, run
from canteen_monitor.config import Config
from canteen_monitor.scanner import ScanResult
from canteen_monitor.storage import Store, observations, registry, sessions

SAMPLE = (Path(__file__).parent / "fixtures" / "synthetic_zh.txt").read_bytes()


@pytest.fixture
def setup(tmp_path):
    config = Config(database_path=tmp_path / "db.sqlite3", scan_location="test vantage")
    store = Store(config.database_path)
    yield config, store
    store.close()


def success(_):
    return ScanResult(stdout=SAMPLE, returncode=0)


def test_append_restart_and_mapping(setup):
    config, store = setup
    first = collect_once(config, store, success)
    assert first["ap_count"] == 3 and first["bss_load_count"] == 2
    store.map_ap("AA:BB:CC:DD:EE:01", "candidate canteen", .4, False)
    collect_once(config, store, success)
    store.close()
    reopened = Store(config.database_path)
    try:
        assert len(reopened.history()) == 6
        rows = reopened.history(bssid="AA:BB:CC:DD:EE:01")
        assert len(rows) == 2 and rows[0]["station_count"] == 0
        assert rows[0]["timestamp"].endswith("+00:00")
        assert len(reopened.history(location="candidate canteen")) == 2
        assert len(reopened.history(ssid="Other")) == 2
        with reopened.engine.connect() as conn:
            session = conn.execute(select(sessions)).mappings().first()
            assert session["raw_stdout"] == SAMPLE
            assert session["scan_location"] == "test vantage"
            mapped = conn.execute(select(registry).where(registry.c.bssid == "aa:bb:cc:dd:ee:01")).mappings().one()
            assert mapped["confirmed"] == 0 and mapped["confidence"] == .4
    finally:
        reopened.close()


@pytest.mark.parametrize("result", [
    ScanResult(b"Access denied", b"error", 1, "netsh exit code 1"),
    ScanResult(b"Location permission required", returncode=0),
    ScanResult(b"partial", error="timeout"),
    ScanResult(b"\xff", returncode=0),
])
def test_failures_do_not_create_observations(setup, result):
    config, store = setup
    summary = collect_once(config, store, lambda _: result)
    assert summary["status"] == "failed"
    assert store.history() == []
    with store.engine.connect() as conn:
        session = conn.execute(select(sessions)).mappings().one()
        assert session["raw_stdout"] == result.stdout
        assert session["raw_stderr"] == result.stderr
        assert session["error"]


def test_no_ap_not_zero_observation(setup):
    config, store = setup
    collect_once(config, store, success)
    summary = collect_once(config, store, lambda _: ScanResult(b"There are 0 networks currently visible.", returncode=0))
    assert summary["status"] == "success" and summary["ap_count"] == 0
    assert len(store.history()) == 3


def test_backup(setup, tmp_path):
    config, store = setup
    collect_once(config, store, success)
    destination = tmp_path / "backup.sqlite3"
    store.backup(destination)
    with sqlite3.connect(destination) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM ap_observations").fetchone()[0] == 3
    with pytest.raises(ValueError):
        store.backup(destination)
    with pytest.raises(ValueError):
        store.backup(config.database_path)


def test_finalized_scan_cannot_overwrite_history(setup):
    config, store = setup
    summary = collect_once(config, store, success)
    with pytest.raises(ValueError):
        store.finish_scan(summary["session_id"], success(1), "", [], "bad")
    assert len(store.history()) == 3


def test_query_validation(setup):
    _, store = setup
    for args in ({"bssid": "invalid"}, {"limit": 0}, {"since": datetime(2026, 1, 1)}):
        with pytest.raises(ValueError):
            store.history(**args)


def test_scheduler_continues_after_failure(setup):
    config, store = setup

    class Stop:
        calls = 0

        def is_set(self):
            return self.calls >= 2

        def wait(self, seconds):
            assert seconds == 60
            self.calls += 1

    with patch("canteen_monitor.collector.collect_once", side_effect=[RuntimeError("transient"), {"error": None}]) as collect:
        run(config, store, Stop())
        assert collect.call_count == 2


def test_scheduler_already_stopped(setup):
    config, store = setup
    stop = Event()
    stop.set()
    with patch("canteen_monitor.collector.collect_once") as collect:
        run(config, store, stop)
        collect.assert_not_called()
