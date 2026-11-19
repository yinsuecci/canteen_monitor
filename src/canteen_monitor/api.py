"""Local, read-only dashboard API. No remote collector write surface."""
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .collector import run
from .config import Config
from .models import normalize_bssid
from .storage import Store, observations, registry, sessions, utc_iso


def create_app(config: Config, collect: bool = False, static_dir: Path | None = None):
    store = Store(config.database_path)
    stop = Event()

    @asynccontextmanager
    async def lifespan(app):
        worker = Thread(target=run, args=(config, store, stop), daemon=True) if collect else None
        if worker:
            worker.start()
        yield
        stop.set()
        if worker:
            worker.join(config.timeout_seconds + 5)
        store.close()

    app = FastAPI(title="Canteen Monitor", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/dashboard/summary")
    def summary():
        now = datetime.now(UTC)
        with store.engine.connect() as conn:
            latest_ids = select(func.max(sessions.c.id)).group_by(sessions.c.collector_id)
            latest = [dict(row) for row in conn.execute(select(
                sessions.c.id, sessions.c.timestamp, sessions.c.collector_id,
                sessions.c.status, sessions.c.error, sessions.c.scan_location,
            ).where(sessions.c.id.in_(latest_ids))).mappings()]
            for row in latest:
                age = (now - datetime.fromisoformat(row["timestamp"])).total_seconds()
                row["fresh"] = age <= max(config.interval_seconds * 3, config.timeout_seconds + 60)
            ids = [row["id"] for row in latest if row["status"] == "success"]
            current = [dict(row) for row in conn.execute(select(
                observations, registry.c.location_name, registry.c.confirmed,
                registry.c.confidence,
            ).join(registry).where(observations.c.session_id.in_(ids)).order_by(
                observations.c.timestamp.desc(), observations.c.bssid
            )).mappings()]
            # Multiple collectors can see the same BSSID. Keep the latest reading.
            unique = {}
            for row in current:
                if row["bssid"] not in unique:
                    raw = row["channel_utilization_raw"]
                    row["channel_utilization_percent"] = None if raw is None else raw / 255 * 100
                    unique[row["bssid"]] = row
            mapped = [dict(row) for row in conn.execute(select(registry)).mappings()]
        return {"timestamp": utc_iso(now), "collectors": latest, "aps": list(unique.values()),
                "registry": mapped, "interval_seconds": config.interval_seconds,
                "collector_id": config.collector_id, "collection_enabled": collect,
                "timeout_seconds": config.timeout_seconds}

    @app.get("/api/aps/{bssid}/history")
    def history(bssid: str, collector_id: str = Query(min_length=1), hours: int = Query(24, ge=1, le=168)):
        try:
            bssid = normalize_bssid(bssid)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        cutoff = utc_iso(datetime.now(UTC) - timedelta(hours=hours))
        with store.engine.connect() as conn:
            # Include absent/failed scans as nulls so charts do not imply zero.
            join = sessions.outerjoin(observations, (observations.c.session_id == sessions.c.id) &
                                      (observations.c.bssid == bssid))
            query = select(sessions.c.timestamp, observations.c.station_count,
                           observations.c.channel_utilization_raw).select_from(join).where(
                sessions.c.collector_id == collector_id, sessions.c.timestamp >= cutoff
            ).order_by(sessions.c.timestamp.desc(), sessions.c.id.desc()).limit(10001)
            rows = [dict(row) for row in conn.execute(query).mappings()]
        truncated = len(rows) > 10000
        return {"points": list(reversed(rows[:10000])), "truncated": truncated}

    directory = static_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if directory.is_dir():
        app.mount("/", StaticFiles(directory=directory, html=True), name="dashboard")
    return app
