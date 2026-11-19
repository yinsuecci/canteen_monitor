from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from sqlalchemy import (Column, Float, ForeignKey, Index, Integer, LargeBinary,
                        MetaData, String, Table, Text, create_engine, event, select)
from .models import Observation, normalize_bssid

metadata = MetaData()
sessions = Table(
    "scan_sessions", metadata,
    Column("id", Integer, primary_key=True),
    Column("timestamp", String, nullable=False, index=True),
    Column("finished_at", String),
    Column("collector_id", String, nullable=False),
    Column("source", String, nullable=False, default="windows_netsh"),
    Column("scan_location", String, nullable=False, default=""),
    Column("status", String, nullable=False),
    Column("returncode", Integer),
    Column("error", Text),
    Column("raw_stdout", LargeBinary),
    Column("raw_stderr", LargeBinary),
    Column("decoded_stdout", Text),
)
registry = Table(
    "ap_registry", metadata,
    Column("bssid", String, primary_key=True),
    Column("ssid", String, nullable=False),
    Column("location_name", String, index=True),
    Column("building", String), Column("area", String),
    Column("band", String), Column("channel", Integer),
    Column("confidence", Float),
    Column("confirmed", Integer, nullable=False, default=0),
    Column("first_seen", String, nullable=False),
    Column("last_seen", String, nullable=False),
    Column("notes", Text),
)
observations = Table(
    "ap_observations", metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", ForeignKey("scan_sessions.id"), nullable=False),
    Column("timestamp", String, nullable=False, index=True),
    Column("collector_id", String, nullable=False),
    Column("source", String, nullable=False),
    Column("ssid", String, nullable=False, index=True),
    Column("bssid", ForeignKey("ap_registry.bssid"), nullable=False, index=True),
    Column("signal", Integer), Column("radio_type", String), Column("band", String),
    Column("channel", Integer), Column("station_count", Integer),
    Column("channel_utilization_raw", Integer),
    Column("channel_utilization_display_percent", Float),
    Column("available_admission_capacity", Integer),
    Index("ix_observations_bssid_timestamp", "bssid", "timestamp"),
)


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


class Store:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine("sqlite:///" + self.path.as_posix(), connect_args={"timeout": 30})

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

        metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()

    def begin_scan(self, timestamp: datetime, collector_id: str, location: str) -> int:
        with self.engine.begin() as connection:
            result = connection.execute(sessions.insert().values(
                timestamp=utc_iso(timestamp), collector_id=collector_id,
                scan_location=location, status="running"))
            return result.inserted_primary_key[0]

    def finish_scan(self, session_id: int, result, decoded: str | None,
                    rows: list[Observation], error: str | None):
        with self.engine.begin() as connection:
            session = connection.execute(select(sessions).where(sessions.c.id == session_id)).mappings().one()
            if session["status"] != "running":
                raise ValueError("Scan has already been finalized")
            if error and rows:
                raise ValueError("Failed scans cannot contain observations")
            for row in rows:
                values = row.model_dump()
                values["timestamp"] = utc_iso(row.timestamp)
                existing = connection.execute(select(registry).where(registry.c.bssid == row.bssid)).mappings().first()
                seen = values["timestamp"]
                updates = dict(ssid=row.ssid, band=row.band, channel=row.channel)
                if existing is None:
                    connection.execute(registry.insert().values(bssid=row.bssid, first_seen=seen, last_seen=seen, **updates))
                else:
                    connection.execute(registry.update().where(registry.c.bssid == row.bssid).values(
                        first_seen=min(seen, existing["first_seen"]), last_seen=max(seen, existing["last_seen"]), **updates))
                connection.execute(observations.insert().values(session_id=session_id, **values))
            connection.execute(sessions.update().where(sessions.c.id == session_id).values(
                finished_at=utc_iso(datetime.now(UTC)), status="failed" if error else "success",
                returncode=result.returncode, error=error, raw_stdout=result.stdout,
                raw_stderr=result.stderr, decoded_stdout=decoded))

    def history(self, bssid: str | None = None, ssid: str | None = None,
                location: str | None = None, since: datetime | None = None,
                until: datetime | None = None, limit: int = 1000):
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        if since and until and since > until:
            raise ValueError("since must be before until")
        query = select(observations)
        if bssid:
            query = query.where(observations.c.bssid == normalize_bssid(bssid))
        if ssid is not None:
            query = query.where(observations.c.ssid == ssid)
        if location is not None:
            # Current manual mapping, not the historical scan vantage point.
            query = query.join(registry).where(registry.c.location_name == location)
        if since:
            query = query.where(observations.c.timestamp >= utc_iso(since))
        if until:
            query = query.where(observations.c.timestamp <= utc_iso(until))
        query = query.order_by(observations.c.timestamp.desc(), observations.c.id.desc()).limit(limit)
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(query).mappings()]
        for row in rows:
            raw = row["channel_utilization_raw"]
            row["channel_utilization_percent"] = None if raw is None else raw / 255 * 100
        return rows

    def map_ap(self, bssid: str, location: str, confidence: float, confirmed: bool, notes: str = ""):
        if not location.strip() or not 0 <= confidence <= 1:
            raise ValueError("Location required and confidence must be in [0, 1]")
        with self.engine.begin() as connection:
            result = connection.execute(registry.update().where(registry.c.bssid == normalize_bssid(bssid)).values(
                location_name=location, confidence=confidence, confirmed=int(confirmed), notes=notes))
            if result.rowcount != 1:
                raise ValueError("BSSID has not been observed")

    def backup(self, destination: Path):
        destination = destination.resolve()
        if destination == self.path or destination.exists():
            raise ValueError("Backup destination must be a new file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)
