from __future__ import annotations

import os
import subprocess
from typing import Iterable


class TmuxError(RuntimeError):
    pass


def ensure_session(session: str) -> None:
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        return
    _run(["tmux", "new-session", "-d", "-s", session])


def open_window(session: str, name: str, path: str) -> str:
    result = subprocess.run(
        [
            "tmux",
            "new-window",
            "-P",
            "-F",
            "#{window_id}",
            "-t",
            session,
            "-n",
            name,
            "-c",
            path,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.decode("utf-8", "replace").strip()


def setup_layout(window_id: str, path: str, layout: str, panes: list[str], commands: dict[str, str]) -> None:
    for _ in range(max(0, len(panes) - 1)):
        _run(["tmux", "split-window", "-t", window_id, "-c", path])

    _run(["tmux", "select-layout", "-t", window_id, layout])

    pane_ids = list(_list_panes(window_id))
    for pane_id, name in zip(pane_ids, panes):
        cmd = commands.get(name)
        if cmd:
            _run(["tmux", "send-keys", "-t", pane_id, cmd, "Enter"])


def focus_window(window_id: str, session: str) -> None:
    if not os.environ.get("TMUX"):
        return
    _run(["tmux", "switch-client", "-t", session])
    _run(["tmux", "select-window", "-t", window_id])


def _list_panes(window_id: str) -> Iterable[str]:
    result = subprocess.run(
        ["tmux", "list-panes", "-t", window_id, "-F", "#{pane_id}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        if line.strip():
            yield line.strip()


def _run(cmd: list[str]) -> None:
    result = subprocess.run(
        cmd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
