from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .bootstrap.runner import BootstrapError, bootstrap_worktree
from .cli import _ensure_gitignore, _ensure_repo_layout, _normalize_worktree_name
from .config.loader import config_root, load_config
from .config.models import TmuxLayoutConfig
from .domain.models import RunRecord, WorktreeRecord
from .domain.status import overall_status
from .git import adapter as git
from .ops.doctor import doctor as doctor_check
from .ops.reindex import reindex
from .persistence import repos
from .persistence.db import init_db
from .tmux.adapter import TmuxError, ensure_session, focus_window, open_window, setup_layout


@dataclass(frozen=True)
class WorktreeListRow:
    name: str
    branch: str
    status: str
    dirty: str
    sync: str
    path: str
    record: WorktreeRecord | None
    kind: str
    branch_ref: str | None



def run_tui() -> None:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, DataTable, Footer, Header, Input, Static

    class PromptScreen(ModalScreen[str | None]):
        def __init__(self, prompt: str, placeholder: str = "") -> None:
            super().__init__()
            self.prompt = prompt
            self.placeholder = placeholder

        def compose(self) -> ComposeResult:
            yield Static(self.prompt, id="prompt-label")
            yield Input(placeholder=self.placeholder, id="prompt-input")
            with Horizontal():
                yield Button("OK", id="prompt-ok", variant="success")
                yield Button("Cancel", id="prompt-cancel", variant="error")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "prompt-ok":
                value = self.query_one("#prompt-input", Input).value.strip()
                self.dismiss(value or None)
            else:
                self.dismiss(None)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            value = event.value.strip()
            self.dismiss(value or None)

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

    class WorktreeApp(App):
        CSS = """
        Screen {
          layout: vertical;
        }
        #main {
          height: 1fr;
        }
        #table {
          border: tall $primary;
          width: 2fr;
        }
        #side {
          width: 1fr;
          min-width: 36;
        }
        #details, #actions, #log {
          padding: 1 2;
          border: tall $surface;
          height: 1fr;
          overflow: hidden;
        }
        #status {
          padding: 0 2;
          height: 3;
          border: tall $accent;
        }
        """

        BINDINGS = [
            ("q", "quit", "quit"),
            ("r", "refresh", "refresh"),
            ("n", "create", "create"),
            ("a", "add_existing", "add branch"),
            ("o", "open", "open"),
            ("e", "edit_config", "edit config"),
            ("c", "copy_branch", "copy branch"),
            ("p", "copy_path", "copy path"),
            ("b", "bootstrap", "bootstrap"),
            ("s", "sync", "sync"),
            ("l", "land", "land"),
            ("x", "remove", "remove"),
            ("R", "reindex", "reindex"),
            ("d", "doctor", "doctor"),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="main"):
                self.table = DataTable(id="table")
                yield self.table
                with Vertical(id="side"):
                    self.details = Static(id="details")
                    self.actions = Static(id="actions")
                    self.log_view = Static(id="log")
                    yield self.details
                    yield self.actions
                    yield self.log_view
            self.status = Static(id="status")
            yield self.status
            yield Footer()

        def on_mount(self) -> None:
            self.table.add_column("name", width=16)
            self.table.add_column("branch", width=18)
            self.table.add_column("status", width=12)
            self.table.add_column("dirty", width=5)
            self.table.add_column("sync", width=11)
            self.table.add_column("path", width=28)
            self.table.cursor_type = "row"
            self._rows: list[WorktreeListRow] = []
            self._repo_root = git.get_repo_root()
            self._pending_init_action: str | None = None
            self._pending_branch: str | None = None
            if not self._ensure_repo_initialized(after_init="refresh"):
                return
            self._refresh_data()

        def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
            row = self._get_selected_row()
            if row is None:
                self.details.update("")
                self.actions.update("")
                return
            self.details.update("\n".join(self._format_details(row)))
            self.actions.update("\n".join(self._format_actions(row)))
            self._set_notes(self._format_notes(row))

        def action_refresh(self) -> None:
            if not self._ensure_repo_initialized(after_init="refresh"):
                return
            self._refresh_data()

        def _refresh_data(self) -> None:
            self.table.clear()
            config_ok = self._reload_config()
            try:
                records = reindex(self._repo_root, self._config)
            except git.GitError as exc:
                self._rows = []
                self._set_status(str(exc))
                return
            self._rows = self._build_rows(records)
            for row in self._rows:
                self.table.add_row(
                    row.name,
                    row.branch,
                    row.status,
                    row.dirty,
                    row.sync,
                    row.path,
                )
            if self._rows:
                self.table.move_cursor(row=0)
            else:
                self.details.update("")
                self.actions.update("")
                self._set_notes([])
            if config_ok:
                self._set_status("refreshed")

        def _build_rows(self, records: list[WorktreeRecord]) -> list[WorktreeListRow]:
            rows: list[WorktreeListRow] = []
            existing_branches = {record.branch for record in records if record.branch}
            for record in records:
                rows.append(
                    WorktreeListRow(
                        name=record.name,
                        branch=record.branch or "(detached)",
                        status=overall_status(record),
                        dirty="yes" if record.git_dirty else "no",
                        sync=record.git_sync or "-",
                        path=_short_path(record.path),
                        record=record,
                        kind="worktree",
                        branch_ref=record.branch,
                    )
                )

            for branch in git.list_local_branches(self._repo_root):
                if branch in existing_branches:
                    continue
                rows.append(
                    WorktreeListRow(
                        name=branch,
                        branch=branch,
                        status="no worktree",
                        dirty="-",
                        sync="-",
                        path="-",
                        record=None,
                        kind="branch",
                        branch_ref=branch,
                    )
                )

            return sorted(rows, key=lambda item: item.name.lower())

        def action_reindex(self) -> None:
            self.action_refresh()

        def action_create(self) -> None:
            self.app.push_screen(PromptScreen("Worktree name", "feat-x"), self._on_create)

        def action_add_existing(self) -> None:
            row = self._get_selected_row()
            if row and row.kind == "branch" and row.branch_ref:
                default_name = _normalize_worktree_name(row.branch_ref.split("/")[-1])
                self._pending_branch = row.branch_ref
                self.app.push_screen(
                    PromptScreen("Worktree name", default_name),
                    self._on_add_branch_name,
                )
                return
            self.app.push_screen(PromptScreen("Branch name", "feature/branch"), self._on_add_branch)

        def action_open(self) -> None:
            row = self._get_selected_row()
            record = self._require_worktree(row, "open")
            if record is None:
                return
            try:
                _open_tmux(self._repo_root, record, self._config)
                self._set_status(f"opened {record.name}")
            except TmuxError as exc:
                self._set_status(str(exc))

        def action_edit_config(self) -> None:
            if not self._ensure_repo_initialized(after_init="open_config"):
                return
            self._open_config_dir()

        def action_copy_branch(self) -> None:
            row = self._get_selected_row()
            if row is None:
                return
            branch = row.branch_ref
            if not branch:
                self._set_status("no branch (detached)")
                return
            if self._copy_to_clipboard(branch):
                self._set_status("copied branch")

        def action_copy_path(self) -> None:
            row = self._get_selected_row()
            record = self._require_worktree(row, "copy path")
            if record is None:
                return
            if self._copy_to_clipboard(str(record.path)):
                self._set_status("copied path")

        def action_bootstrap(self) -> None:
            row = self._get_selected_row()
            record = self._require_worktree(row, "bootstrap")
            if record is None:
                return
            try:
                repos.update_worktree_state(self._repo_root, record.id, bootstrap="BOOTSTRAPPING")
                bootstrap_worktree(self._repo_root, record, self._config)
                repos.update_worktree_state(self._repo_root, record.id, bootstrap="BOOTSTRAPPED")
                self._set_status(f"bootstrapped {record.name}")
            except BootstrapError as exc:
                repos.update_worktree_state(self._repo_root, record.id, bootstrap="BOOTSTRAP_ERROR", last_error=str(exc))
                self._set_status(str(exc))

        def action_remove(self) -> None:
            row = self._get_selected_row()
            record = self._require_worktree(row, "remove")
            if record is None:
                return
            self.app.push_screen(ConfirmScreen(f"Remove {record.name}?"), lambda ok: self._on_remove(record, ok))

        def action_sync(self) -> None:
            row = self._get_selected_row()
            record = self._require_worktree(row, "sync")
            if record is None:
                return
            try:
                git.rebase_onto(str(record.path), f"origin/{self._config.worktrees.default_base}")
                self._set_status(f"synced {record.name}")
                self.action_refresh()
            except git.GitError as exc:
                self._set_status(str(exc))

        def action_land(self) -> None:
            row = self._get_selected_row()
            record = self._require_worktree(row, "land")
            if record is None:
                return
            try:
                branch = record.branch or f"wt/{record.name}"
                git.checkout(self._repo_root, self._config.worktrees.default_base)
                git.merge_from(self._repo_root, branch)
                self._set_status(f"landed {record.name}")
            except git.GitError as exc:
                self._set_status(str(exc))

        def action_doctor(self) -> None:
            issues = doctor_check(self._repo_root, self._config)
            if not issues:
                self._set_notes(["No issues found."])
                self._set_status("doctor report")
                return
            self._set_notes(issues)
            self._set_status("doctor report")

        def _on_create(self, value: str | None) -> None:
            if not value:
                return
            name = _normalize_worktree_name(value)
            if not name:
                self._set_status("invalid worktree name")
                return
            try:
                git.add_worktree(
                    self._repo_root,
                    str(Path(self._repo_root) / self._config.worktrees.root / name),
                    f"wt/{name}",
                    self._config.worktrees.default_base,
                    detached=False,
                )
                self.action_refresh()
                self._set_status(f"created {name}")
            except git.GitError as exc:
                self._set_status(str(exc))

        def _on_add_branch(self, value: str | None) -> None:
            if not value:
                return
            branch = value.strip()
            default_name = _normalize_worktree_name(branch.split("/")[-1])
            if not default_name:
                self._set_status("invalid branch name")
                return
            self._pending_branch = branch
            self.app.push_screen(
                PromptScreen("Worktree name", default_name),
                self._on_add_branch_name,
            )

        def _on_add_branch_name(self, value: str | None) -> None:
            if not value:
                return
            branch = self._pending_branch or ""
            self._pending_branch = None
            name = _normalize_worktree_name(value)
            if not name:
                self._set_status("invalid worktree name")
                return
            try:
                git.add_existing_worktree(
                    self._repo_root,
                    str(Path(self._repo_root) / self._config.worktrees.root / name),
                    branch,
                )
                self.action_refresh()
                self._set_status(f"added {name} from {branch}")
            except git.GitError as exc:
                self._set_status(str(exc))

        def _on_remove(self, row: WorktreeRecord, ok: bool | None) -> None:
            if not ok:
                return
            try:
                git.remove_worktree(self._repo_root, str(row.path), force=False)
                self.action_refresh()
                self._set_status(f"removed {row.name}")
            except git.GitError as exc:
                self._set_status(str(exc))

        def _get_selected_row(self) -> Optional[WorktreeListRow]:
            if not self._rows:
                return None
            row_index = self.table.cursor_row
            if row_index is None:
                return None
            if row_index >= len(self._rows):
                return None
            return self._rows[row_index]

        def _require_worktree(self, row: WorktreeListRow | None, action: str) -> WorktreeRecord | None:
            if row is None:
                return None
            if row.record is None:
                self._set_status(f"{action} requires a worktree; press a to add")
                return None
            return row.record

        def _set_status(self, message: str) -> None:
            self.status.update(message)

        def _set_notes(self, lines: list[str]) -> None:
            if not lines:
                self.log_view.update("Select a worktree to see notes.")
                return
            max_lines = 6
            trimmed = lines[:max_lines]
            if len(lines) > max_lines:
                trimmed.append("…")
            self.log_view.update("\n".join(trimmed))

        def _format_details(self, row: WorktreeListRow) -> list[str]:
            if row.record is None:
                return [
                    f"branch: {row.branch}",
                    "status: no worktree",
                    "next: add worktree (a)",
                ]
            record = row.record
            purpose = record.purpose or record.name.replace("-", " ")
            status = overall_status(record)
            branch = record.branch or "(detached)"
            last_used = _format_datetime(record.last_accessed_at)
            lock_info = self._lock_info(record)
            lines = [
                f"name: {record.name}",
                f"purpose: {purpose}",
                f"branch: {branch}",
                f"status: {status}",
                f"sync: {record.git_sync or '-'} | dirty: {'yes' if record.git_dirty else 'no'}",
                f"lock: {lock_info}",
                f"bootstrap: {record.bootstrap} | runtime: {record.runtime}",
                f"agent: {record.agent}",
                f"last used: {last_used}",
                f"path: {record.path}",
            ]
            return lines

        def _format_actions(self, row: WorktreeListRow) -> list[str]:
            if row.record is None:
                return [
                    "next: add worktree (a)",
                    "shortcuts: a add | c copy branch",
                ]
            next_step = _next_action(row.record)
            return [
                f"next: {next_step}",
                "shortcuts: o open | b bootstrap | s sync",
                "          l land | x remove | d doctor",
                "          c copy branch | p copy path",
            ]

        def _format_notes(self, row: WorktreeListRow) -> list[str]:
            if row.record is None:
                return ["Branch only; no worktree yet.", "Press a to add."]
            record = row.record
            lines: list[str] = []
            run = self._latest_run(record)
            if run:
                exit_code = "-" if run.exit_code is None else str(run.exit_code)
                command = _short_text(run.cmd, 36)
                lines.append(f"run: {run.status or '-'} exit {exit_code} {command}")
            events = repos.list_events(self._repo_root, record.id, limit=6)
            for event in events:
                at = _format_datetime(event.at)
                line = f"{at} {event.type}"
                if event.message:
                    line = f"{line} — {event.message}"
                lines.append(line)
            if not lines:
                if record.last_error:
                    return [f"last error: {record.last_error}"]
                return ["No recent events."]
            return lines

        def _latest_run(self, record: WorktreeRecord) -> Optional[RunRecord]:
            runs = repos.list_runs(self._repo_root, record.id, limit=1)
            return runs[0] if runs else None

        def _lock_info(self, record: WorktreeRecord) -> str:
            locks = repos.list_locks(self._repo_root)
            for lock in locks:
                if lock.worktree_id == record.id:
                    return lock.owner or "locked"
            return "none"

        def _copy_to_clipboard(self, text: str) -> bool:
            candidates = [
                ["pbcopy"],
                ["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]
            for cmd in candidates:
                if not shutil.which(cmd[0]):
                    continue
                result = subprocess.run(
                    cmd,
                    input=text.encode("utf-8"),
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if result.returncode == 0:
                    return True
                stderr = result.stderr.decode("utf-8", "replace").strip()
                self._set_status(stderr or "clipboard command failed")
                return False
            self._set_status("no clipboard tool found")
            return False

        def _ensure_repo_initialized(self, after_init: str | None = None) -> bool:
            config_path = Path(config_root(self._repo_root)) / "wt.toml"
            if config_path.exists():
                try:
                    _ensure_repo_layout(self._repo_root)
                    _ensure_gitignore(self._repo_root)
                    init_db(self._repo_root)
                except OSError as exc:
                    self._set_status(str(exc))
                    return False
                return True
            self._pending_init_action = after_init
            self.app.push_screen(
                PromptScreen("Coding agent command (codex/gemini/copilot)", "codex"),
                self._on_init_agent_command,
            )
            return False

        def _on_init_agent_command(self, value: str | None) -> None:
            if value is None:
                self._set_status("init canceled")
                self._pending_init_action = None
                return
            agent_cmd = (value or "codex").strip()
            if not agent_cmd:
                agent_cmd = "codex"
            self._initialize_repo(agent_cmd)
            action = self._pending_init_action
            self._pending_init_action = None
            if action == "open_config":
                self._open_config_dir()
            elif action == "refresh":
                self._refresh_data()

        def _initialize_repo(self, agent_cmd: str) -> None:
            config_path = Path(config_root(self._repo_root)) / "wt.toml"
            if not config_path.exists():
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(self._build_wizard_config(agent_cmd), encoding="utf-8")
            try:
                _ensure_repo_layout(self._repo_root)
                _ensure_gitignore(self._repo_root)
                init_db(self._repo_root)
            except OSError as exc:
                self._set_status(str(exc))
                return
            self._set_status("initialized .wt config")

        def _open_config_dir(self) -> None:
            config_dir = Path(config_root(self._repo_root))
            if not config_dir.exists():
                self._set_status("config directory not found")
                return
            if not self._reload_config():
                return
            if not self._config.open.editor_cmd:
                self._set_status("open.editor_cmd is not set")
                return
            try:
                subprocess.Popen([*self._config.open.editor_cmd, str(config_dir)], cwd=self._repo_root)
                self._set_status("opened config in editor")
            except OSError as exc:
                self._set_status(str(exc))

        def _build_wizard_config(self, agent_cmd: str) -> str:
            agent_cmd = agent_cmd.replace("\\", "\\\\").replace('"', '\\"')
            return f"""
[worktrees]
root = ".worktrees"
default_base = "main"

[env]
kind = "uv"
venv_dir = ".venv"
dotenv_file = ".env"
direnv_file = ".envrc"
unique_ports = true
port_keys = ["APP_PORT", "UI_PORT"]

[agent]
enabled = true
root_dir = ".agent"

[open]
editor_cmd = ["pycharm"]
prefer_tmux = true

[tmux]
session = "repo"
default_layout = "agent"

[tmux.layouts.agent]
layout = "even-horizontal"
panes = ["agent", "shell"]
commands = {{ agent = "{agent_cmd}" }}

[tmux.layouts.single]
layout = "even-horizontal"
panes = ["shell"]

[tmux.layouts.two-pane]
layout = "even-horizontal"
panes = ["shell", "api"]
commands = {{ api = "uv run api:dev" }}

[tmux.layouts.three-pane]
layout = "main-vertical"
panes = ["shell", "api", "ui"]
commands = {{ api = "uv run api:dev", ui = "uv run ui:dev" }}

[safety]
refuse_remove_if_dirty = true
refuse_remove_if_unpushed = true
""".strip() + "\n"

        def _reload_config(self) -> bool:
            try:
                config = load_config(self._repo_root, None)
                _ensure_default_layouts(config)
            except Exception as exc:
                self._set_status(str(exc))
                return False
            self._config = config
            return True

    WorktreeApp().run()


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _short_path(path: Path, max_len: int = 28) -> str:
    text = str(path)
    if len(text) <= max_len:
        return text
    head_len = max_len - 9
    return f"{text[:head_len]}…{text[-8:]}"


def _short_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}…"


def _next_action(row: WorktreeRecord) -> str:
    status = overall_status(row)

    if status == "UNBOOTSTRAPPED":
        return "bootstrap (b)"
    if status in {"BEHIND_MAIN", "DIVERGED"}:
        return "sync (s)"
    if status == "READY":
        return "open (o)"
    return "review"


def _open_tmux(repo_root: str, row: WorktreeRecord, config) -> None:
    session = config.tmux.session
    if session == "repo":
        session = Path(repo_root).name
    layout_name = config.tmux.default_layout
    layout_config = config.tmux.layouts.get(layout_name)
    if not layout_config:
        layout_config = list(config.tmux.layouts.values())[0]
    ensure_session(session)
    window_id = open_window(session, row.name, str(row.path))
    setup_layout(window_id, str(row.path), layout_config.layout, layout_config.panes, layout_config.commands)
    focus_window(window_id, session)


def _ensure_default_layouts(config) -> None:
    if config.tmux.layouts:
        return
    config.tmux.layouts = {
        "single": TmuxLayoutConfig(layout="even-horizontal", panes=["shell"], commands={}),
        "two-pane": TmuxLayoutConfig(
            layout="even-horizontal",
            panes=["shell", "api"],
            commands={"api": "uv run api:dev"},
        ),
        "three-pane": TmuxLayoutConfig(
            layout="main-vertical",
            panes=["shell", "api", "ui"],
            commands={"api": "uv run api:dev", "ui": "uv run ui:dev"},
        ),
    }
