from __future__ import annotations

import json
import os
import shlex
import subprocess
import uuid
import getpass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .bootstrap.runner import BootstrapError, bootstrap_worktree
from .bootstrap.templates import apply_templates
from .config.loader import load_config
from .config.models import TmuxLayoutConfig, WtConfig
from .domain.models import EventRecord, WorktreeRecord
from .run_store import save_run_record
from .domain.status import overall_status
from .git import adapter as git
from .ops.doctor import doctor as doctor_check
from .ops.reindex import reindex
from .persistence import repos
from .persistence.db import connect, init_db
from .tmux.adapter import (
    TmuxError,
    ensure_session,
    focus_window,
    has_session,
    list_panes,
    list_windows,
    open_or_attach_window,
    select_pane,
    select_window,
    setup_layout,
)
from .tmux.status import summarize_window


app = typer.Typer(add_completion=False)
tmux_app = typer.Typer(add_completion=False)
app.add_typer(tmux_app, name="tmux")
console = Console()

DEFAULT_CONFIG_TOML = """
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

[opencode]
enabled = true
config_path = ".opencode/config.json"

[opencode.themes]
codex = []
copilot = []

[tmux]
session = "repo"
default_layout = "single"

[tmux.layouts.single]
layout = "even-horizontal"
panes = ["shell"]

[tmux.layouts.two-pane]
layout = "even-horizontal"
panes = ["shell", "api"]
commands = { api = "uv run api:dev" }

[tmux.layouts.three-pane]
layout = "main-vertical"
panes = ["shell", "api", "ui"]
commands = { api = "uv run api:dev", ui = "uv run ui:dev" }

[safety]
refuse_remove_if_dirty = true
refuse_remove_if_unpushed = true
""".strip()

DEFAULT_PROFILE_TOML = """
[hooks]
post_create = ["uv sync"]
post_switch = ["uv sync"]
run_checks = []
""".strip()

UI_PROFILE_TOML = """
[hooks]
post_create = ["uv sync", "uv run ui:install"]
post_switch = ["uv sync"]
run_checks = []

[env]
port_keys = ["APP_PORT", "UI_PORT", "VITE_PORT"]
""".strip()

AGENT_PROFILE_TOML = """
[agent]
enabled = true
root_dir = ".agent"
""".strip()

ENV_TEMPLATE = """
# Base environment variables for worktrees.
# Copy into .env and adjust per worktree.
""".strip()

CONTEXT_TEMPLATE = """
# Agent Context

Provide task context, goals, and constraints for the coding agent.
""".strip()

RUNBOOK_TEMPLATE = """
# Agent Runbook

Checklist for starting work:
- Review context.md
- Validate bootstrap status
- Run tests or smoke checks as needed
""".strip()

ENVRC_TEMPLATE = """
# direnv: load .env if present
if [ -f ".env" ]; then
  dotenv .env
fi
""".strip()

OPENCODE_TEMPLATE = """
{}
""".strip()


@app.command("init")
def init() -> None:
    """Initialize .wt config/templates and database."""
    repo_root = _repo_root()
    _ensure_repo_layout(repo_root)
    init_db(repo_root)
    _ensure_gitignore(repo_root)
    console.print("initialized .wt configuration and database")


