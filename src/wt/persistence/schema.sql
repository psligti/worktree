CREATE TABLE IF NOT EXISTS worktrees (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    branch TEXT,
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

CREATE TABLE IF NOT EXISTS locks (
    worktree_id TEXT PRIMARY KEY,
    owner TEXT,
    locked_at TEXT,
    FOREIGN KEY(worktree_id) REFERENCES worktrees(id)
);

CREATE TABLE IF NOT EXISTS ports (
    worktree_id TEXT NOT NULL,
    key TEXT NOT NULL,
    port INTEGER NOT NULL,
    PRIMARY KEY(worktree_id, key),
    FOREIGN KEY(worktree_id) REFERENCES worktrees(id)
);

CREATE TABLE IF NOT EXISTS settings_cache (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_worktrees_name ON worktrees(name);
CREATE INDEX IF NOT EXISTS idx_worktrees_path ON worktrees(path);
CREATE INDEX IF NOT EXISTS idx_events_worktree_id ON events(worktree_id);
CREATE INDEX IF NOT EXISTS idx_runs_worktree_id ON runs(worktree_id);
