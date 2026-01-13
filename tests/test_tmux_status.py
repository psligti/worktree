from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wt.tmux.adapter import PaneSnapshot
from wt.tmux.status import classify_pane, summarize_window


class TestTmuxStatus(unittest.TestCase):
    def test_shell_is_idle(self) -> None:
        pane = PaneSnapshot(
            pane_id="%1",
            current_command="zsh",
            active=True,
            last_lines=[""],
        )
        self.assertEqual(classify_pane(pane), "idle")

    def test_agent_question_detected(self) -> None:
        pane = PaneSnapshot(
            pane_id="%2",
            current_command="codex",
            active=True,
            last_lines=["Question: Which file should I update?"],
        )
        self.assertEqual(classify_pane(pane), "question")

    def test_agent_waiting_detected(self) -> None:
        pane = PaneSnapshot(
            pane_id="%3",
            current_command="gemini",
            active=True,
            last_lines=[">"],
        )
        self.assertEqual(classify_pane(pane), "waiting")

    def test_agent_busy_when_no_prompt(self) -> None:
        pane = PaneSnapshot(
            pane_id="%4",
            current_command="opencode",
            active=True,
            last_lines=["Thinking about refactor..."],
        )
        self.assertEqual(classify_pane(pane), "busy")

    def test_opencode_idle_marker_is_waiting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            worktree = Path(temp_dir)
            marker = worktree / ".opencode" / "idle"
            marker.parent.mkdir(parents=True)
            marker.write_text("idle", encoding="utf-8")
            pane = PaneSnapshot(
                pane_id="%5",
                current_command="opencode",
                active=True,
                last_lines=["Thinking about refactor..."],
                current_path=str(worktree),
            )
            self.assertEqual(classify_pane(pane), "waiting")

    def test_window_summary_prefers_question(self) -> None:
        panes = [
            PaneSnapshot(
                pane_id="%5",
                current_command="zsh",
                active=False,
                last_lines=[""],
            ),
            PaneSnapshot(
                pane_id="%6",
                current_command="codex",
                active=True,
                last_lines=["Working..."],
            ),
            PaneSnapshot(
                pane_id="%7",
                current_command="codex",
                active=False,
                last_lines=["What should we do?"],
            ),
        ]
        summary = summarize_window(panes)
        self.assertEqual(summary.status, "question")
        self.assertEqual(summary.waiting_pane_id, "%7")
