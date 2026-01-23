from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import connect
from ..domain.models import (
    ContainerRecord,
    EventRecord,
    LockRecord,
    PullRequestRecord,
    RunRecord,
    ServiceRecord,
    WorktreeRecord,
)


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
        ON CONFLICT(id) DO UPDATE SET
            id = excluded.id,
            name = excluded.name,
            path = excluded.path,
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
            created_at = excluded.created_at,
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


def list_locks(repo_root: str) -> list[LockRecord]:
    with connect(repo_root) as conn:
        rows = conn.execute("SELECT * FROM locks ORDER BY locked_at DESC").fetchall()
    return [_lock_from_row(row) for row in rows]


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


def record_run_finish(
    repo_root: str, run_id: str, exit_code: int, output_path: str | None
) -> None:
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


def list_runs(repo_root: str, worktree_id: str, limit: int = 10) -> list[RunRecord]:
    with connect(repo_root) as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE worktree_id = ? ORDER BY started_at DESC LIMIT ?",
            (worktree_id, limit),
        ).fetchall()
    return [_run_from_row(row) for row in rows]


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


def _run_from_row(row) -> RunRecord:
    if row is None:
        raise ValueError("missing run row")
    data = dict(row)
    return RunRecord.model_validate(data)


def _lock_from_row(row) -> LockRecord:
    if row is None:
        raise ValueError("missing lock row")
    data = dict(row)
    return LockRecord.model_validate(data)


def upsert_service(repo_root: str, record: ServiceRecord) -> None:
    data = record.model_dump(mode="json")
    with connect(repo_root) as conn:
        conn.execute(
            """
            INSERT INTO services (
                id, worktree_id, name, pane_id, status, pid,
                started_at, stopped_at, last_health_check, health_status
            ) VALUES (
                :id, :worktree_id, :name, :pane_id, :status, :pid,
                :started_at, :stopped_at, :last_health_check, :health_status
            )
            ON CONFLICT(worktree_id, name) DO UPDATE SET
                pane_id = excluded.pane_id,
                status = excluded.status,
                pid = excluded.pid,
                started_at = excluded.started_at,
                stopped_at = excluded.stopped_at,
                last_health_check = excluded.last_health_check,
                health_status = excluded.health_status
            """,
            data,
        )


def get_service(repo_root: str, worktree_id: str, name: str) -> Optional[ServiceRecord]:
    with connect(repo_root) as conn:
        row = conn.execute(
            "SELECT * FROM services WHERE worktree_id = ? AND name = ?",
            (worktree_id, name),
        ).fetchone()
    return _service_from_row(row) if row else None


def list_services(repo_root: str, worktree_id: str) -> list[ServiceRecord]:
    with connect(repo_root) as conn:
        rows = conn.execute(
            "SELECT * FROM services WHERE worktree_id = ? ORDER BY name",
            (worktree_id,),
        ).fetchall()
    return [_service_from_row(row) for row in rows]


