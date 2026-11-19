"""Authenticated, idempotent scan ingestion and local-only device administration."""
from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select

from .models import normalize_bssid
from .storage import Store, devices, observations, registry, sessions, utc_iso

Source = Literal["esp32_c5", "linux_probe", "windows_netsh"]


class DeviceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    collector_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=80)
    location: str = Field(default="", max_length=160)
    source: Source = "esp32_c5"
    interval_seconds: int = Field(default=60, ge=10, le=86400, strict=True)


class DeviceEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    location: str = Field(max_length=160)
    interval_seconds: int = Field(ge=10, le=86400, strict=True)
    enabled: bool


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bssid: str
    ssid: str = Field(max_length=32)
    signal: int | None = Field(default=None, ge=0, le=100, strict=True)
    rssi_dbm: int | None = Field(default=None, ge=-127, le=20, strict=True)
    radio_type: str | None = Field(default=None, max_length=32)
    band: Literal["2.4GHz", "5GHz", "6GHz"] | None = None
    channel: int | None = Field(default=None, ge=1, le=233, strict=True)
    station_count: int | None = Field(default=None, ge=0, le=65535, strict=True)
    channel_utilization_raw: int | None = Field(default=None, ge=0, le=255, strict=True)
    channel_utilization_display_percent: float | None = Field(default=None, ge=0, le=100)
    available_admission_capacity: int | None = Field(default=None, ge=0, le=65535, strict=True)
    _bssid = field_validator("bssid")(normalize_bssid)


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    batch_id: UUID
    collector_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    timestamp: AwareDatetime
    status: Literal["success", "failed"]
    error: str | None = Field(default=None, max_length=1000)
    observations: list[Reading] = Field(max_length=512)

    @model_validator(mode="after")
    def validate_scan(self):
        if self.timestamp > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Scan timestamp is more than 5 minutes in the future")
        if self.status == "failed" and (self.observations or not self.error):
            raise ValueError("Failed scans require an error and no observations")
        if self.status == "success" and self.error:
            raise ValueError("Successful scans cannot include an error")
        ids = [row.bssid for row in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate BSSID in scan")
        return self


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def local_access(request: Request):
    # Never trust forwarded headers. The CLI explicitly disables proxy_headers.
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Device administration is only available on server localhost")
    if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(403, "Local administration requires a loopback Host")
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Cross-origin administration is not allowed")


def local_admin(request: Request):
    local_access(request)
    if request.headers.get("x-local-admin") != "1":
        raise HTTPException(403, "Missing local administration header")


def public_device(row):
    item = dict(row)
    item.pop("token_hash", None)
    item["enabled"] = bool(item["enabled"])
    now = datetime.now(UTC)
    last = item["last_received_at"]
    item["online"] = bool(item["enabled"] and last and (now-datetime.fromisoformat(last)).total_seconds() <= max(180, item["interval_seconds"]*3))
    item["data_fresh"] = bool(item["last_observed_at"] and (now-datetime.fromisoformat(item["last_observed_at"])).total_seconds() <= max(180, item["interval_seconds"]*3))
    return item


def ingest(store: Store, token: str, batch: Batch):
    received = utc_iso(datetime.now(UTC))
    captured = utc_iso(batch.timestamp)
    payload_hash = digest(json.dumps(batch.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))
    with store.engine.connect() as conn:
        # Serialize check-and-insert so concurrent retries cannot insert twice.
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            device = conn.execute(select(devices).where(devices.c.token_hash == digest(token), devices.c.enabled == 1)).mappings().first()
            if not device or device["collector_id"] != batch.collector_id:
                raise HTTPException(401, "Invalid or disabled device credential")
            existing = conn.execute(select(sessions).where(sessions.c.collector_id == batch.collector_id, sessions.c.batch_id == str(batch.batch_id))).mappings().first()
            if existing and existing["payload_hash"] != payload_hash:
                raise HTTPException(409, "batch_id already used for different scan content")
            if existing:
                conn.execute(devices.update().where(devices.c.collector_id == batch.collector_id).values(last_received_at=received))
                conn.commit()
                return {"accepted": True, "duplicate": True, "session_id": existing["id"]}
            result = conn.execute(sessions.insert().values(
                collector_id=batch.collector_id, timestamp=captured, finished_at=captured,
                received_at=received, batch_id=str(batch.batch_id), payload_hash=payload_hash,
                source=device["source"], scan_location=device["location"], status=batch.status, error=batch.error))
            session_id = result.inserted_primary_key[0]
            for reading in batch.observations:
                old = conn.execute(select(registry).where(registry.c.bssid == reading.bssid)).mappings().first()
                values = dict(ssid=reading.ssid, band=reading.band, channel=reading.channel)
                if not old:
                    conn.execute(registry.insert().values(bssid=reading.bssid, first_seen=captured, last_seen=captured, **values))
                else:
                    if captured < old["last_seen"]:
                        values = {}
                    conn.execute(registry.update().where(registry.c.bssid == reading.bssid).values(
                        first_seen=min(captured, old["first_seen"]), last_seen=max(captured, old["last_seen"]), **values))
                conn.execute(observations.insert().values(session_id=session_id, timestamp=captured,
                    collector_id=batch.collector_id, source=device["source"], **reading.model_dump()))
            update = {"last_received_at": received}
            if not device["last_observed_at"] or captured >= device["last_observed_at"]:
                update.update(last_observed_at=captured, last_status=batch.status, last_error=batch.error)
            conn.execute(devices.update().where(devices.c.collector_id == batch.collector_id).values(**update))
            conn.commit()
            return {"accepted": True, "duplicate": False, "session_id": session_id}
        except Exception:
            conn.rollback()
            raise


def router(store: Store):
    routes = APIRouter()

    @routes.get("/api/devices")
    def list_devices():
        with store.engine.connect() as conn:
            return [public_device(row) for row in conn.execute(select(devices).order_by(devices.c.created_at)).mappings()]

    @routes.post("/api/devices", status_code=201)
    def create_device(body: DeviceInput, request: Request):
        local_admin(request)
        token = secrets.token_urlsafe(32)
        with store.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            if conn.execute(select(devices.c.collector_id).where(devices.c.collector_id == body.collector_id)).first() or conn.execute(select(sessions.c.id).where(sessions.c.collector_id == body.collector_id).limit(1)).first():
                raise HTTPException(409, "Collector ID is already in use (including historical collectors)")
            conn.execute(devices.insert().values(**body.model_dump(), token_hash=digest(token), created_at=utc_iso(datetime.now(UTC))))
            conn.commit()
        return {"collector_id": body.collector_id, "token": token}

    @routes.put("/api/devices/{collector_id}")
    def edit_device(collector_id: str, body: DeviceEdit, request: Request):
        local_admin(request)
        with store.engine.begin() as conn:
            result = conn.execute(devices.update().where(devices.c.collector_id == collector_id).values(**body.model_dump()))
            if result.rowcount != 1:
                raise HTTPException(404, "Unknown device")
        return {"updated": True}

    @routes.post("/api/devices/{collector_id}/rotate-key")
    def rotate(collector_id: str, request: Request):
        local_admin(request)
        token = secrets.token_urlsafe(32)
        with store.engine.begin() as conn:
            result = conn.execute(devices.update().where(devices.c.collector_id == collector_id).values(token_hash=digest(token)))
            if result.rowcount != 1:
                raise HTTPException(404, "Unknown device")
        return {"collector_id": collector_id, "token": token}

    @routes.post("/api/collector/observations")
    async def upload(request: Request):
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 256:
            raise HTTPException(401, "Bearer device credential required")
        token = authorization[7:]
        with store.engine.connect() as conn:
            if not conn.execute(select(devices.c.collector_id).where(devices.c.token_hash == digest(token), devices.c.enabled == 1)).first():
                raise HTTPException(401, "Invalid or disabled device credential")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 262144:
                raise HTTPException(413, "Scan payload exceeds 256 KiB")
        try:
            batch = Batch.model_validate_json(data)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors(include_input=False, include_context=False, include_url=False)) from exc
        return ingest(store, token, batch)

    return routes
