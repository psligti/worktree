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
    schema = """
    CREATE TABLE IF NOT EXISTS worktrees (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        branch TEXT,
        purpose TEXT,
        head_sha TEXT,
        base_ref TEXT,
        lifecycle TEXT NOT NULL,
        bootstrap TEXT NOT NULL,
        agent TEXT NOT NULL,
        runtime TEXT NOT NULL,
        git_dirty INTEGER NOT NULL DEFAULT 0,
        git_sync TEXT,
        upstream TEXT,
        ahead INTEGER NOT NULL DEFAULT 0,
        behind INTEGER NOT NULL DEFAULT 0,
        behind_main INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        last_accessed_at TEXT,
        last_error TEXT,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        worktree_id TEXT NOT NULL,
        at TEXT NOT NULL,
        type TEXT NOT NULL,
        from_state TEXT,
        to_state TEXT,
        cmd TEXT,
        exit_code INTEGER,
        message TEXT,
        FOREIGN KEY(worktree_id) REFERENCES worktrees(id)
    );
    CREATE TABLE IF NOT EXISTS locks (
        worktree_id TEXT PRIMARY KEY,
        owner TEXT,
        locked_at TEXT,
        FOREIGN KEY(worktree_id) REFERENCES worktrees(id)
    );
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        worktree_id TEXT NOT NULL,
        cmd TEXT NOT NULL,
        status TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        exit_code INTEGER,
        output_path TEXT,
        FOREIGN KEY(worktree_id) REFERENCES worktrees(id)
    );
    CREATE TABLE IF NOT EXISTS ports (
        worktree_id TEXT NOT NULL,
        key TEXT NOT NULL,
        port INTEGER NOT NULL,
        PRIMARY KEY (worktree_id, key),
        FOREIGN KEY(worktree_id) REFERENCES worktrees(id)
    );
    CREATE TABLE IF NOT EXISTS settings_cache (
        id TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS services (
        id TEXT PRIMARY KEY,
        worktree_id TEXT NOT NULL,
        name TEXT NOT NULL,
        pane_id TEXT,
        status TEXT NOT NULL DEFAULT 'stopped',
        pid INTEGER,
        started_at TEXT,
        stopped_at TEXT,
        last_health_check TEXT,
        health_status TEXT DEFAULT 'unknown',
        FOREIGN KEY(worktree_id) REFERENCES worktrees(id),
        UNIQUE(worktree_id, name)
    );
    CREATE TABLE IF NOT EXISTS pull_requests (
        id TEXT PRIMARY KEY,
        worktree_id TEXT NOT NULL,
        number INTEGER NOT NULL,
        title TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'open',
        url TEXT NOT NULL,
        head_branch TEXT NOT NULL,
        base_branch TEXT NOT NULL,
        draft INTEGER NOT NULL DEFAULT 0,
        mergeable INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        merged_at TEXT,
        closed_at TEXT,
        FOREIGN KEY(worktree_id) REFERENCES worktrees(id),
        UNIQUE(worktree_id, number)
    );
    CREATE TABLE IF NOT EXISTS containers (
        id TEXT PRIMARY KEY,
        worktree_id TEXT NOT NULL,
        name TEXT NOT NULL,
        container_id TEXT NOT NULL,
        container_name TEXT NOT NULL,
        image TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'created',
        started_at TEXT,
        stopped_at TEXT,
        ports TEXT,
        FOREIGN KEY(worktree_id) REFERENCES worktrees(id),
        UNIQUE(worktree_id, name)
    );
    CREATE INDEX IF NOT EXISTS idx_worktrees_name ON worktrees(name);
    CREATE INDEX IF NOT EXISTS idx_worktrees_path ON worktrees(path);
    CREATE INDEX IF NOT EXISTS idx_events_worktree_id ON events(worktree_id);
    CREATE INDEX IF NOT EXISTS idx_runs_worktree_id ON runs(worktree_id);
    CREATE INDEX IF NOT EXISTS idx_services_worktree_id ON services(worktree_id);
    CREATE INDEX IF NOT EXISTS idx_pull_requests_worktree_id ON pull_requests(worktree_id);
    CREATE INDEX IF NOT EXISTS idx_containers_worktree_id ON containers(worktree_id);
    """
    with connect(repo_root) as conn:
        conn.executescript(schema)


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, column_type: str
) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
