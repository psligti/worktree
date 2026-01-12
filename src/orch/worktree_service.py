from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


class WorktreeError(RuntimeError):
    pass


@dataclass
class WorktreeEntry:
    path: Path
    head: str
    branch: Optional[str]
    locked: bool = False


class WorktreeService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def list_worktrees(self) -> List[WorktreeEntry]:
        cmd = ["git", "-C", str(self.repo_root), "worktree", "list", "--porcelain"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise WorktreeError(result.stderr.strip() or "failed to list worktrees")
        return _parse_worktree_porcelain(result.stdout)

    def worktree_exists(self, path: Path) -> bool:
        for entry in self.list_worktrees():
            if entry.path.resolve() == path.resolve():
                return True
        return False

    def branch_exists(self, branch: str) -> bool:
        cmd = ["git", "-C", str(self.repo_root), "show-ref", "--verify", f"refs/heads/{branch}"]
        return subprocess.run(cmd, capture_output=True, text=True, check=False).returncode == 0

    def ensure_branch(self, branch: str, base_ref: str) -> None:
        if self.branch_exists(branch):
            return
        cmd = ["git", "-C", str(self.repo_root), "branch", branch, base_ref]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise WorktreeError(result.stderr.strip() or "failed to create branch")

    def ensure_worktree(self, path: Path, branch: str, base_ref: str) -> None:
        if self.worktree_exists(path):
            return
        if self.branch_exists(branch):
            cmd = ["git", "-C", str(self.repo_root), "worktree", "add", str(path), branch]
        else:
            cmd = [
                "git",
                "-C",
                str(self.repo_root),
                "worktree",
                "add",
                "-b",
                branch,
                str(path),
                base_ref,
            ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise WorktreeError(result.stderr.strip() or "failed to create worktree")

    def is_dirty(self, worktree_path: Path) -> bool:
        cmd = ["git", "-C", str(worktree_path), "status", "--porcelain"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise WorktreeError(result.stderr.strip() or "failed to check worktree status")
        return bool(result.stdout.strip())

    def remove_worktree(self, worktree_path: Path) -> None:
        cmd = ["git", "-C", str(self.repo_root), "worktree", "remove", str(worktree_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise WorktreeError(result.stderr.strip() or "failed to remove worktree")


def _parse_worktree_porcelain(output: str) -> List[WorktreeEntry]:
    entries: List[WorktreeEntry] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            if current:
                entries.append(_entry_from_dict(current))
                current = {}
            current["worktree"] = value
        else:
            current[key] = value
    if current:
        entries.append(_entry_from_dict(current))
    return entries


def _entry_from_dict(data: dict[str, str]) -> WorktreeEntry:
    branch = data.get("branch")
    if branch:
        branch = branch.replace("refs/heads/", "")
    return WorktreeEntry(
        path=Path(data.get("worktree", ".")),
        head=data.get("HEAD", ""),
        branch=branch,
        locked="locked" in data,
    )