@app.command("new")
def new(
    name: str,
    base: Optional[str] = typer.Option(None, "--base"),
    profile: Optional[str] = typer.Option(None, "--profile"),
    open_window: bool = typer.Option(False, "--open"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    purpose: Optional[str] = typer.Option(None, "--purpose"),
) -> None:
    """Create a new worktree and optionally bootstrap/open it."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)

    name = _normalize_worktree_name(name)
    if not name:
        console.print("invalid worktree name")
        raise typer.Exit(code=2)

    worktree_root = Path(repo_root) / config.worktrees.root
    worktree_root.mkdir(parents=True, exist_ok=True)
    path = worktree_root / name
    path_str = str(path)
    branch = f"wt/{name}"

    record = _seed_record(path, name, branch, config, purpose)
    with connect(repo_root) as conn:
        repos.upsert_worktree(conn, record)
    _record_event(repo_root, record.id, "CreateRequested", "ABSENT", "CREATING")

    base_to_use = base if base is not None else _infer_base_from_repo(repo_root, config)
    try:
        git.add_worktree(
            repo_root,
            path_str,
            branch,
            base_to_use,
            detached=False,
        )
        apply_templates(repo_root, path_str, config)
        _record_event(repo_root, record.id, "CreateSucceeded", "CREATING", "READY")
    except git.GitError as exc:
        _record_event(
            repo_root, record.id, "CreateFailed", "CREATING", "ERROR", message=str(exc)
        )
        current = _current_branch(repo_root)
        if current:
            try:
                git.add_worktree_no_branch(repo_root, path_str, current)
                apply_templates(repo_root, path_str, config)
                _record_event(
                    repo_root, record.id, "CreateSucceeded", "CREATING", "READY"
                )
            except Exception as exc2:
                raise typer.Exit(code=5) from exc2
        else:
            raise typer.Exit(code=5)

    records = reindex(repo_root, config)
    record = _find_record(records, name)
    _run_hooks("post_create", config.hooks.post_create, repo_root, record.path)

    if bootstrap:
        _bootstrap(repo_root, record, config)
    if open_window:
        _open(repo_root, record, config, None, editor=True)

    console.print(f"created worktree {name}")


@app.command("add")
def add_cmd(
    name: str,
    branch: str = typer.Option(..., "--branch"),
    profile: Optional[str] = typer.Option(None, "--profile"),
    open_window: bool = typer.Option(False, "--open"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    purpose: Optional[str] = typer.Option(None, "--purpose"),
) -> None:
    """Add a worktree for an existing branch."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)

    name = _normalize_worktree_name(name)
    if not name:
        console.print("invalid worktree name")
        raise typer.Exit(code=2)

    worktree_root = Path(repo_root) / config.worktrees.root
    worktree_root.mkdir(parents=True, exist_ok=True)
    path = worktree_root / name
    path_str = str(path)

    record = _seed_record(path, name, branch, config, purpose)
    with connect(repo_root) as conn:
        repos.upsert_worktree(conn, record)
    _record_event(repo_root, record.id, "CreateRequested", "ABSENT", "CREATING")

    try:
        git.add_existing_worktree(repo_root, path_str, branch)
        apply_templates(repo_root, path_str, config)
        _record_event(repo_root, record.id, "CreateSucceeded", "CREATING", "READY")
    except git.GitError as exc:
        _record_event(
            repo_root, record.id, "CreateFailed", "CREATING", "ERROR", message=str(exc)
        )
        raise typer.Exit(code=5)

    records = reindex(repo_root, config)
    record = _find_record(records, name)
    _run_hooks("post_create", config.hooks.post_create, repo_root, record.path)

    if bootstrap:
        _bootstrap(repo_root, record, config)
    if open_window:
        _open(repo_root, record, config, None, editor=True)

    console.print(f"added worktree {name} from {branch}")


@app.command("open")
def open_cmd(
    name: str,
    layout: Optional[str] = typer.Option(None, "--layout"),
    editor: bool = typer.Option(True, "--editor/--no-editor"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Open a worktree in tmux and optionally launch the editor."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)
    _run_hooks("post_switch", config.hooks.post_switch, repo_root, record.path)
    _open(repo_root, record, config, layout, editor)


@tmux_app.command("waiting-pane")
def tmux_waiting_pane_cmd(
    window: Optional[str] = typer.Option(None, "--window", help="tmux window name"),
    session: Optional[str] = typer.Option(None, "--session", help="tmux session name"),
    switch: bool = typer.Option(
        True, "--switch/--no-switch", help="select the pane in tmux"
    ),
    print_pane: bool = typer.Option(False, "--print", help="print pane id if found"),
) -> None:
    """Switch to the waiting pane in a tmux window."""
    repo_root = _repo_root()
    config = _load_config(repo_root, None)
    session_name = session or _tmux_session_name(repo_root, config)
    target = None
    if window:
        target = f"{session_name}:{window}"
    elif not os.environ.get("TMUX"):
        console.print("tmux window required when not running inside tmux")
        raise typer.Exit(code=2)
    try:
        panes = list_panes(target)
        summary = summarize_window(panes)
        pane_id = summary.waiting_pane_id
        if not pane_id:
            if print_pane:
                console.print("")
            return
        if print_pane:
            console.print(pane_id)
            if not switch:
                return
        if switch:
            select_pane(pane_id)
    except (TmuxError, OSError) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)


def _window_tmux_status(session_name: str, window: str) -> tuple[str, Optional[str]]:
    try:
        panes = list_panes(f"{session_name}:{window}")
        summary = summarize_window(panes)
        return summary.status, summary.waiting_pane_id
    except (TmuxError, OSError):
        return "error", None


@tmux_app.command("status-line")
def tmux_status_line_cmd(
    session: Optional[str] = typer.Option(None, "--session", help="tmux session name"),
) -> None:
    """Render a compact tmux status summary."""
    repo_root = _repo_root()
    config = _load_config(repo_root, None)
    session_name = session or _tmux_session_name(repo_root, config)
    if not has_session(session_name):
        console.print("wt:off")
        return
    try:
        windows = list_windows(session_name)
    except (TmuxError, OSError):
        console.print("wt:error")
        return
    counts = {"question": 0, "waiting": 0, "busy": 0, "idle": 0, "error": 0}
    for window in windows:
        status, _ = _window_tmux_status(session_name, window)
        counts[status] = counts.get(status, 0) + 1
    if counts["error"]:
        console.print("wt:error")
        return
    if counts["question"] or counts["waiting"]:
        parts = []
        if counts["question"]:
            parts.append(f"q:{counts['question']}")
        if counts["waiting"]:
            parts.append(f"w:{counts['waiting']}")
        console.print("wt " + " ".join(parts))
        return
    if counts["busy"]:
        console.print("wt:busy")
        return
    console.print("wt:idle")


@tmux_app.command("next-waiting")
def tmux_next_waiting_cmd(
    session: Optional[str] = typer.Option(None, "--session", help="tmux session name"),
    switch: bool = typer.Option(
        True, "--switch/--no-switch", help="select the pane in tmux"
    ),
    print_target: bool = typer.Option(
        False, "--print", help="print window:pane if found"
    ),
) -> None:
    """Switch to the next waiting tmux pane across windows."""
    repo_root = _repo_root()
    config = _load_config(repo_root, None)
    session_name = session or _tmux_session_name(repo_root, config)
    if not has_session(session_name):
        if print_target:
            console.print("")
        return
    try:
        windows = list_windows(session_name)
    except (TmuxError, OSError) as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)
    for window in windows:
        status, pane_id = _window_tmux_status(session_name, window)
        if status in {"question", "waiting"} and pane_id:
            if print_target:
                console.print(f"{window}:{pane_id}")
                if not switch:
                    return
            if switch:
                select_window(session_name, window)
                select_pane(pane_id)
            return
    if print_target:
        console.print("")


@app.command("purpose")
def purpose_cmd(
    name: str,
    purpose: Optional[str] = typer.Argument(None),
    clear: bool = typer.Option(False, "--clear"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Set or view worktree purpose metadata."""
    if purpose and clear:
        console.print("provide a purpose or use --clear")
        raise typer.Exit(code=2)

    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if purpose is None and not clear:
        current = record.purpose or "(not set)"
        console.print(f"{name}: {current}")
        return

    value = None if clear else purpose
    repos.update_worktree_state(repo_root, record.id, purpose=value)
    console.print(f"updated purpose for {name}")


@app.command("runs")
def runs_cmd(
    name: str,
    limit: int = typer.Option(10, "--limit"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """List recent runs for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    runs = repos.list_runs(repo_root, record.id, limit=limit)
    if not runs:
        console.print("no runs recorded")
        return

    table = Table(title=f"Runs for {name}")
    table.add_column("started")
    table.add_column("status")
    table.add_column("exit")
    table.add_column("cmd")
    table.add_column("output")
    for run in runs:
        started = run.started_at.isoformat(sep=" ", timespec="minutes")
        exit_code = "-" if run.exit_code is None else str(run.exit_code)
        output_path = run.output_path or "-"
        table.add_row(started, run.status or "-", exit_code, run.cmd, output_path)
    console.print(table)


@app.command("locks")
def locks_cmd() -> None:
    """List active worktree locks."""
    repo_root = _repo_root()
    init_db(repo_root)
    locks = repos.list_locks(repo_root)
    if not locks:
        console.print("no locks recorded")
        return

    table = Table(title="Worktree Locks")
    table.add_column("worktree")
    table.add_column("owner")
    table.add_column("locked_at")
    for lock in locks:
        locked_at = (
            lock.locked_at.isoformat(sep=" ", timespec="minutes")
            if lock.locked_at
            else "-"
        )
        table.add_row(lock.worktree_id, lock.owner or "-", locked_at)
    console.print(table)


@app.command("bootstrap")
def bootstrap_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Bootstrap a worktree (venv, env, templates)."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)
    _bootstrap(repo_root, record, config)


@app.command("ls")
def ls_cmd(
    profile: Optional[str] = typer.Option(None, "--profile"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List worktrees with derived status."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)

    if json_output:
        payload = [record.model_dump(mode="json") for record in records]
        console.print_json(json.dumps(payload))
        return

    table = Table(title="Worktrees")
    table.add_column("name")
    table.add_column("branch")
    table.add_column("status")
    table.add_column("dirty")
    table.add_column("sync")
    table.add_column("path")
    for record in records:
        table.add_row(
            record.name,
            record.branch or "(detached)",
            overall_status(record),
            "yes" if record.git_dirty else "no",
            record.git_sync or "-",
            str(record.path),
        )
    console.print(table)


@app.command("sync")
def sync_cmd(
    name: str,
    strategy: str = typer.Option("rebase", "--strategy"),
    from_ref: Optional[str] = typer.Option(None, "--from"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Bring main changes into a feature worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    ref = from_ref or f"origin/{config.worktrees.default_base}"
    try:
        if strategy == "merge":
            git.merge_from(str(record.path), ref)
        else:
            git.rebase_onto(str(record.path), ref)
    except git.GitError as exc:
        _record_event(repo_root, record.id, "SyncFailed", None, None, message=str(exc))
        raise typer.Exit(code=5)

    _record_event(repo_root, record.id, "SyncSucceeded", None, None)
    console.print(f"synced {name} from {ref}")


@app.command("land")
def land_cmd(
    name: str,
    strategy: str = typer.Option("merge", "--strategy"),
    run_checks: bool = typer.Option(False, "--run-checks"),
    cleanup: bool = typer.Option(False, "--cleanup"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Merge a worktree branch back to main (local merge-first)."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if config.safety.refuse_remove_if_dirty and record.git_dirty:
        console.print(f"refusing to land {name}: dirty worktree")
        raise typer.Exit(code=4)

    if run_checks:
        _run_hooks("run_checks", config.hooks.run_checks, repo_root, record.path)

    base_ref = config.worktrees.default_base
    branch = record.branch or f"wt/{name}"

    try:
        git.checkout(repo_root, base_ref)
        if strategy == "merge":
            git.merge_from(repo_root, branch)
        else:
            git.rebase_onto(repo_root, branch)
    except git.GitError as exc:
        _record_event(repo_root, record.id, "LandFailed", None, None, message=str(exc))
        raise typer.Exit(code=5)

    _record_event(repo_root, record.id, "LandSucceeded", None, None)
    console.print(f"landed {name} into {base_ref}")

    if cleanup:
        _run_hooks("pre_remove", config.hooks.pre_remove, repo_root, record.path)
        try:
            git.remove_worktree(repo_root, str(record.path), force=False)
        except git.GitError as exc:
            console.print(f"cleanup failed: {exc}")
            raise typer.Exit(code=5)


@app.command("lock")
def lock_cmd(
    name: str,
    reason: Optional[str] = typer.Option(None, "--reason"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Lock a worktree to prevent cleanup."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    try:
        git.lock_worktree(repo_root, str(record.path), reason=reason)
        repos.upsert_lock(repo_root, record.id, owner=_lock_owner(reason))
    except git.GitError as exc:
        _record_event(repo_root, record.id, "LockFailed", None, None, message=str(exc))
        raise typer.Exit(code=5)

    _record_event(repo_root, record.id, "LockSucceeded", None, None)
    console.print(f"locked {name}")


@app.command("unlock")
def unlock_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Unlock a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    try:
        git.unlock_worktree(repo_root, str(record.path))
        repos.clear_lock(repo_root, record.id)
    except git.GitError as exc:
        _record_event(
            repo_root, record.id, "UnlockFailed", None, None, message=str(exc)
        )
        raise typer.Exit(code=5)

    _record_event(repo_root, record.id, "UnlockSucceeded", None, None)
    console.print(f"unlocked {name}")


@app.command("run")
def run_cmd(
    name: str,
    command: list[str] = typer.Argument(
        ..., help="Command to run (use -- to separate)."
    ),
    lock_on_run: bool = typer.Option(False, "--lock-on-run"),
    artifacts: Optional[Path] = typer.Option(None, "--artifacts"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Run a command inside the worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    started_at = datetime.now(timezone.utc)
    run_id = repos.record_run_start(repo_root, record.id, shlex.join(command))

    if lock_on_run:
        git.lock_worktree(repo_root, str(record.path), reason="locked during run")
        repos.upsert_lock(repo_root, record.id, owner=_lock_owner("run"))

    try:
        result = subprocess.run(
            command,
            cwd=str(record.path),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        if lock_on_run:
            try:
                git.unlock_worktree(repo_root, str(record.path))
                repos.clear_lock(repo_root, record.id)
            except git.GitError as exc:
                console.print(f"unlock failed: {exc}")

    output = result.stdout or ""
    output_path = None
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        log_path = artifacts / f"{name}-run-{timestamp}.log"
        log_path.write_text(output, encoding="utf-8")
        output_path = str(log_path)
        console.print(f"saved output to {log_path}")

    ended_at = datetime.now(timezone.utc)
    run_record = {
        "id": run_id,
        "worktree_id": record.id,
        "command": shlex.join(command),
        "status": "success" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "output": output,
        "output_path": output_path,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
    }
    save_run_record(repo_root, run_id, run_record)
    repos.record_run_finish(repo_root, run_id, result.returncode, output_path)

    if output:
        console.print(output.rstrip("\n"))

    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@app.command("rm")
def rm_cmd(
    name: str,
    force: bool = typer.Option(False, "--force"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Remove a worktree with safety checks."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if config.safety.refuse_remove_if_dirty and record.git_dirty and not force:
        console.print(f"refusing to remove {name}: dirty worktree")
        raise typer.Exit(code=4)

    if config.safety.refuse_remove_if_unpushed and record.ahead > 0 and not force:
        console.print(f"refusing to remove {name}: unpushed commits")
        raise typer.Exit(code=4)

    _run_hooks("pre_remove", config.hooks.pre_remove, repo_root, record.path)

    try:
        git.remove_worktree(repo_root, str(record.path), force=force)
    except git.GitError as exc:
        _record_event(
            repo_root, record.id, "RemoveFailed", None, None, message=str(exc)
        )
        raise typer.Exit(code=5)

    _record_event(repo_root, record.id, "RemoveSucceeded", None, "ABSENT")
    console.print(f"removed worktree {name}")


@app.command("reindex")
def reindex_cmd(profile: Optional[str] = typer.Option(None, "--profile")) -> None:
    """Rebuild the DB cache from git worktree list."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    console.print(f"reindexed {len(records)} worktrees")


@app.command("doctor")
def doctor_cmd(profile: Optional[str] = typer.Option(None, "--profile")) -> None:
    """Diagnose common issues."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    issues = doctor_check(repo_root, config)
    if not issues:
        console.print("no issues found")
        return
    for issue in issues:
        console.print(issue)


@app.command("api")
def api_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Launch the FastAPI server."""
    try:
        import uvicorn
    except ImportError:
        console.print("uvicorn is not installed")
        raise typer.Exit(code=1)

    uvicorn.run(
        "wt.api_server:create_app", host=host, port=port, factory=True, reload=reload
    )


@app.command("tui")
def tui_cmd() -> None:
    """Launch the Textual TUI."""
    from .tui import run_tui

    run_tui()


def _repo_root() -> str:
    try:
        return git.get_repo_root()
    except git.GitError as exc:
        console.print(str(exc))
        raise typer.Exit(code=5)


def _current_branch(repo_root: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--abbrev-ref", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        br = result.stdout.strip()
        return None if br == "HEAD" else br
    except Exception:
        return None


def _infer_base_from_repo(repo_root: str, config: WtConfig) -> str:
    current = _current_branch(repo_root)
    return current if current else config.worktrees.default_base


def _load_config(repo_root: str, profile: Optional[str]) -> WtConfig:
    try:
        config = load_config(repo_root, profile)
    except Exception as exc:  # pragma: no cover - defensive
        console.print(str(exc))
        raise typer.Exit(code=1)
    _ensure_default_layouts(config)
    return config


def _tmux_session_name(repo_root: str, config: WtConfig) -> str:
    session = config.tmux.session
    if session == "repo":
        return Path(repo_root).name
    return session


def _ensure_default_layouts(config: WtConfig) -> None:
    if config.tmux.layouts:
        return
    config.tmux.layouts = {
        "single": TmuxLayoutConfig(
            layout="even-horizontal", panes=["shell"], commands={}
        ),
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


def _seed_record(
    path: Path,
    name: str,
    branch: str,
    config: WtConfig,
    purpose: Optional[str] = None,
) -> WorktreeRecord:
    now = datetime.now(timezone.utc)
    return WorktreeRecord(
        id=_stable_id(path),
        name=name,
        path=path,
        branch=branch,
        purpose=purpose,
        base_ref=config.worktrees.default_base,
        lifecycle="CREATING",
        bootstrap="UNBOOTSTRAPPED",
        agent="DETACHED",
        runtime="STOPPED",
        created_at=now,
        updated_at=now,
    )


def _stable_id(path: Path) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(path)))


def _normalize_worktree_name(value: str) -> str:
    out: list[str] = []
    last_dash = False
    for ch in value.strip():
        if ch.isalnum():
            out.append(ch.lower())
            last_dash = False
        elif not last_dash:
            out.append("-")
            last_dash = True
    return "".join(out).strip("-")


def _record_event(
    repo_root: str,
    worktree_id: str,
    event_type: str,
    from_state: Optional[str],
    to_state: Optional[str],
    message: Optional[str] = None,
) -> None:
    event = EventRecord(
        id=str(uuid.uuid4()),
        worktree_id=worktree_id,
        at=datetime.now(timezone.utc),
        type=event_type,
        from_state=from_state,
        to_state=to_state,
        cmd=None,
        exit_code=None,
        message=message,
    )
    repos.record_event(repo_root, event)


def _find_record(records: list[WorktreeRecord], name: str) -> WorktreeRecord:
    for record in records:
        if record.name == name:
            return record
    console.print(f"worktree not found: {name}")
    raise typer.Exit(code=3)


def _bootstrap(repo_root: str, record: WorktreeRecord, config: WtConfig) -> None:
    repos.update_worktree_state(repo_root, record.id, bootstrap="BOOTSTRAPPING")
    _record_event(
        repo_root, record.id, "BootstrapRequested", record.bootstrap, "BOOTSTRAPPING"
    )
    try:
        bootstrap_worktree(repo_root, record, config)
    except BootstrapError as exc:
        repos.update_worktree_state(
            repo_root, record.id, bootstrap="BOOTSTRAP_ERROR", last_error=str(exc)
        )
        _record_event(
            repo_root,
            record.id,
            "BootstrapFailed",
            "BOOTSTRAPPING",
            "BOOTSTRAP_ERROR",
            message=str(exc),
        )
        raise typer.Exit(code=5)

    repos.update_worktree_state(repo_root, record.id, bootstrap="BOOTSTRAPPED")
    _record_event(
        repo_root, record.id, "BootstrapSucceeded", "BOOTSTRAPPING", "BOOTSTRAPPED"
    )
    console.print(f"bootstrapped {record.name}")


def _open(
    repo_root: str,
    record: WorktreeRecord,
    config: WtConfig,
    layout: Optional[str],
    editor: bool,
) -> None:
    layout_name = layout or config.tmux.default_layout
    layout_config = config.tmux.layouts.get(layout_name)
    if not layout_config:
        console.print(f"unknown layout: {layout_name}")
        raise typer.Exit(code=2)

    session = config.tmux.session
    if session == "repo":
        session = os.path.basename(repo_root)

    # Create unique window name: project/branch or project/task
    project_name = os.path.basename(repo_root)
    window_name = f"{project_name}/{record.branch or record.purpose or record.name}"

    try:
        ensure_session(session)
        window_id, is_new = open_or_attach_window(
            session, window_name, str(record.path)
        )

        # Only setup layout if this is a new window
        if is_new:
            setup_layout(
                window_id,
                str(record.path),
                layout_config.layout,
                layout_config.panes,
                layout_config.commands,
                window_name,
            )

        focus_window(window_id, session)
    except TmuxError as exc:
        console.print(str(exc))
        raise typer.Exit(code=5)

    repos.update_worktree_state(
        repo_root, record.id, last_accessed_at=datetime.now(timezone.utc).isoformat()
    )

    if editor:
        _open_editor(str(record.path), config)

    action = "attached to" if not is_new else "opened"
    console.print(
        f"{action} {record.name} in tmux session {session} (window: {window_name})"
    )


def _open_editor(path: str, config: WtConfig) -> None:
    if not config.open.editor_cmd:
        return
    subprocess.Popen([*config.open.editor_cmd, path])


def _lock_owner(reason: str | None = None) -> str:
    user = os.environ.get("USER") or getpass.getuser()
    if reason:
        return f"{user}:{reason}"
    return user


def _run_hooks(
    hook_name: str, commands: list[str], repo_root: str, worktree_path: Path
) -> None:
    _run_hook_commands(hook_name, commands, worktree_path)
    _run_hook_scripts(hook_name, repo_root, worktree_path)


def _run_hook_commands(hook_name: str, commands: list[str], cwd: Path) -> None:
    for command in commands:
        args = shlex.split(command)
        if not args:
            continue
        result = subprocess.run(
            args,
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            output = result.stdout.strip()
            message = f"{hook_name} hook failed: {command}"
            if output:
                message = f"{message}\n{output}"
            console.print(message)
            raise typer.Exit(code=1)


def _run_hook_scripts(hook_name: str, repo_root: str, cwd: Path) -> None:
    hooks_dir = Path(repo_root) / ".wt" / "config" / "hooks.d" / f"{hook_name}.d"
    if not hooks_dir.exists():
        return
    for script in sorted(hooks_dir.iterdir()):
        if script.is_dir():
            continue
        if os.access(script, os.X_OK):
            args = [str(script)]
        else:
            args = ["/bin/sh", str(script)]
        result = subprocess.run(
            args,
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            output = result.stdout.strip()
            message = f"{hook_name} hook failed: {script.name}"
            if output:
                message = f"{message}\n{output}"
            console.print(message)
            raise typer.Exit(code=1)


def _ensure_repo_layout(repo_root: str) -> None:
    root = Path(repo_root) / ".wt"
    config_dir = root / "config"
    templates_dir = root / "templates"
    profiles_dir = config_dir / "profiles"
    hooks_dir = config_dir / "hooks.d"

    (hooks_dir / "post_create.d").mkdir(parents=True, exist_ok=True)
    (hooks_dir / "post_switch.d").mkdir(parents=True, exist_ok=True)
    (hooks_dir / "pre_remove.d").mkdir(parents=True, exist_ok=True)
    (hooks_dir / "run_checks.d").mkdir(parents=True, exist_ok=True)

    (templates_dir / "env").mkdir(parents=True, exist_ok=True)
    (templates_dir / "agent").mkdir(parents=True, exist_ok=True)
    (templates_dir / "opencode").mkdir(parents=True, exist_ok=True)
    (templates_dir / "worktree").mkdir(parents=True, exist_ok=True)
    profiles_dir.mkdir(parents=True, exist_ok=True)

    _write_if_missing(config_dir / "wt.toml", DEFAULT_CONFIG_TOML)
    _write_if_missing(profiles_dir / "default.toml", DEFAULT_PROFILE_TOML)
    _write_if_missing(profiles_dir / "ui-dev.toml", UI_PROFILE_TOML)
    _write_if_missing(profiles_dir / "agent.toml", AGENT_PROFILE_TOML)

    _write_if_missing(templates_dir / "env" / ".env.base", ENV_TEMPLATE)
    _write_if_missing(templates_dir / "agent" / "context.md", CONTEXT_TEMPLATE)
    _write_if_missing(templates_dir / "agent" / "runbook.md", RUNBOOK_TEMPLATE)
    _write_if_missing(templates_dir / "opencode" / "codex.json", OPENCODE_TEMPLATE)
    _write_if_missing(templates_dir / "opencode" / "copilot.json", OPENCODE_TEMPLATE)
    _write_if_missing(templates_dir / "worktree" / ".envrc", ENVRC_TEMPLATE)


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")


def _ensure_gitignore(repo_root: str) -> None:
    gitignore = Path(repo_root) / ".gitignore"
    entries = [".wt/state/", ".wt/logs/", ".wt/cache/", ".worktrees/"]
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8").splitlines()
    else:
        existing = []

    updated = False
    for entry in entries:
        if entry not in existing:
            existing.append(entry)
            updated = True

    if updated:
        gitignore.write_text("\n".join(existing) + "\n", encoding="utf-8")
