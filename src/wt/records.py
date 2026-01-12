from __future__ import annotations

import os

from .models import GitWorktree

SCHEMA_VERSION = "1.0"


def infer_task_id_from_path(path: str, root_dir: str = ".worktrees") -> str:
    parts = path.split(os.sep)
    if root_dir not in parts:
        return ""

    basename = os.path.basename(path)
    if "-" not in basename:
        return ""

    return basename.split("-", 1)[0]


def worktree_record_from_git(item: GitWorktree, task_id: str | None = None) -> dict[str, object]:
    resolved_task_id = task_id or infer_task_id_from_path(item.path)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": resolved_task_id,
        "path": item.path,
        "branch": None if item.detached else item.branch,
        "head_sha": item.head_sha,
        "locked": item.locked,
        "lock_reason": item.lock_reason,
        "prunable": item.prunable,
        "prunable_reason": item.prunable_reason,
    }
