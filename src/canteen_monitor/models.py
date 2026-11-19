from pydantic import AwareDatetime, BaseModel, Field, field_validator


def normalize_bssid(value: str) -> str:
    import re
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", value):
        raise ValueError("BSSID must contain six colon-separated hexadecimal octets")
    return value.lower()


class Observation(BaseModel):
    timestamp: AwareDatetime
    collector_id: str = Field(min_length=1)
    source: str = "windows_netsh"
    ssid: str
    bssid: str
    signal: int | None = Field(default=None, ge=0, le=100)
    radio_type: str | None = None
    band: str | None = None
    channel: int | None = Field(default=None, ge=1, le=233)
    station_count: int | None = Field(default=None, ge=0, le=65535)
    channel_utilization_raw: int | None = Field(default=None, ge=0, le=255)
    channel_utilization_display_percent: float | None = Field(default=None, ge=0, le=100)
    available_admission_capacity: int | None = Field(default=None, ge=0, le=65535)

    _bssid = field_validator("bssid")(normalize_bssid)

    @property
    def channel_utilization_percent(self) -> float | None:
        raw = self.channel_utilization_raw
        return None if raw is None else raw / 255 * 100
