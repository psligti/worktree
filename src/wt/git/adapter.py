from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from ..domain.models import GitSyncState


class GitError(RuntimeError):
    pass


def get_repo_root(cwd: str | None = None) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.decode("utf-8", "replace").strip())
    repo_root = result.stdout.decode("utf-8", "replace").strip()

    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if common.returncode != 0:
        return repo_root
    common_dir = common.stdout.decode("utf-8", "replace").strip()
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = Path(repo_root) / common_path
    if common_path.name == ".git":
        return str(common_path.parent)
    return repo_root


@dataclass(frozen=True)
class GitWorktreeEntry:
    path: str
    head_sha: str
    branch: Optional[str]
    detached: bool
    locked: bool
    lock_reason: Optional[str]
    prunable: Optional[bool]
    prunable_reason: Optional[str]


def list_worktrees(repo_root: str) -> list[GitWorktreeEntry]:
    output = _run_git(["worktree", "list", "--porcelain", "-z"], cwd=repo_root)
    return _parse_worktree_porcelain_z(output)


def add_worktree(
    repo_root: str,
    path: str,
    branch: str | None,
    base: str | None,
    detached: bool = False,
) -> None:
    if detached:
        _run_git(["worktree", "add", "-d", path], cwd=repo_root)
        return
    command = ["worktree", "add", "-b", branch or "wt/worktree", path]
    if base:
        command.append(base)
    _run_git(command, cwd=repo_root)


def remove_worktree(repo_root: str, path: str, force: bool = False) -> None:
    command = ["worktree", "remove"]
    if force:
        command.append("-f")
    command.append(path)
    _run_git(command, cwd=repo_root)


def merge_from(path: str, ref: str) -> None:
    _run_git(["-C", path, "merge", ref])


def rebase_onto(path: str, ref: str) -> None:
    _run_git(["-C", path, "rebase", ref])


def checkout(repo_root: str, ref: str) -> None:
    _run_git(["-C", repo_root, "checkout", ref])


def is_dirty(path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", path, "status", "--porcelain"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.decode("utf-8", "replace").strip())
    return bool(result.stdout.strip())


def get_upstream(path: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace").strip() or None


def get_ahead_behind(path: str, upstream: str) -> tuple[int, int]:
    result = subprocess.run(
        ["git", "-C", path, "rev-list", "--left-right", "--count", f"HEAD...{upstream}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.decode("utf-8", "replace").strip())
    parts = result.stdout.decode("utf-8", "replace").strip().split()
    if len(parts) != 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def resolve_main_ref(path: str, candidates: list[str]) -> Optional[str]:
    for ref in candidates:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--verify", ref],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            return ref
    return None


def get_behind_main(path: str, main_ref: str) -> int:
    result = subprocess.run(
        ["git", "-C", path, "rev-list", "--count", f"HEAD..{main_ref}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.decode("utf-8", "replace").strip())
    value = result.stdout.decode("utf-8", "replace").strip()
    return int(value) if value else 0


def compute_git_sync(upstream: Optional[str], ahead: int, behind: int, behind_main: int) -> GitSyncState | None:
    if upstream is None:
        return "NO_UPSTREAM"
    if ahead > 0 and behind > 0:
        return "DIVERGED"
    if behind > 0 or behind_main > 0:
        return "BEHIND_MAIN"
    if ahead > 0:
        return "AHEAD_MAIN"
    return "UP_TO_DATE"


def _run_git(args: list[str], cwd: Optional[str] = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def _parse_worktree_porcelain_z(data: bytes) -> list[GitWorktreeEntry]:
    records: list[GitWorktreeEntry] = []
    current: dict[str, object] | None = None

    for raw in _split_nul(data):
        token = raw.decode("utf-8", "surrogateescape")
        if token.startswith("worktree "):
            if current is not None:
                records.append(_finalize_record(current))
            current = {
                "path": token[len("worktree ") :],
                "head_sha": "",
                "branch": None,
                "detached": False,
                "locked": False,
                "lock_reason": None,
                "prunable": None,
                "prunable_reason": None,
            }
            continue

        if current is None:
            continue

        if token == "detached":
            current["detached"] = True
            continue

        key, value = _split_key_value(token)
        if key == "HEAD":
            current["head_sha"] = value or ""
        elif key == "branch":
            current["branch"] = value
        elif key == "locked":
            current["locked"] = True
            current["lock_reason"] = _git_c_unquote(value) if value else None
        elif key == "prunable":
            current["prunable"] = True
            current["prunable_reason"] = _git_c_unquote(value) if value else None

    if current is not None:
        records.append(_finalize_record(current))

    return records


def _split_nul(data: bytes) -> Iterable[bytes]:
    for part in data.split(b"\x00"):
        if part:
            yield part


def _split_key_value(token: str) -> tuple[str, Optional[str]]:
    if " " not in token:
        return token, None
    key, value = token.split(" ", 1)
    return key, value


def _finalize_record(data: dict[str, object]) -> GitWorktreeEntry:
    branch = _coerce_optional_str(data.get("branch")) if not data.get("detached") else None
    return GitWorktreeEntry(
        path=str(data.get("path", "")),
        head_sha=str(data.get("head_sha", "")),
        branch=branch,
        detached=bool(data.get("detached")),
        locked=bool(data.get("locked")),
        lock_reason=_coerce_optional_str(data.get("lock_reason")),
        prunable=_coerce_optional_bool(data.get("prunable")),
        prunable_reason=_coerce_optional_str(data.get("prunable_reason")),
    )


def _coerce_optional_str(value: object | None) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _coerce_optional_bool(value: object | None) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


def _git_c_unquote(value: str) -> str:
    if len(value) < 2 or not (value.startswith('"') and value.endswith('"')):
        return value

    out: list[str] = []
    i = 1
    end = len(value) - 1
    while i < end:
        ch = value[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue

        i += 1
        if i >= end:
            break

        esc = value[i]
        if esc == "a":
            out.append("\a")
        elif esc == "b":
            out.append("\b")
        elif esc == "t":
            out.append("\t")
        elif esc == "n":
            out.append("\n")
        elif esc == "v":
            out.append("\v")
        elif esc == "f":
            out.append("\f")
        elif esc == "r":
            out.append("\r")
        elif esc == "\\":
            out.append("\\")
        elif esc == '"':
            out.append('"')
        elif esc in "01234567":
            digits = esc
            j = i + 1
            while j < end and len(digits) < 3 and value[j] in "01234567":
                digits += value[j]
                j += 1
            out.append(chr(int(digits, 8)))
            i = j - 1
        elif esc == "x":
            if i + 2 < end and _is_hex(value[i + 1]) and _is_hex(value[i + 2]):
                out.append(chr(int(value[i + 1 : i + 3], 16)))
                i += 2
            else:
                out.append("x")
        else:
            out.append(esc)
        i += 1

    return "".join(out)


def _is_hex(ch: str) -> bool:
    return ("0" <= ch <= "9") or ("a" <= ch <= "f") or ("A" <= ch <= "F")
