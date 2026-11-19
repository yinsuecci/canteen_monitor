import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
from .collector import collect_once, run
from .config import Config
from .storage import Store


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect AP broadcast load, not people counts")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("scan", help="One live scan; exit 1 if failed")
    commands.add_parser("collect", help="Serial scans until Ctrl+C")
    serve = commands.add_parser("serve", help="Local dashboard and read-only API")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 only on an authorized private network or behind HTTPS")
    serve.add_argument("--collect", action="store_true", help="Also run periodic scans")
    history = commands.add_parser("history", help="Latest observations as JSON, UTC timestamps")
    history.add_argument("--bssid")
    history.add_argument("--ssid")
    history.add_argument("--location")
    history.add_argument("--since", type=datetime.fromisoformat)
    history.add_argument("--until", type=datetime.fromisoformat)
    history.add_argument("--limit", type=int, default=1000)
    mapping = commands.add_parser("map", help="Manually label an observed exact BSSID")
    mapping.add_argument("bssid")
    mapping.add_argument("location")
    mapping.add_argument("--confidence", type=float, required=True)
    mapping.add_argument("--confirmed", action="store_true")
    mapping.add_argument("--notes", default="")
    backup = commands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = None
    try:
        config = Config.load(args.config)
        if args.command == "serve":
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(config, collect=args.collect), host=args.host, port=args.port, proxy_headers=False)
            return 0
        store = Store(config.database_path)
        if args.command == "scan":
            result = collect_once(config, store)
            print(json.dumps(result, ensure_ascii=True))
            return int(result["status"] == "failed")
        if args.command == "collect":
            run(config, store)
        elif args.command == "history":
            print(json.dumps(store.history(args.bssid, args.ssid, args.location, args.since, args.until, args.limit), ensure_ascii=True, indent=2))
        elif args.command == "map":
            store.map_ap(args.bssid, args.location, args.confidence, args.confirmed, args.notes)
            print("Mapping saved")
        elif args.command == "backup":
            store.backup(args.destination)
            print(f"Backup created: {args.destination.resolve()}")
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logging.error("%s", exc)
        return 1
    finally:
        if store:
            store.close()
