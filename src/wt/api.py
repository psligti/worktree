from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Optional

from .git.adapter import get_repo_root
from .git_worktree import GitWorktreeError, parse_worktree_porcelain_z, run_git_worktree_list_porcelain_z
from .metadata import load_metadata
from .models import GitWorktree
from .persistence import repos
from .records import infer_task_id_from_path


@dataclass(frozen=True)
class WorktreeMetadata:
    task_id: str
    path: str
    branch: Optional[str]
    purpose: Optional[str]
    head_sha: str
    locked: bool
    lock_reason: Optional[str]
    prunable: Optional[bool]
    prunable_reason: Optional[str]
    dirty: bool


def list_worktrees() -> list[WorktreeMetadata]:
    raw = run_git_worktree_list_porcelain_z()
    items = parse_worktree_porcelain_z(raw)
    task_map = _load_task_map()
    purpose_map = _load_purpose_map()
    rows: list[WorktreeMetadata] = []
    for item in items:
        task_id = task_map.get(item.path) or infer_task_id_from_path(item.path)
        purpose = purpose_map.get(item.path)
        rows.append(_metadata_from_git(item, task_id, purpose))
    return rows


def get_worktree_by_task_id(task_id: str) -> WorktreeMetadata:
    rows = list_worktrees()
    for row in rows:
        if row.task_id == task_id:
            return row
    raise LookupError(f"task-id not found: {task_id}")


def _load_purpose_map() -> dict[str, str | None]:
    try:
        repo_root = get_repo_root()
    except GitWorktreeError:
        return {}
    try:
        records = repos.list_worktrees(repo_root)
    except Exception:
        return {}
    return {str(record.path): record.purpose for record in records}


def create_worktree(
    task_id: str,
    *,
    base: str | None = None,
    branch: str | None = None,
    path: str | None = None,
    detached: bool = False,
    lock: bool = False,
    lock_reason: str | None = None,
) -> WorktreeMetadata:
    slug = slugify(task_id)
    resolved_path = path or os.path.join(".worktrees", f"{task_id}-{slug}")
    resolved_branch = branch or f"wt/{task_id}/{slug}"

    if detached:
        _run_git(["worktree", "add", "-d", resolved_path])
    else:
        command = ["worktree", "add", "-b", resolved_branch, resolved_path]
        if base:
            command.append(base)
        _run_git(command)

    if lock:
        reason = lock_reason or "locked via wt api"
        _run_git(["worktree", "lock", "--reason", reason, resolved_path])

    try:
        item = _find_worktree_by_path(resolved_path)
    except LookupError as exc:
        raise GitWorktreeError(str(exc)) from exc
    return _metadata_from_git(item, task_id, None)


def lock_worktree(path: str, reason: str) -> None:
    _run_git(["worktree", "lock", "--reason", reason, path])


def unlock_worktree(path: str) -> None:
    _run_git(["worktree", "unlock", path])


def remove_worktree(path: str, force: bool = False) -> None:
    command = ["worktree", "remove"]
    if force:
        command.append("-f")
    command.append(path)
    _run_git(command)


def run_command_in_worktree(path: str, command: str) -> str:
    import subprocess

    args = shlex.split(command)
    if not args:
        raise GitWorktreeError("missing command")
    result = subprocess.run(
        args,
        cwd=path,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = result.stdout.decode("utf-8", "replace")
    return output or "(no output)"


def open_in_editor(path: str) -> None:
    import shutil
    import subprocess

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        args = shlex.split(editor)
        args.append(path)
        subprocess.Popen(args)
        return

    for candidate in ("pycharm", "subl", "code"):
        if shutil.which(candidate):
            subprocess.Popen([candidate, path])
            return

    raise GitWorktreeError("no editor found")


def get_recent_commits(path: str, count: int = 5) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "-C", path, "log", "-n", str(count), "--oneline"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return result.stderr.decode("utf-8", "replace").strip()
    return result.stdout.decode("utf-8", "replace").strip() or "(no commits)"


def get_diffstat(path: str) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "-C", path, "diff", "--stat"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return result.stderr.decode("utf-8", "replace").strip()
    return result.stdout.decode("utf-8", "replace").strip() or "(no changes)"


def slugify(value: str) -> str:
    out: list[str] = []
    last_dash = False
    for ch in value.strip():
        if ch.isalnum():
            out.append(ch.lower())
            last_dash = False
        elif not last_dash:
            out.append("-")
            last_dash = True
    slug = "".join(out).strip("-")
    return slug or "task"


def _metadata_from_git(item: GitWorktree, task_id: str, purpose: str | None) -> WorktreeMetadata:
    return WorktreeMetadata(
        task_id=task_id,
        path=item.path,
        branch=item.branch if not item.detached else None,
        purpose=purpose,
        head_sha=item.head_sha,
        locked=item.locked,
        lock_reason=item.lock_reason,
        prunable=item.prunable,
        prunable_reason=item.prunable_reason,
        dirty=_is_dirty(item.path),
    )


def _find_worktree_by_path(path: str) -> GitWorktree:
    try:
        raw = run_git_worktree_list_porcelain_z()
    except GitWorktreeError:
        raise LookupError("failed to query worktrees")
    items = parse_worktree_porcelain_z(raw)
    for item in items:
        if item.path == path:
            return item
    raise LookupError("worktree not found")


def _run_git(args: list[str]) -> None:
    import subprocess

    result = subprocess.run(
        ["git", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitWorktreeError(result.stderr.decode("utf-8", "replace").strip())


def _is_dirty(path: str) -> bool:
    import subprocess

    result = subprocess.run(
        ["git", "-C", path, "status", "--porcelain"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def _get_repo_root() -> str | None:
    import subprocess

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace").strip() or None


def _load_task_map() -> dict[str, str]:
    repo_root = _get_repo_root()
    if not repo_root:
        return {}
    data = load_metadata(repo_root)
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        return {}
    return {task_id: info.get("path", "") for task_id, info in tasks.items() if info.get("path")}
