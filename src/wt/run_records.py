from __future__ import annotations

from typing import Optional

from .records import SCHEMA_VERSION


def build_run_record(
    *,
    run_id: str,
    task_id: str,
    command: list[str],
    exit_code: int,
    duration_ms: int,
    started_at: str,
    ended_at: str,
    artifacts_dir: Optional[str],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "command": command,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "started_at": started_at,
        "ended_at": ended_at,
        "artifacts_dir": artifacts_dir,
    }
