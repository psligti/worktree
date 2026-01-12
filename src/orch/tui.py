from __future__ import annotations

from pathlib import Path
from typing import Optional

from .cli import _build_orchestrator


def run_tui(
    repo_root: Optional[Path] = None,
    tasks_path: Optional[Path] = None,
    session: Optional[str] = None,
) -> None:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, DataTable, Footer, Header, Static

    class ConfirmScreen(ModalScreen[bool]):
        def __init__(self, prompt: str) -> None:
            super().__init__()
            self.prompt = prompt

        def compose(self) -> ComposeResult:
            yield Static(self.prompt, id="confirm-label")
            with Horizontal():
                yield Button("Yes", id="confirm-yes", variant="error")
                yield Button("No", id="confirm-no", variant="primary")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.dismiss(event.button.id == "confirm-yes")

    class ActionScreen(ModalScreen[str | None]):
        def __init__(self, story_id: str) -> None:
            super().__init__()
            self.story_id = story_id

        def compose(self) -> ComposeResult:
            yield Static(f"Story {self.story_id}", id="action-label")
            with Vertical():
                yield Button("Start", id="action-start", variant="success")
                yield Button("Attach", id="action-attach", variant="primary")
                yield Button("Pause", id="action-pause")
                yield Button("Resume", id="action-resume")
                yield Button("Done", id="action-done", variant="warning")
                yield Button("Cleanup", id="action-cleanup", variant="error")
                yield Button("Cancel", id="action-cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "action-cancel":
                self.dismiss(None)
                return
            self.dismiss(event.button.id.replace("action-", ""))

    class TaskApp(App):
        CSS = """
        Screen {
          layout: vertical;
        }
        #main {
          height: 1fr;
        }
        #summary {
          padding: 0 2;
          height: 1;
        }
        """

        BINDINGS = [
            ("q", "quit", "quit"),
            ("r", "refresh", "refresh"),
            ("n", "next", "next attention"),
            ("a", "actions", "actions"),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            with Vertical(id="main"):
                self.table = DataTable(id="table")
                yield self.table
            self.summary = Static(id="summary")
            yield self.summary
            yield Footer()

        def on_mount(self) -> None:
            self.table.add_columns("story", "epic", "title", "status", "worktree", "tmux", "agent")
            self.table.cursor_type = "row"
            self._orch = _build_orchestrator(repo_root, tasks_path, session)
            self._rows = []
            self._refresh_data()

        def _refresh_data(self) -> None:
            self._rows = self._orch.list_tasks()
            self.table.clear()
            for row in self._rows:
                self.table.add_row(
                    row.story_id,
                    row.epic_id,
                    row.title,
                    row.status,
                    "yes" if row.has_worktree else "no",
                    "yes" if row.has_tmux_window else "no",
                    row.agent_status,
                )
            if self._rows:
                self.table.move_cursor(row=0)
            summary = self._orch.status_summary()
            summary_text = " ".join(f"{key}:{value}" for key, value in summary.items())
            self.summary.update(summary_text)

        def _selected_story_id(self) -> Optional[str]:
            if not self._rows:
                return None
            row_index = self.table.cursor_row
            if row_index is None:
                return None
            return self._rows[row_index].story_id

        def action_refresh(self) -> None:
            self._refresh_data()

        def action_next(self) -> None:
            story_id = self._orch.next_waiting()
            if story_id:
                self._orch.attach(story_id, pane="codex")

        def action_actions(self) -> None:
            story_id = self._selected_story_id()
            if not story_id:
                return
            self.app.push_screen(ActionScreen(story_id), lambda action: self._handle_action(story_id, action))

        def _handle_action(self, story_id: str, action: str | None) -> None:
            if not action:
                return
            if action == "start":
                self._orch.start_story(story_id)
            elif action == "attach":
                self._orch.attach(story_id, pane="codex")
            elif action == "pause":
                self._orch.pause(story_id)
            elif action == "resume":
                self._orch.resume(story_id)
            elif action == "done":
                self._orch.done(story_id, write_back_yaml=False, cleanup_worktree=False)
            elif action == "cleanup":
                self.app.push_screen(
                    ConfirmScreen("Cleanup worktree?"),
                    lambda confirm: self._cleanup_story(story_id, confirm),
                )
            self._refresh_data()

        def _cleanup_story(self, story_id: str, confirm: bool) -> None:
            if confirm:
                self._orch.done(story_id, write_back_yaml=False, cleanup_worktree=True)
                self._refresh_data()

    TaskApp().run()
