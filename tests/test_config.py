import pytest
from canteen_monitor.config import Config


def test_relative_database(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('database_path = "data/test.db"', encoding="utf-8")
    assert Config.load(path).database_path == tmp_path / "data/test.db"


@pytest.mark.parametrize("content", ['interval_seconds = 0', 'timeout_seconds = true', 'collector_id = ""', 'unknown = 1'])
def test_bad_config(tmp_path, content):
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        Config.load(path)
