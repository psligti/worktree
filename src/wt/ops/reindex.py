from __future__ import annotations

import os
import uuid
from datetime import datetime

from ..config.models import WtConfig
from ..domain.models import WorktreeRecord
from ..git.adapter import (
    compute_git_sync,
    get_ahead_behind,
    get_behind_main,
    get_upstream,
    is_dirty,
    list_worktrees,
    resolve_main_ref,
)
from ..persistence import repos
from ..persistence.db import connect


def reindex(repo_root: str, config: WtConfig) -> list[WorktreeRecord]:
    existing = {str(record.path): record for record in repos.list_worktrees(repo_root)}
    records: list[WorktreeRecord] = []
    present_paths: set[str] = set()

    entries = list_worktrees(repo_root)
    for entry in entries:
        present_paths.add(entry.path)
        prev = existing.get(entry.path)
        record = _build_record(repo_root, entry, config, prev)
        with connect(repo_root) as conn:
            repos.upsert_worktree(conn, record)
        records.append(record)

    repos.mark_missing_paths(repo_root, present_paths)
    return records


def _build_record(repo_root: str, entry, config: WtConfig, prev: WorktreeRecord | None) -> WorktreeRecord:
    name = _worktree_name(repo_root, entry.path, config)
    upstream = get_upstream(entry.path)
    ahead = 0
    behind = 0
    if upstream:
        ahead, behind = get_ahead_behind(entry.path, upstream)

    main_ref = resolve_main_ref(entry.path, [f"origin/{config.worktrees.default_base}", config.worktrees.default_base])
    behind_main = get_behind_main(entry.path, main_ref) if main_ref else 0
    git_sync = compute_git_sync(upstream, ahead, behind, behind_main)

    now = datetime.utcnow()
    return WorktreeRecord(
        id=_stable_id(entry.path),
        name=name,
        path=entry.path,
        branch=entry.branch,
        head_sha=entry.head_sha,
        base_ref=config.worktrees.default_base,
        lifecycle="READY",
        bootstrap=prev.bootstrap if prev else "UNBOOTSTRAPPED",
        agent=prev.agent if prev else "DETACHED",
        runtime=prev.runtime if prev else "STOPPED",
        git_dirty=is_dirty(entry.path),
        git_sync=git_sync,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        behind_main=behind_main,
        created_at=prev.created_at if prev else now,
        last_accessed_at=prev.last_accessed_at if prev else None,
        last_error=prev.last_error if prev else None,
        updated_at=now,
    )


def _stable_id(path: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, path))


def _worktree_name(repo_root: str, path: str, config: WtConfig) -> str:
    worktree_root = os.path.join(repo_root, config.worktrees.root)
    try:
        rel = os.path.relpath(path, worktree_root)
    except ValueError:
        return os.path.basename(path)
    if rel.startswith(".."):
        return os.path.basename(path)
    return rel.split(os.sep)[0]

