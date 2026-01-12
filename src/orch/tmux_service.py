from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


class TmuxError(RuntimeError):
    pass


@dataclass
class WindowInfo:
    name: str
    flags: str


@dataclass
class PaneInfo:
    pane_id: str
    title: str
    current_command: str


class TmuxService:
    def __init__(self, session: str) -> None:
        self.session = session

    def session_exists(self) -> bool:
        result = subprocess.run(
            ["tmux", "has-session", "-t", self.session],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def ensure_session(self, workdir: Path) -> None:
        if self.session_exists():
            return
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", self.session, "-c", str(workdir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "failed to create tmux session")

    def list_windows(self) -> List[WindowInfo]:
        if not self.session_exists():
            return []
        result = subprocess.run(
            ["tmux", "list-windows", "-t", self.session, "-F", "#{window_name}\t#{window_flags}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "failed to list tmux windows")
        windows = []
        for line in result.stdout.splitlines():
            name, _, flags = line.partition("\t")
            windows.append(WindowInfo(name=name, flags=flags))
        return windows

    def window_exists(self, window_name: str) -> bool:
        return any(window.name == window_name for window in self.list_windows())

    def ensure_window(self, window_name: str, workdir: Path) -> None:
        if self.window_exists(window_name):
            return
        result = subprocess.run(
            [
                "tmux",
                "new-window",
                "-t",
                self.session,
                "-n",
                window_name,
                "-c",
                str(workdir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "failed to create tmux window")

    def list_panes(self, window_name: str) -> List[PaneInfo]:
        if not self.window_exists(window_name):
            return []
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-t",
                f"{self.session}:{window_name}",
                "-F",
                "#{pane_id}\t#{pane_title}\t#{pane_current_command}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "failed to list tmux panes")
        panes = []
        for line in result.stdout.splitlines():
            pane_id, _, rest = line.partition("\t")
            title, _, command = rest.partition("\t")
            panes.append(PaneInfo(pane_id=pane_id, title=title, current_command=command))
        return panes

    def ensure_panes(self, window_name: str, pane_titles: List[str], workdir: Path, layout: str) -> Dict[str, str]:
        self.ensure_window(window_name, workdir)
        panes = self.list_panes(window_name)
        if not panes:
            panes = self.list_panes(window_name)
        while len(panes) < len(pane_titles):
            result = subprocess.run(
                [
                    "tmux",
                    "split-window",
                    "-t",
                    f"{self.session}:{window_name}",
                    "-c",
                    str(workdir),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise TmuxError(result.stderr.strip() or "failed to split tmux pane")
            panes = self.list_panes(window_name)
        panes = self.list_panes(window_name)
        for title, pane in zip(pane_titles, panes):
            subprocess.run(
                [
                    "tmux",
                    "select-pane",
                    "-t",
                    pane.pane_id,
                    "-T",
                    title,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        subprocess.run(
            ["tmux", "select-layout", "-t", f"{self.session}:{window_name}", layout],
            capture_output=True,
            text=True,
            check=False,
        )
        panes = self.list_panes(window_name)
        return {pane.title: pane.pane_id for pane in panes if pane.title}

    def focus_window(self, window_name: str, pane_title: Optional[str] = None) -> None:
        target = f"{self.session}:{window_name}"
        if pane_title:
            pane_target = self.resolve_pane(window_name, pane_title)
            if pane_target:
                target = pane_target
        subprocess.run(["tmux", "select-window", "-t", f"{self.session}:{window_name}"], check=False)
        if pane_title:
            subprocess.run(["tmux", "select-pane", "-t", target], check=False)

    def resolve_pane(self, window_name: str, pane_title: str) -> Optional[str]:
        for pane in self.list_panes(window_name):
            if pane.title == pane_title:
                return pane.pane_id
        return None

    def send_keys(self, target: str, keys: str, enter: bool = True) -> None:
        cmd = ["tmux", "send-keys", "-t", target, keys]
        if enter:
            cmd.append("Enter")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "failed to send tmux keys")

    def send_ctrl_c(self, target: str) -> None:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", target, "C-c"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise TmuxError(result.stderr.strip() or "failed to send Ctrl-C")
