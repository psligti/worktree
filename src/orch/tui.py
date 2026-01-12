from __future__ import annotations

from pathlib import Path
from typing import Optional

from .cli import _build_orchestrator
from .models import Story, TaskListItem


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
            button_id = event.button.id or ""
            if button_id == "action-cancel":
                self.dismiss(None)
                return
            self.dismiss(button_id.replace("action-", "") or None)

    class TaskApp(App):
        CSS = """
        Screen {
          layout: vertical;
        }
        #main {
          height: 1fr;
        }
        #table {
          border: tall $primary;
          border_title: "Stories";
          width: 2fr;
        }
        #side {
          width: 1fr;
          min-width: 36;
        }
        #overview, #criteria, #actions {
          padding: 1 2;
          border: tall $surface;
          height: 1fr;
          overflow: hidden;
        }
        #overview {
          border_title: "Overview";
        }
        #criteria {
          border_title: "Acceptance";
        }
        #actions {
          border_title: "Next Steps";
        }
        #summary {
          padding: 0 2;
          height: 3;
          border: tall $accent;
          border_title: "Summary";
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
            with Horizontal(id="main"):
                self.table = DataTable(id="table")
                yield self.table
                with Vertical(id="side"):
                    self.overview = Static(id="overview")
                    self.criteria = Static(id="criteria")
                    self.actions = Static(id="actions")
                    yield self.overview
                    yield self.criteria
                    yield self.actions
            self.summary = Static(id="summary")
            yield self.summary
            yield Footer()

        def on_mount(self) -> None:
            self.table.add_column("story", width=8)
            self.table.add_column("epic", width=8)
            self.table.add_column("title", width=32)
            self.table.add_column("status", width=12)
            self.table.add_column("worktree", width=8)
            self.table.add_column("tmux", width=6)
            self.table.add_column("agent", width=8)
            self.table.cursor_type = "row"
            self._orch = _build_orchestrator(repo_root, tasks_path, session)
            self._rows = []
            self._stories = {}
            self._refresh_data()

        def _refresh_data(self) -> None:
            tasks_doc = self._orch.task_store.load()
            self._stories = {
                story.id: story
                for epic in tasks_doc.epics
                for story in epic.stories
            }
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
                self._update_details(self._rows[0])
            else:
                self.overview.update("")
                self.criteria.update("")
                self.actions.update("")
            summary = self._orch.status_summary()
            summary_text = " ".join(f"{key}:{value}" for key, value in summary.items())
            self.summary.update(summary_text)

        def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
            row = self._selected_row()
            if row is None:
                self.overview.update("")
                self.criteria.update("")
                self.actions.update("")
                return
            self._update_details(row)

        def _update_details(self, row: TaskListItem) -> None:
            story = self._stories.get(row.story_id)
            self.overview.update("\n".join(self._format_overview(row, story)))
            self.criteria.update("\n".join(self._format_criteria(story)))
            self.actions.update("\n".join(self._format_actions(row)))

        def _selected_row(self) -> Optional[TaskListItem]:
            if not self._rows:
                return None
            row_index = self.table.cursor_row
            if row_index is None:
                return None
            return self._rows[row_index]

        def _format_overview(self, row: TaskListItem, story: Story | None) -> list[str]:
            lines = [
                f"story: {row.story_id}",
                f"epic: {row.epic_id}",
                f"title: {row.title}",
                f"status: {row.status}",
                f"worktree: {'yes' if row.has_worktree else 'no'} | tmux: {'yes' if row.has_tmux_window else 'no'}",
                f"agent: {row.agent_status}",
            ]
            if story and story.owner:
                lines.append(f"owner: {story.owner}")
            if story and story.tags:
                lines.append(f"tags: {', '.join(story.tags)}")
            return lines

        def _format_criteria(self, story: Story | None) -> list[str]:
            if not story or not story.acceptance_criteria:
                return ["(no acceptance criteria)"]
            lines = [f"- {item}" for item in story.acceptance_criteria]
            return self._trim_lines(lines, max_lines=6)

        def _format_actions(self, row: TaskListItem) -> list[str]:
            return [
                f"next: {self._next_action(row)}",
                "shortcuts: a actions | n next | r refresh",
            ]

        def _next_action(self, row: TaskListItem) -> str:
            status = row.status
            if status == "backlog":
                return "start"
            if status == "active":
                return "pause or done"
            if status == "paused":
                return "resume"
            if status == "waiting_human":
                return "attach or resume"
            if status == "blocked":
                return "resume"
            if status == "done":
                return "cleanup"
            return "review"

        def _trim_lines(self, lines: list[str], max_lines: int) -> list[str]:
            if len(lines) <= max_lines:
                return lines
            return [*lines[: max_lines - 1], "…"]

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

        def _cleanup_story(self, story_id: str, confirm: bool | None) -> None:
            if confirm:
                self._orch.done(story_id, write_back_yaml=False, cleanup_worktree=True)
                self._refresh_data()

    TaskApp().run()
