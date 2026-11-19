from datetime import UTC, datetime
import logging
from .config import Config
from .parser import parse_netsh
from .scanner import decode_output, scan
from .storage import Store

logger = logging.getLogger(__name__)


def collect_once(config: Config, store: Store, scanner=scan) -> dict:
    timestamp = datetime.now(UTC)
    session_id = store.begin_scan(timestamp, config.collector_id, config.scan_location)
    result = scanner(config.timeout_seconds)
    decoded = None
    rows = []
    error = result.error
    try:
        decoded = decode_output(result.stdout)
        if not error:
            if result.returncode != 0:
                error = f"Unexpected netsh return code: {result.returncode}"
            else:
                rows = parse_netsh(decoded, timestamp, config.collector_id)
    except ValueError as exc:
        error = error or str(exc)
    store.finish_scan(session_id, result, decoded, rows, error)
    return dict(session_id=session_id, status="failed" if error else "success",
                ap_count=len(rows), bss_load_count=sum(r.station_count is not None for r in rows), error=error)


def run(config: Config, store: Store, stop=None):
    """Serial fixed-delay scans; do not overlap or replay missed intervals."""
    from threading import Event
    stop = stop if stop is not None else Event()
    while not stop.is_set():
        try:
            result = collect_once(config, store)
            logger.log(logging.ERROR if result["error"] else logging.INFO, "%s", result)
        except Exception:
            # Storage failures must be visible, never reported as successful scans.
            logger.exception("Collection failed; a running session may require inspection")
        stop.wait(config.interval_seconds)
