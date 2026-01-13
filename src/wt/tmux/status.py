from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .adapter import PaneSnapshot


PaneState = str

SHELL_COMMANDS = {"bash", "zsh", "sh", "fish", "tmux"}
AGENT_COMMANDS = {"codex", "gemini", "copilot", "opencode"}

QUESTION_PATTERNS = [
    re.compile(r"\?\s*$"),
    re.compile(r"\bquestion\b", re.IGNORECASE),
]

WAITING_PATTERNS = [
    re.compile(r"^>\s*$"),
    re.compile(r"^>>>\s*$"),
    re.compile(r"^(you|user|human)\s*[:>]\s*$", re.IGNORECASE),
    re.compile(r"^type your message", re.IGNORECASE),
    re.compile(r"^enter (a )?message", re.IGNORECASE),
    re.compile(r"^waiting for (input|prompt)", re.IGNORECASE),
    re.compile(r"^press enter", re.IGNORECASE),
]


@dataclass(frozen=True)
class WindowStatus:
    status: str
    waiting_pane_id: Optional[str]


def summarize_window(panes: Sequence[PaneSnapshot]) -> WindowStatus:
    if not panes:
        return WindowStatus(status="idle", waiting_pane_id=None)
    pane_states = {pane.pane_id: classify_pane(pane) for pane in panes}
    waiting_pane_id = _first_with_state(pane_states, panes, "question")
    if waiting_pane_id:
        return WindowStatus(status="question", waiting_pane_id=waiting_pane_id)
    waiting_pane_id = _first_with_state(pane_states, panes, "waiting")
    if waiting_pane_id:
        return WindowStatus(status="waiting", waiting_pane_id=waiting_pane_id)
    if "busy" in pane_states.values():
        return WindowStatus(status="busy", waiting_pane_id=None)
    return WindowStatus(status="idle", waiting_pane_id=None)


def classify_pane(pane: PaneSnapshot) -> PaneState:
    command = pane.current_command.strip()
    if not command or command in SHELL_COMMANDS:
        return "idle"
    last_line = _last_nonempty_line(pane.last_lines)
    if _matches(QUESTION_PATTERNS, last_line) and _is_prompt_command(command):
        return "question"
    if _matches(WAITING_PATTERNS, last_line) and _is_prompt_command(command):
        return "waiting"
    if _has_opencode_idle_marker(pane):
        return "waiting"
    return "busy"


def _is_prompt_command(command: str) -> bool:
    return command in AGENT_COMMANDS or command not in SHELL_COMMANDS


def _has_opencode_idle_marker(pane: PaneSnapshot) -> bool:
    if not pane.current_path:
        return False
    try:
        start = Path(pane.current_path)
    except (TypeError, ValueError):
        return False
    for path in [start, *start.parents]:
        marker = path / ".opencode" / "idle"
        if marker.exists():
            return True
    return False


def _last_nonempty_line(lines: Iterable[str]) -> str:
    for line in reversed(list(lines)):
        if line.strip():
            return line.strip()
    return ""


def _matches(patterns: Sequence[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _first_with_state(
    pane_states: dict[str, PaneState],
    panes: Sequence[PaneSnapshot],
    state: PaneState,
) -> Optional[str]:
    for pane in panes:
        if pane_states.get(pane.pane_id) == state:
            return pane.pane_id
    return None
