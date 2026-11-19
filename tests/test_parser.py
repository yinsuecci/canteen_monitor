from datetime import UTC, datetime
from pathlib import Path
import pytest
from canteen_monitor.parser import ParseError, parse_netsh
from canteen_monitor.scanner import decode_output

FIXTURES = Path(__file__).parent / "fixtures"


def parse(text):
    return parse_netsh(text, datetime.now(UTC), "test")


def test_synthetic_english():
    row, = parse((FIXTURES / "synthetic_en.txt").read_text(encoding="utf-8"))
    assert row.bssid == "02:00:00:00:00:02"
    assert row.station_count == 7
    assert row.channel_utilization_raw == 64
    assert row.channel_utilization_percent == pytest.approx(64 / 255 * 100)
    assert row.available_admission_capacity == 10000


def test_synthetic_chinese_multiple_networks():
    a, b, c = parse((FIXTURES / "synthetic_zh.txt").read_text(encoding="utf-8"))
    assert a.station_count == 0
    assert b.station_count is None
    assert b.channel_utilization_raw is None
    assert a.band == "5GHz" and b.band == "2.4GHz"
    assert c.ssid == "Other" and c.station_count == 10
    assert c.channel_utilization_raw is None
    assert c.channel_utilization_display_percent == 13


@pytest.mark.parametrize("text", ["", "Access is denied.", "需要位置权限。", "SSID 1 : test\n BSSID 1 : invalid"])
def test_invalid_output(text):
    with pytest.raises(ParseError):
        parse(text)


@pytest.mark.parametrize("text", ["There are 0 networks currently visible.", "当前有 0 个网络可见。"])
def test_zero_networks(text):
    assert parse(text) == []


def test_validation():
    with pytest.raises(ParseError):
        parse("SSID 1 : x\n BSSID 1 : aa:bb:cc:dd:ee:ff\n  Bss Load:\n   Channel Utilization: 256")


def test_encodings():
    text = "连接的电台: 0"
    assert decode_output(text.encode("utf-8")) == text
    assert decode_output(text.encode("utf-16")) == text
    assert decode_output(text.encode("gb18030")) == text
