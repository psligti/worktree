from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Iterable, List, Optional


class TmuxError(RuntimeError):
    pass


@dataclass(frozen=True)
class PaneSnapshot:
    pane_id: str
    current_command: str
    active: bool
    last_lines: List[str]
    current_path: str = ""


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


def has_session(session: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


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


def list_windows(session: str) -> List[str]:
    result = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
    return [
        line.strip()
        for line in result.stdout.decode("utf-8", "replace").splitlines()
        if line.strip()
    ]


def setup_layout(
    window_id: str, path: str, layout: str, panes: list[str], commands: dict[str, str]
) -> None:
    for _ in range(max(0, len(panes) - 1)):
        _run(["tmux", "split-window", "-t", window_id, "-c", path])

    _run(["tmux", "select-layout", "-t", window_id, layout])

    pane_ids = list(_list_panes(window_id))
    for pane_id, name in zip(pane_ids, panes):
        cmd = commands.get(name)
        if cmd:
            _run(["tmux", "send-keys", "-t", pane_id, cmd, "Enter"])


def list_panes(
    target: Optional[str] = None, capture_lines: int = 6
) -> List[PaneSnapshot]:
    cmd = ["tmux", "list-panes"]
    if target:
        cmd += ["-t", target]
    cmd += [
        "-F",
        "#{pane_id}\t#{pane_current_command}\t#{pane_active}\t#{pane_current_path}",
    ]
    result = subprocess.run(
        cmd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
    panes: List[PaneSnapshot] = []
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        pane_id, _, rest = line.partition("\t")
        command, _, rest = rest.partition("\t")
        active, _, current_path = rest.partition("\t")
        last_lines = _capture_pane(pane_id, capture_lines) if capture_lines > 0 else []
        panes.append(
            PaneSnapshot(
                pane_id=pane_id.strip(),
                current_command=command.strip(),
                active=active.strip() == "1",
                last_lines=last_lines,
                current_path=current_path.strip(),
            )
        )
    return panes


def focus_window(window_id: str, session: str) -> None:
    if not os.environ.get("TMUX"):
        return
    _run(["tmux", "switch-client", "-t", session])
    _run(["tmux", "select-window", "-t", window_id])


def select_pane(pane_id: str) -> None:
    _run(["tmux", "select-pane", "-t", pane_id])


def select_window(session: str, window: str) -> None:
    _run(["tmux", "select-window", "-t", f"{session}:{window}"])


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


def _capture_pane(pane_id: str, lines: int) -> List[str]:
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.decode("utf-8", "replace").splitlines()


def _run(cmd: list[str]) -> None:
    result = subprocess.run(
        cmd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
