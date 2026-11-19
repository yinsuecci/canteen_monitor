import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("privacy_guard", Path(__file__).parents[1] / "scripts/check_privacy.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_private_artifacts_blocked():
    for path in [".env", "data/archive.txt", "backup.sqlite3", "probe-credentials.json", "docs/screenshots/demo.png"]:
        assert guard.inspect(path, b"example")
    assert not guard.inspect("collector-config.example.toml", b"example")


def test_only_synthetic_identifiers_and_no_secret_output():
    assert guard.inspect("fixture.txt", b"00:" + b"11:22:33:44:55") == ["non-synthetic AP identifier"]
    assert not guard.inspect("fixture.txt", b"02:00:00:00:00:01")
    assert guard.inspect("config.txt", b"ghp_" + b"x" * 36) == ["credential"]
