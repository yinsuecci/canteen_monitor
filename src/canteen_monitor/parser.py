"""Parse explicit fields only: missing data never becomes zero."""
import re
from datetime import datetime
from pydantic import ValidationError
from .models import Observation


class ParseError(ValueError):
    pass


KEYS = {
    "signal": "signal", "信号": "signal",
    "radio type": "radio_type", "无线电类型": "radio_type",
    "band": "band", "波段": "band", "频段": "band",
    "channel": "channel", "频道": "channel", "信道": "channel",
    "connected stations": "station_count", "station count": "station_count",
    "连接的电台": "station_count", "连接的站点": "station_count",
    "channel utilization": "channel_utilization_raw", "频道利用率": "channel_utilization_raw",
    "信道利用率": "channel_utilization_raw",
    "medium available capacity": "available_admission_capacity",
    "available admission capacity": "available_admission_capacity",
    "中可用容量": "available_admission_capacity", "可用准入容量": "available_admission_capacity",
}
LOAD_FIELDS = {"station_count", "channel_utilization_raw", "available_admission_capacity"}


def parse_netsh(text: str, timestamp: datetime, collector_id: str) -> list[Observation]:
    records: list[Observation] = []
    current: dict | None = None
    ssid: str | None = None
    load_indent: int | None = None

    def finish():
        if current is not None:
            try:
                records.append(Observation(**current))
            except ValidationError as exc:
                raise ParseError(str(exc)) from exc

    for line in text.splitlines():
        ssid_match = re.match(r"^\s*SSID\s+\d+\s*[:：]\s?(.*)$", line, re.I)
        if ssid_match:
            finish()
            current = None
            ssid = ssid_match[1].strip()
            load_indent = None
            continue
        bssid_match = re.match(r"^\s*BSSID\s+\d+\s*[:：]\s*(.*?)\s*$", line, re.I)
        if bssid_match:
            if ssid is None:
                raise ParseError("BSSID encountered without an SSID")
            finish()
            current = dict(timestamp=timestamp, collector_id=collector_id, ssid=ssid, bssid=bssid_match[1])
            load_indent = None
            continue
        if current is None:
            continue
        pair = re.match(r"^(\s*)([^:：]+)[:：]\s*(.*?)\s*$", line)
        if not pair:
            continue
        indent, key, value = len(pair[1]), pair[2].strip().lower(), pair[3]
        if load_indent is not None and indent <= load_indent:
            load_indent = None
        if key in {"bss load", "bss 负载", "bss负载"}:
            load_indent = indent
            continue
        field = KEYS.get(key)
        if field is None or (field in LOAD_FIELDS and load_indent is None):
            continue
        if field in {"radio_type", "band"}:
            current[field] = re.sub(r"\s+", "", value) if field == "band" else value
            continue
        number = re.match(r"^(\d+)(.*)$", value)
        if not number:
            raise ParseError(f"Invalid numeric field {key}: {value}")
        if field == "channel_utilization_raw":
            # A percent-only output does not provide the raw 0..255 value.
            if number[2].lstrip().startswith("%"):
                current["channel_utilization_display_percent"] = int(number[1])
                continue
            percent = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*%\s*\)", value)
            if percent:
                current["channel_utilization_display_percent"] = float(percent[1])
        current[field] = int(number[1])
    finish()
    if not records:
        # netsh sometimes returns exit code 0 for permission/radio errors.
        zero_networks = re.search(r"(?:there (?:are|is)\s+0\s+networks?|(?:当前|目前).*?0\s*个.*?网络)", text, re.I)
        if not zero_networks:
            raise ParseError("No recognizable networks or explicit zero-network result")
    return records