def update_service_status(
    repo_root: str,
    worktree_id: str,
    name: str,
    status: str,
    pane_id: Optional[str] = None,
    pid: Optional[int] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect(repo_root) as conn:
        if status == "running":
            conn.execute(
                """
                UPDATE services
                SET status = ?, pane_id = ?, pid = ?, started_at = ?, stopped_at = NULL
                WHERE worktree_id = ? AND name = ?
                """,
                (status, pane_id, pid, now, worktree_id, name),
            )
        elif status == "stopped":
            conn.execute(
                """
                UPDATE services
                SET status = ?, stopped_at = ?, pid = NULL
                WHERE worktree_id = ? AND name = ?
                """,
                (status, now, worktree_id, name),
            )
        else:
            conn.execute(
                """
                UPDATE services
                SET status = ?
                WHERE worktree_id = ? AND name = ?
                """,
                (status, worktree_id, name),
            )


def update_service_health(
    repo_root: str, worktree_id: str, name: str, health_status: str
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect(repo_root) as conn:
        conn.execute(
            """
            UPDATE services
            SET health_status = ?, last_health_check = ?
            WHERE worktree_id = ? AND name = ?
            """,
            (health_status, now, worktree_id, name),
        )


def delete_service(repo_root: str, worktree_id: str, name: str) -> None:
    with connect(repo_root) as conn:
        conn.execute(
            "DELETE FROM services WHERE worktree_id = ? AND name = ?",
            (worktree_id, name),
        )


def _service_from_row(row) -> ServiceRecord:
    if row is None:
        raise ValueError("missing service row")
    data = dict(row)
    return ServiceRecord.model_validate(data)


def upsert_pull_request(repo_root: str, record: PullRequestRecord) -> None:
    data = record.model_dump(mode="json")
    data["draft"] = 1 if record.draft else 0
    data["mergeable"] = (
        1 if record.mergeable else (0 if record.mergeable is False else None)
    )
    with connect(repo_root) as conn:
        conn.execute(
            """
            INSERT INTO pull_requests (
                id, worktree_id, number, title, state, url,
                head_branch, base_branch, draft, mergeable,
                created_at, updated_at, merged_at, closed_at
            ) VALUES (
                :id, :worktree_id, :number, :title, :state, :url,
                :head_branch, :base_branch, :draft, :mergeable,
                :created_at, :updated_at, :merged_at, :closed_at
            )
            ON CONFLICT(worktree_id, number) DO UPDATE SET
                title = excluded.title,
                state = excluded.state,
                url = excluded.url,
                head_branch = excluded.head_branch,
                base_branch = excluded.base_branch,
                draft = excluded.draft,
                mergeable = excluded.mergeable,
                updated_at = excluded.updated_at,
                merged_at = excluded.merged_at,
                closed_at = excluded.closed_at
            """,
            data,
        )


def get_pull_request(
    repo_root: str, worktree_id: str, number: int
) -> Optional[PullRequestRecord]:
    with connect(repo_root) as conn:
        row = conn.execute(
            "SELECT * FROM pull_requests WHERE worktree_id = ? AND number = ?",
            (worktree_id, number),
        ).fetchone()
    return _pull_request_from_row(row) if row else None


def get_pull_request_for_worktree(
    repo_root: str, worktree_id: str
) -> Optional[PullRequestRecord]:
    with connect(repo_root) as conn:
        row = conn.execute(
            "SELECT * FROM pull_requests WHERE worktree_id = ? ORDER BY updated_at DESC LIMIT 1",
            (worktree_id,),
        ).fetchone()
    return _pull_request_from_row(row) if row else None


def list_pull_requests(
    repo_root: str, worktree_id: Optional[str] = None, limit: int = 20
) -> list[PullRequestRecord]:
    with connect(repo_root) as conn:
        if worktree_id:
            rows = conn.execute(
                "SELECT * FROM pull_requests WHERE worktree_id = ? ORDER BY updated_at DESC LIMIT ?",
                (worktree_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pull_requests ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_pull_request_from_row(row) for row in rows]


def update_pull_request_state(
    repo_root: str,
    worktree_id: str,
    number: int,
    state: str,
    merged_at: Optional[str] = None,
    closed_at: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect(repo_root) as conn:
        conn.execute(
            """
            UPDATE pull_requests
            SET state = ?, updated_at = ?, merged_at = ?, closed_at = ?
            WHERE worktree_id = ? AND number = ?
            """,
            (state, now, merged_at, closed_at, worktree_id, number),
        )


def delete_pull_request(repo_root: str, worktree_id: str, number: int) -> None:
    with connect(repo_root) as conn:
        conn.execute(
            "DELETE FROM pull_requests WHERE worktree_id = ? AND number = ?",
            (worktree_id, number),
        )


def _pull_request_from_row(row) -> PullRequestRecord:
    if row is None:
        raise ValueError("missing pull_request row")
    data = dict(row)
    data["draft"] = bool(data.get("draft"))
    mergeable_raw = data.get("mergeable")
    if mergeable_raw is None:
        data["mergeable"] = None
    else:
        data["mergeable"] = bool(mergeable_raw)
    return PullRequestRecord.model_validate(data)


def upsert_container(repo_root: str, record: ContainerRecord) -> None:
    data = record.model_dump(mode="json")
    with connect(repo_root) as conn:
        conn.execute(
            """
            INSERT INTO containers (
                id, worktree_id, name, container_id, container_name,
                image, status, started_at, stopped_at, ports
            ) VALUES (
                :id, :worktree_id, :name, :container_id, :container_name,
                :image, :status, :started_at, :stopped_at, :ports
            )
            ON CONFLICT(worktree_id, name) DO UPDATE SET
                container_id = excluded.container_id,
                container_name = excluded.container_name,
                image = excluded.image,
                status = excluded.status,
                started_at = excluded.started_at,
                stopped_at = excluded.stopped_at,
                ports = excluded.ports
            """,
            data,
        )


def get_container(
    repo_root: str, worktree_id: str, name: str
) -> Optional[ContainerRecord]:
    with connect(repo_root) as conn:
        row = conn.execute(
            "SELECT * FROM containers WHERE worktree_id = ? AND name = ?",
            (worktree_id, name),
        ).fetchone()
    return _container_from_row(row) if row else None


def list_containers(repo_root: str, worktree_id: str) -> list[ContainerRecord]:
    with connect(repo_root) as conn:
        rows = conn.execute(
            "SELECT * FROM containers WHERE worktree_id = ? ORDER BY name",
            (worktree_id,),
        ).fetchall()
    return [_container_from_row(row) for row in rows]


def update_container_status(
    repo_root: str,
    worktree_id: str,
    name: str,
    status: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect(repo_root) as conn:
        if status == "running":
            conn.execute(
                """
                UPDATE containers
                SET status = ?, started_at = ?, stopped_at = NULL
                WHERE worktree_id = ? AND name = ?
                """,
                (status, now, worktree_id, name),
            )
        elif status in ("stopped", "exited"):
            conn.execute(
                """
                UPDATE containers
                SET status = ?, stopped_at = ?
                WHERE worktree_id = ? AND name = ?
                """,
                (status, now, worktree_id, name),
            )
        else:
            conn.execute(
                """
                UPDATE containers
                SET status = ?
                WHERE worktree_id = ? AND name = ?
                """,
                (status, worktree_id, name),
            )


def delete_container(repo_root: str, worktree_id: str, name: str) -> None:
    with connect(repo_root) as conn:
        conn.execute(
            "DELETE FROM containers WHERE worktree_id = ? AND name = ?",
            (worktree_id, name),
        )


def _container_from_row(row) -> ContainerRecord:
    if row is None:
        raise ValueError("missing container row")
    data = dict(row)
    return ContainerRecord.model_validate(data)
