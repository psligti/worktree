from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Iterable, Optional

from .models import GitWorktree


class GitWorktreeError(RuntimeError):
    pass


def run_git_worktree_list_porcelain_z(cwd: Optional[str] = None) -> bytes:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain", "-z"],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitWorktreeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def parse_worktree_porcelain_z(data: bytes) -> list[GitWorktree]:
    records: list[GitWorktree] = []
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


def _finalize_record(data: dict[str, object]) -> GitWorktree:
    return GitWorktree(
        path=str(data.get("path", "")),
        head_sha=str(data.get("head_sha", "")),
        branch=data.get("branch") if not data.get("detached") else None,
        detached=bool(data.get("detached")),
        locked=bool(data.get("locked")),
        lock_reason=data.get("lock_reason"),
        prunable=data.get("prunable"),
        prunable_reason=data.get("prunable_reason"),
    )


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
