from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Config:
    collector_id: str = "windows_01"
    interval_seconds: int = 60
    timeout_seconds: int = 30
    database_path: Path = Path("data/canteen.sqlite3")
    scan_location: str = ""

    @classmethod
    def load(cls, path: Path) -> "Config":
        with path.open("rb") as stream:
            values = tomllib.load(stream)
        unknown = set(values) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        for key in ("interval_seconds", "timeout_seconds"):
            value = values.get(key, getattr(cls(), key))
            if type(value) is not int or value <= 0:
                raise ValueError(f"{key} must be a positive integer")
        for key in ("collector_id", "scan_location"):
            if not isinstance(values.get(key, ""), str):
                raise ValueError(f"{key} must be a string")
        if not values.get("collector_id", cls().collector_id).strip():
            raise ValueError("collector_id must not be empty")
        database = Path(values.get("database_path", cls().database_path))
        values["database_path"] = (path.resolve().parent / database).resolve()
        return cls(**values)
