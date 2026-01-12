from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import connect
from ..domain.models import EventRecord, WorktreeRecord


def upsert_worktree(conn, record: WorktreeRecord) -> None:
    data = _serialize_worktree(record)
    conn.execute(
        """
        INSERT INTO worktrees (
            id, name, path, branch, head_sha, base_ref, lifecycle, bootstrap, agent, runtime,
            git_dirty, git_sync, upstream, ahead, behind, behind_main,
            created_at, last_accessed_at, last_error, updated_at
        ) VALUES (
            :id, :name, :path, :branch, :head_sha, :base_ref, :lifecycle, :bootstrap, :agent, :runtime,
            :git_dirty, :git_sync, :upstream, :ahead, :behind, :behind_main,
            :created_at, :last_accessed_at, :last_error, :updated_at
        )
        ON CONFLICT(path) DO UPDATE SET
            id = excluded.id,
            name = excluded.name,
            branch = excluded.branch,
            head_sha = excluded.head_sha,
            base_ref = excluded.base_ref,
            lifecycle = excluded.lifecycle,
            bootstrap = excluded.bootstrap,
            agent = excluded.agent,
            runtime = excluded.runtime,
            git_dirty = excluded.git_dirty,
            git_sync = excluded.git_sync,
            upstream = excluded.upstream,
            ahead = excluded.ahead,
            behind = excluded.behind,
            behind_main = excluded.behind_main,
            last_accessed_at = excluded.last_accessed_at,
            last_error = excluded.last_error,
            updated_at = excluded.updated_at
        """,
        data,
    )


def list_worktrees(repo_root: str) -> list[WorktreeRecord]:
    with connect(repo_root) as conn:
        rows = conn.execute("SELECT * FROM worktrees ORDER BY name").fetchall()
    return [_worktree_from_row(row) for row in rows]


def get_worktree_by_name(repo_root: str, name: str) -> Optional[WorktreeRecord]:
    with connect(repo_root) as conn:
        row = conn.execute("SELECT * FROM worktrees WHERE name = ?", (name,)).fetchone()
    return _worktree_from_row(row) if row else None


def mark_missing_paths(repo_root: str, present_paths: set[str]) -> None:
    with connect(repo_root) as conn:
        rows = conn.execute("SELECT id, path FROM worktrees").fetchall()
        for row in rows:
            if row["path"] not in present_paths:
                conn.execute(
                    "UPDATE worktrees SET lifecycle = ?, updated_at = ? WHERE id = ?",
                    ("ABSENT", datetime.now(timezone.utc).isoformat(), row["id"]),
                )


def record_event(repo_root: str, event: EventRecord) -> None:
    data = event.model_dump(mode="json")
    data["cmd"] = json.dumps(data["cmd"]) if data.get("cmd") else None
    with connect(repo_root) as conn:
        conn.execute(
            """
            INSERT INTO events (id, worktree_id, at, type, from_state, to_state, cmd, exit_code, message)
            VALUES (:id, :worktree_id, :at, :type, :from_state, :to_state, :cmd, :exit_code, :message)
            """,
            data,
        )


def update_worktree_state(repo_root: str, worktree_id: str, **updates: object) -> None:
    if not updates:
        return
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    columns = ", ".join(f"{key} = :{key}" for key in updates.keys())
    updates["id"] = worktree_id
    with connect(repo_root) as conn:
        conn.execute(f"UPDATE worktrees SET {columns} WHERE id = :id", updates)


def upsert_ports(repo_root: str, worktree_id: str, ports: dict[str, int]) -> None:
    with connect(repo_root) as conn:
        for key, port in ports.items():
            conn.execute(
                """
                INSERT INTO ports (worktree_id, key, port)
                VALUES (?, ?, ?)
                ON CONFLICT(worktree_id, key) DO UPDATE SET port = excluded.port
                """,
                (worktree_id, key, port),
            )


def list_ports(repo_root: str) -> dict[str, int]:
    with connect(repo_root) as conn:
        rows = conn.execute("SELECT key, port FROM ports").fetchall()
    return {row["key"]: int(row["port"]) for row in rows}


def _serialize_worktree(record: WorktreeRecord) -> dict[str, object]:
    data = record.model_dump(mode="json")
    data["path"] = str(record.path)
    return data


def _worktree_from_row(row) -> WorktreeRecord:
    if row is None:
        raise ValueError("missing worktree row")
    data = dict(row)
    data["path"] = Path(data["path"])
    return WorktreeRecord.model_validate(data)
