"""Durable at-least-once upload queue. Server batch IDs make delivery idempotent."""
import argparse
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import sqlite3
from threading import Event
import tomllib
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from .parser import parse_netsh
from .remote import Batch
from .scanner import decode_output, scan

logger = logging.getLogger(__name__)


class UploadQueue:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS pending (batch_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created INTEGER NOT NULL, last_error TEXT)")
        self.connection.commit()

    def enqueue(self, batch: Batch):
        payload = batch.model_dump_json()
        old = self.connection.execute("SELECT payload FROM pending WHERE batch_id=?", (str(batch.batch_id),)).fetchone()
        if old and old[0] != payload:
            raise ValueError("Queued batch ID already has different content")
        self.connection.execute("INSERT OR IGNORE INTO pending(batch_id,payload,created) VALUES(?,?,?)", (str(batch.batch_id), payload, int(datetime.now(UTC).timestamp()*1000000)))
        self.connection.commit()

    def flush(self, client, endpoint: str, token: str, limit=100):
        sent = 0
        for batch_id, payload in self.connection.execute("SELECT batch_id,payload FROM pending ORDER BY created LIMIT ?", (limit,)).fetchall():
            error = None
            try:
                response = client.post(endpoint, content=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                if response.status_code != 200:
                    error = f"HTTP {response.status_code}"
                else:
                    ack = response.json()
                    if ack.get("accepted") is not True:
                        error = "Missing acceptance acknowledgement"
            except (httpx.HTTPError, ValueError, AttributeError):
                error = "Connection failed or invalid acknowledgement"
            if error:
                self.connection.execute("UPDATE pending SET last_error=? WHERE batch_id=?", (error, batch_id))
                self.connection.commit()
                logger.warning("Upload retained in queue: %s", error)
                break
            self.connection.execute("DELETE FROM pending WHERE batch_id=?", (batch_id,))
            self.connection.commit()
            sent += 1
        return sent

    def close(self):
        self.connection.close()


def windows_batch(collector_id: str, timeout: int) -> Batch:
    timestamp = datetime.now(UTC)
    result = scan(timeout)
    error = result.error
    rows = []
    if not error:
        try:
            rows = [row.model_dump(exclude={"timestamp", "collector_id", "source"}) for row in parse_netsh(decode_output(result.stdout), timestamp, collector_id)]
        except ValueError as exc:
            error = str(exc)[:1000]
    return Batch(batch_id=uuid4(), collector_id=collector_id, timestamp=timestamp,
                 status="failed" if error else "success", error=error, observations=rows)


def main():
    parser = argparse.ArgumentParser(description="Remote collector uploader; use --enqueue for Linux/other sensor JSON")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--enqueue", type=Path, help="Queue a protocol-v1 scan JSON without starting Windows scans")
    parser.add_argument("--flush-only", action="store_true", help="Upload existing queue, do not scan")
    parser.add_argument("--once", action="store_true", help="One scan/upload attempt")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    queue = None
    try:
        with args.config.open("rb") as file:
            config = tomllib.load(file)
        url = config["server_url"].rstrip("/")
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
            raise ValueError("server_url must be a plain server origin, without credentials or query")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and config.get("allow_insecure_http") is True):
            raise ValueError("HTTPS required; private-network HTTP requires explicit allow_insecure_http=true")
        interval, timeout = config.get("interval_seconds", 60), config.get("timeout_seconds", 30)
        if type(interval) is not int or interval < 10 or type(timeout) is not int or timeout < 1:
            raise ValueError("Invalid interval or timeout")
        token = os.environ.get(config.get("token_env", "CANTEEN_DEVICE_TOKEN"), "")
        if not token:
            raise ValueError("Device token environment variable is missing")
        path = args.config.resolve().parent / config.get("queue_path", "data/upload-queue.sqlite3")
        queue = UploadQueue(path)
        if args.enqueue:
            batch = Batch.model_validate_json(args.enqueue.read_bytes())
            if batch.collector_id != config["collector_id"]:
                raise ValueError("Input collector_id does not match configuration")
            queue.enqueue(batch)
        backoff = interval
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            while True:
                if not args.enqueue and not args.flush_only:
                    queue.enqueue(windows_batch(config["collector_id"], timeout))
                count = queue.flush(client, url + "/api/collector/observations", token)
                remaining = queue.connection.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
                logger.info("Uploaded %s batches; %s queued", count, remaining)
                if args.once or args.enqueue or args.flush_only:
                    return int(remaining > 0)
                Event().wait(backoff)
                backoff = min(backoff * 2, 300) if remaining else interval
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logger.error("%s", exc)
        return 1
    finally:
        if queue:
            queue.close()


if __name__ == "__main__":
    raise SystemExit(main())
