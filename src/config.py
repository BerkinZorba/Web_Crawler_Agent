"""Load JSON configuration from disk with simple defaults."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    max_workers: int
    fetch_timeout_sec: float
    queue_max_size: int
    user_agent: str


def default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "default.json"


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or default_config_path()
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    root = cfg_path.resolve().parent.parent
    db = Path(data["db_path"])
    if not db.is_absolute():
        db = root / db
    return AppConfig(
        db_path=db,
        max_workers=int(data.get("max_workers", 4)),
        fetch_timeout_sec=float(data.get("fetch_timeout_sec", 15.0)),
        queue_max_size=int(data.get("queue_max_size", 1000)),
        user_agent=str(data.get("user_agent", "LocalCrawler/1.0")),
    )
