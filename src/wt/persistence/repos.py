from __future__ import annotations

import json
import uuid
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
            id, name, path, branch, purpose, head_sha, base_ref, lifecycle, bootstrap, agent, runtime,
            git_dirty, git_sync, upstream, ahead, behind, behind_main,
            created_at, last_accessed_at, last_error, updated_at
        ) VALUES (
            :id, :name, :path, :branch, :purpose, :head_sha, :base_ref, :lifecycle, :bootstrap, :agent, :runtime,
            :git_dirty, :git_sync, :upstream, :ahead, :behind, :behind_main,
            :created_at, :last_accessed_at, :last_error, :updated_at
        )
        ON CONFLICT(path) DO UPDATE SET
            id = excluded.id,
            name = excluded.name,
            branch = excluded.branch,
            purpose = excluded.purpose,
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


def list_events(repo_root: str, worktree_id: str, limit: int = 5) -> list[EventRecord]:
    with connect(repo_root) as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE worktree_id = ? ORDER BY at DESC LIMIT ?",
            (worktree_id, limit),
        ).fetchall()
    return [_event_from_row(row) for row in rows]


def upsert_lock(repo_root: str, worktree_id: str, owner: str | None = None) -> None:
    locked_at = datetime.now(timezone.utc).isoformat()
    with connect(repo_root) as conn:
        conn.execute(
            """
            INSERT INTO locks (worktree_id, owner, locked_at)
            VALUES (?, ?, ?)
            ON CONFLICT(worktree_id) DO UPDATE SET owner = excluded.owner, locked_at = excluded.locked_at
            """,
            (worktree_id, owner, locked_at),
        )


def clear_lock(repo_root: str, worktree_id: str) -> None:
    with connect(repo_root) as conn:
        conn.execute("DELETE FROM locks WHERE worktree_id = ?", (worktree_id,))


def record_run_start(repo_root: str, worktree_id: str, cmd: str) -> str:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    with connect(repo_root) as conn:
        conn.execute(
            """
            INSERT INTO runs (id, worktree_id, cmd, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, worktree_id, cmd, "running", started_at),
        )
    return run_id


def record_run_finish(repo_root: str, run_id: str, exit_code: int, output_path: str | None) -> None:
    ended_at = datetime.now(timezone.utc).isoformat()
    status = "success" if exit_code == 0 else "failed"
    with connect(repo_root) as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = ?, ended_at = ?, exit_code = ?, output_path = ?
            WHERE id = ?
            """,
            (status, ended_at, exit_code, output_path, run_id),
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


def _event_from_row(row) -> EventRecord:
    if row is None:
        raise ValueError("missing event row")
    data = dict(row)
    if data.get("cmd"):
        data["cmd"] = json.loads(data["cmd"])
    return EventRecord.model_validate(data)
