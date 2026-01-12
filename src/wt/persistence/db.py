from __future__ import annotations

import sqlite3
from pathlib import Path


def db_path(repo_root: str) -> Path:
    return Path(repo_root) / ".wt" / "state" / "wt.db"


def ensure_state_dirs(repo_root: str) -> None:
    state_dir = Path(repo_root) / ".wt" / "state"
    logs_dir = Path(repo_root) / ".wt" / "logs"
    cache_dir = Path(repo_root) / ".wt" / "cache"
    for path in (state_dir, logs_dir, cache_dir):
        path.mkdir(parents=True, exist_ok=True)


def connect(repo_root: str) -> sqlite3.Connection:
    ensure_state_dirs(repo_root)
    path = db_path(repo_root)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(repo_root: str) -> None:
    ensure_state_dirs(repo_root)
    schema_path = Path(__file__).with_name("schema.sql")
    schema = schema_path.read_text(encoding="utf-8")
    with connect(repo_root) as conn:
        conn.executescript(schema)
