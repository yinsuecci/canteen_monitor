"""Dashboard and authenticated remote collector API."""
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .collector import run
from .config import Config
from .models import normalize_bssid
from .storage import Store, devices, observations, registry, sessions, utc_iso
from .remote import local_access, router


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

    @app.middleware("http")
    async def privacy_boundary(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in {"/api/health", "/api/collector/observations"}:
            try:
                local_access(request)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(router(store))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/dashboard/summary")
    def summary(include_local: bool = False):
        now = datetime.now(UTC)
        with store.engine.connect() as conn:
            ranked = select(sessions.c.id, func.row_number().over(
                partition_by=sessions.c.collector_id,
                order_by=(sessions.c.timestamp.desc(), sessions.c.id.desc())
            ).label("rank"))
            if not include_local and not collect:
                ranked = ranked.where(sessions.c.batch_id.is_not(None))
            ranked = ranked.subquery()
            latest_ids = select(ranked.c.id).where(ranked.c.rank == 1)
            registered = {row['collector_id']: row for row in conn.execute(select(devices)).mappings()}
            latest = [dict(row) for row in conn.execute(select(
                sessions.c.id, sessions.c.timestamp, sessions.c.collector_id,
                sessions.c.status, sessions.c.error, sessions.c.scan_location,
                sessions.c.received_at, sessions.c.source,
            ).where(sessions.c.id.in_(latest_ids))).mappings()]
            for row in latest:
                age = (now - datetime.fromisoformat(row["timestamp"])).total_seconds()
                device = registered.get(row["collector_id"])
                row["interval_seconds"] = device["interval_seconds"] if device else config.interval_seconds
                row["fresh"] = age <= max(row["interval_seconds"] * 3, config.timeout_seconds + 60) and bool(device["enabled"] if device else True)
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
