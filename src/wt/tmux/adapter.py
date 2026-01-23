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


def find_window(session: str, name: str) -> str | None:
    """Find a window by name in a session. Returns window_id if found, None otherwise."""
    result = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_id}:#{window_name}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None

    for line in result.stdout.decode("utf-8", "replace").splitlines():
        if line.strip():
            window_id, window_name = line.strip().split(":", 1)
            if window_name == name:
                return window_id
    return None


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


def open_or_attach_window(session: str, name: str, path: str) -> tuple[str, bool]:
    """
    Open or attach to a window.
    Returns (window_id, is_new) where is_new is True if a new window was created.
    """
    existing_window_id = find_window(session, name)
    if existing_window_id:
        return existing_window_id, False

    window_id = open_window(session, name, path)
    return window_id, True


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
    window_id: str,
    path: str,
    layout: str,
    panes: list[str],
    commands: dict[str, str],
    window_name: str = "",
) -> None:
    for _ in range(max(0, len(panes) - 1)):
        _run(["tmux", "split-window", "-t", window_id, "-c", path])

    _run(["tmux", "select-layout", "-t", window_id, layout])

    pane_ids = list(_list_panes(window_id))
    for pane_id, name in zip(pane_ids, panes):
        # Set unique pane title based on window name and pane name
        pane_title = f"{window_name}:{name}" if window_name else name
        _run(["tmux", "select-pane", "-t", pane_id, "-T", pane_title])

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


def send_keys(pane_id: str, keys: str, enter: bool = True) -> None:
    cmd = ["tmux", "send-keys", "-t", pane_id, keys]
    if enter:
        cmd.append("Enter")
    _run(cmd)


def send_signal(pane_id: str, signal: str = "C-c") -> None:
    _run(["tmux", "send-keys", "-t", pane_id, signal])


def capture_pane(pane_id: str, lines: int = 100) -> List[str]:
    return _capture_pane(pane_id, lines)


def get_pane_pid(pane_id: str) -> Optional[int]:
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_pid}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    pid_str = result.stdout.decode("utf-8", "replace").strip()
    try:
        return int(pid_str)
    except ValueError:
        return None


def find_pane_by_title(window_id: str, title: str) -> Optional[str]:
    result = subprocess.run(
        ["tmux", "list-panes", "-t", window_id, "-F", "#{pane_id}\t#{pane_title}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        pane_id, _, pane_title = line.partition("\t")
        if pane_title.strip() == title or pane_title.strip().endswith(f":{title}"):
            return pane_id.strip()
    return None


def split_window(window_id: str, path: str, title: Optional[str] = None) -> str:
    result = subprocess.run(
        [
            "tmux",
            "split-window",
            "-t",
            window_id,
            "-c",
            path,
            "-P",
            "-F",
            "#{pane_id}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise TmuxError(result.stderr.decode("utf-8", "replace").strip())
    pane_id = result.stdout.decode("utf-8", "replace").strip()
    if title:
        _run(["tmux", "select-pane", "-t", pane_id, "-T", title])
    return pane_id


def kill_pane(pane_id: str) -> None:
    subprocess.run(
        ["tmux", "kill-pane", "-t", pane_id],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
