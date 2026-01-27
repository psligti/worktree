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
from .domain.models import EventRecord, PullRequestRecord, WorktreeRecord
from .run_store import save_run_record
from .domain.status import overall_status
from .git import adapter as git
from .ops.doctor import doctor as doctor_check
from .ops.gc import GcCandidate, select_gc_candidates
from .ops.reindex import reindex
from .ops.skills import install_skills
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
from .services.manager import ServiceError, ServiceManager
from .github.adapter import GitHubAdapter, GitHubError
from .database.manager import DatabaseError, DatabaseManager
from .containers.manager import ContainerError, ContainerManager
from .secrets.manager import SecretsError, SecretsManager


app = typer.Typer(add_completion=False)
tmux_app = typer.Typer(add_completion=False)
svc_app = typer.Typer(add_completion=False)
pr_app = typer.Typer(add_completion=False)
db_app = typer.Typer(add_completion=False)
ctr_app = typer.Typer(add_completion=False)
secrets_app = typer.Typer(add_completion=False)
app.add_typer(tmux_app, name="tmux")
app.add_typer(svc_app, name="svc")
app.add_typer(pr_app, name="pr")
app.add_typer(db_app, name="db")
app.add_typer(ctr_app, name="ctr")
app.add_typer(secrets_app, name="secrets")
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
post_create = []
post_switch = []
run_checks = []
""".strip()

UI_PROFILE_TOML = """
[hooks]
post_create = []
post_switch = []
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


@app.command("install-skills")
def install_skills_cmd(
    global_only: bool = typer.Option(
        False, "--global", help="Install to global XDG skills directory only"
    ),
    local_only: bool = typer.Option(
        False,
        "--local-only",
        help="Install to local worktrees and templates only (skip global)",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing skill files"),
) -> None:
    """Install OpenCode skills to global and/or local targets."""
    repo_root = _repo_root()
    config = _load_config(repo_root, None)

    try:
        results = install_skills(
            repo_root=repo_root,
            config=config,
            global_only=global_only,
            local_only=local_only,
            force=force,
        )

        # Build summary message
        messages = []

        if results.get("created", 0) > 0:
            messages.append(f"Installed {results['created']} skills")
        if results.get("skipped", 0) > 0:
            messages.append(f"Skipped {results['skipped']} existing skills")
        if results.get("overwritten", 0) > 0:
            messages.append(f"Overwritten {results['overwritten']} skills")
        if results.get("errors", 0) > 0:
            messages.append(f"Encountered {results['errors']} errors")

        summary = "; ".join(messages)
        console.print(summary)

        if results.get("errors", 0) > 0:
            raise typer.Exit(code=1)

    except (OSError, IOError) as exc:
        console.print(f"Failed to install skills: {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"Unexpected error: {exc}")
        raise typer.Exit(code=1)


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


@app.command("clone")
def clone_cmd(
    source: str,
    name: str,
    branch: Optional[str] = typer.Option(None, "--branch"),
    profile: Optional[str] = typer.Option(None, "--profile"),
    open_window: bool = typer.Option(False, "--open"),
    bootstrap: bool = typer.Option(False, "--bootstrap"),
    purpose: Optional[str] = typer.Option(None, "--purpose"),
) -> None:
    """Clone a worktree from an existing one."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)

    records = reindex(repo_root, config)
    source_record = _find_record(records, source)

    name = _normalize_worktree_name(name)
    if not name:
        console.print("invalid worktree name")
        raise typer.Exit(code=2)

    worktree_root = Path(repo_root) / config.worktrees.root
    worktree_root.mkdir(parents=True, exist_ok=True)
    path = worktree_root / name
    if path.exists():
        console.print(f"worktree path already exists: {path}")
        raise typer.Exit(code=2)

    branch_name = branch or f"wt/{name}"
    base_ref = source_record.head_sha or source_record.branch
    if not base_ref:
        console.print(f"unable to clone {source}: missing head sha and branch")
        raise typer.Exit(code=5)

    record = _seed_record(
        path, name, branch_name, config, purpose or source_record.purpose
    )
    with connect(repo_root) as conn:
        repos.upsert_worktree(conn, record)
    _record_event(repo_root, record.id, "CreateRequested", "ABSENT", "CREATING")

    try:
        git.add_worktree(
            repo_root,
            str(path),
            branch_name,
            base_ref,
            detached=False,
        )
        apply_templates(repo_root, str(path), config)
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

    console.print(f"cloned worktree {name} from {source}")


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


@svc_app.command("start")
def svc_start_cmd(
    name: str,
    service: Optional[str] = typer.Option(None, "--service", "-s", help="Service name"),
    all_services: bool = typer.Option(False, "--all", "-a", help="Start all services"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Start services for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.services.definitions:
        console.print("no services defined in config")
        raise typer.Exit(code=2)

    manager = ServiceManager(repo_root, config)
    manager.ensure_service_records(record)

    service_name = None if all_services else service
    try:
        started = manager.start(record, service_name)
    except ServiceError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    if started:
        console.print(f"started: {', '.join(started)}")
    else:
        console.print("no services started (already running or none specified)")


@svc_app.command("stop")
def svc_stop_cmd(
    name: str,
    service: Optional[str] = typer.Option(None, "--service", "-s", help="Service name"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Stop services for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ServiceManager(repo_root, config)
    stopped = manager.stop(record, service)

    if stopped:
        console.print(f"stopped: {', '.join(stopped)}")
    else:
        console.print("no services stopped")


@svc_app.command("restart")
def svc_restart_cmd(
    name: str,
    service: str = typer.Option(..., "--service", "-s", help="Service name to restart"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Restart a service for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ServiceManager(repo_root, config)
    try:
        manager.restart(record, service)
    except ServiceError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"restarted: {service}")


@svc_app.command("status")
def svc_status_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Show service status for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ServiceManager(repo_root, config)
    services = manager.status(record)

    if not services:
        console.print("no services tracked")
        return

    table = Table(title=f"Services for {name}")
    table.add_column("name")
    table.add_column("status")
    table.add_column("health")
    table.add_column("pane")
    table.add_column("started")

    for svc in services:
        started = (
            svc.started_at.isoformat(sep=" ", timespec="minutes")
            if svc.started_at
            else "-"
        )
        table.add_row(
            svc.name,
            svc.status,
            svc.health_status,
            svc.pane_id or "-",
            started,
        )
    console.print(table)


@svc_app.command("logs")
def svc_logs_cmd(
    name: str,
    service: str = typer.Option(..., "--service", "-s", help="Service name"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Show logs for a service."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ServiceManager(repo_root, config)
    log_lines = manager.logs(record, service, lines)

    if not log_lines:
        console.print(f"no logs available for {service}")
        return

    for line in log_lines:
        console.print(line)


@pr_app.command("create")
def pr_create_cmd(
    name: str,
    title: Optional[str] = typer.Option(None, "--title", "-t", help="PR title"),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="PR body"),
    base: str = typer.Option("main", "--base", help="Base branch"),
    draft: bool = typer.Option(False, "--draft", "-d", help="Create as draft"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Create a pull request for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    pr_title = title or record.purpose or f"Feature: {record.name}"
    pr_body = body or ""

    gh = GitHubAdapter(str(record.path))
    try:
        pr = gh.create_pr(
            title=pr_title,
            body=pr_body,
            base=base,
            head=record.branch,
            draft=draft,
        )
    except GitHubError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    pr_record = PullRequestRecord(
        id=str(uuid.uuid4()),
        worktree_id=record.id,
        number=pr.number,
        title=pr.title,
        state=pr.state,
        url=pr.url,
        head_branch=pr.head_branch,
        base_branch=pr.base_branch,
        draft=pr.draft,
        mergeable=pr.mergeable,
    )
    repos.upsert_pull_request(repo_root, pr_record)

    console.print(f"created PR #{pr.number}: {pr.url}")


@pr_app.command("status")
def pr_status_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Show PR status for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    gh = GitHubAdapter(str(record.path))
    pr = gh.get_pr_for_branch(record.branch or f"wt/{name}")

    if not pr:
        console.print(f"no PR found for {name}")
        return

    checks = gh.pr_checks(pr.number)

    table = Table(title=f"PR #{pr.number}: {pr.title}")
    table.add_column("field")
    table.add_column("value")
    table.add_row("state", pr.state)
    table.add_row("draft", "yes" if pr.draft else "no")
    table.add_row(
        "mergeable", str(pr.mergeable) if pr.mergeable is not None else "unknown"
    )
    table.add_row("base", pr.base_branch)
    table.add_row("head", pr.head_branch)
    table.add_row("url", pr.url)
    console.print(table)

    if checks:
        check_table = Table(title="Checks")
        check_table.add_column("name")
        check_table.add_column("state")
        check_table.add_column("conclusion")
        for check in checks:
            check_table.add_row(
                check.get("name", "-"),
                check.get("state", "-"),
                check.get("conclusion", "-"),
            )
        console.print(check_table)


@pr_app.command("merge")
def pr_merge_cmd(
    name: str,
    strategy: str = typer.Option(
        "squash", "--strategy", "-s", help="merge|squash|rebase"
    ),
    delete_branch: bool = typer.Option(True, "--delete-branch/--no-delete-branch"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Merge a pull request."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    gh = GitHubAdapter(str(record.path))
    pr = gh.get_pr_for_branch(record.branch or f"wt/{name}")

    if not pr:
        console.print(f"no PR found for {name}")
        raise typer.Exit(code=1)

    if pr.state != "open":
        console.print(f"PR #{pr.number} is not open (state: {pr.state})")
        raise typer.Exit(code=1)

    if strategy not in ("merge", "squash", "rebase"):
        console.print(f"invalid strategy: {strategy}")
        raise typer.Exit(code=2)

    try:
        gh.merge_pr(pr.number, strategy=strategy, delete_branch=delete_branch)
    except GitHubError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    now = datetime.now(timezone.utc).isoformat()
    repos.update_pull_request_state(
        repo_root, record.id, pr.number, "merged", merged_at=now
    )

    console.print(f"merged PR #{pr.number}")


@pr_app.command("close")
def pr_close_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Close a pull request without merging."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    gh = GitHubAdapter(str(record.path))
    pr = gh.get_pr_for_branch(record.branch or f"wt/{name}")

    if not pr:
        console.print(f"no PR found for {name}")
        raise typer.Exit(code=1)

    try:
        gh.close_pr(pr.number)
    except GitHubError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    now = datetime.now(timezone.utc).isoformat()
    repos.update_pull_request_state(
        repo_root, record.id, pr.number, "closed", closed_at=now
    )

    console.print(f"closed PR #{pr.number}")


@pr_app.command("open")
def pr_open_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Open a pull request in the browser."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    gh = GitHubAdapter(str(record.path))
    pr = gh.get_pr_for_branch(record.branch or f"wt/{name}")

    if not pr:
        console.print(f"no PR found for {name}")
        raise typer.Exit(code=1)

    try:
        gh.open_pr_in_browser(pr.number)
    except GitHubError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"opened PR #{pr.number} in browser")


@pr_app.command("ready")
def pr_ready_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Mark a draft PR as ready for review."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    gh = GitHubAdapter(str(record.path))
    pr = gh.get_pr_for_branch(record.branch or f"wt/{name}")

    if not pr:
        console.print(f"no PR found for {name}")
        raise typer.Exit(code=1)

    if not pr.draft:
        console.print(f"PR #{pr.number} is not a draft")
        raise typer.Exit(code=1)

    try:
        gh.pr_ready(pr.number)
    except GitHubError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"marked PR #{pr.number} as ready for review")


@pr_app.command("ls")
def pr_ls_cmd(
    limit: int = typer.Option(20, "--limit", "-n"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """List tracked pull requests."""
    repo_root = _repo_root()
    init_db(repo_root)

    prs = repos.list_pull_requests(repo_root, limit=limit)

    if not prs:
        console.print("no pull requests tracked")
        return

    table = Table(title="Pull Requests")
    table.add_column("#")
    table.add_column("title")
    table.add_column("state")
    table.add_column("branch")
    table.add_column("updated")

    for pr in prs:
        updated = pr.updated_at.isoformat(sep=" ", timespec="minutes")
        table.add_row(
            str(pr.number),
            pr.title[:50] + "..." if len(pr.title) > 50 else pr.title,
            pr.state,
            pr.head_branch,
            updated,
        )
    console.print(table)


@db_app.command("create")
def db_create_cmd(
    name: str,
    db_type: str = typer.Option("sqlite", "--type", "-t", help="postgres|sqlite"),
    suffix: str = typer.Option("", "--suffix", "-s", help="Database name suffix"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Create a database for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.database.enabled:
        console.print("database isolation is not enabled in config")
        raise typer.Exit(code=2)

    if db_type not in ("postgres", "sqlite"):
        console.print(f"invalid database type: {db_type}")
        raise typer.Exit(code=2)

    manager = DatabaseManager(repo_root, config)
    try:
        db_name = manager.create_database(record, db_type, suffix)  # type: ignore[arg-type]
    except DatabaseError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"created {db_type} database: {db_name}")


@db_app.command("drop")
def db_drop_cmd(
    name: str,
    db_type: str = typer.Option("sqlite", "--type", "-t", help="postgres|sqlite"),
    suffix: str = typer.Option("", "--suffix", "-s", help="Database name suffix"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Drop a database for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if db_type not in ("postgres", "sqlite"):
        console.print(f"invalid database type: {db_type}")
        raise typer.Exit(code=2)

    manager = DatabaseManager(repo_root, config)
    try:
        manager.drop_database(record, db_type, suffix)  # type: ignore[arg-type]
    except DatabaseError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    db_name = manager.db_name_for_worktree(record, suffix)
    console.print(f"dropped {db_type} database: {db_name}")


@db_app.command("snapshot")
def db_snapshot_cmd(
    name: str,
    db_type: str = typer.Option("sqlite", "--type", "-t", help="postgres|sqlite"),
    suffix: str = typer.Option("", "--suffix", "-s", help="Database name suffix"),
    snapshot_name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Snapshot name"
    ),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Create a snapshot of a worktree database."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if db_type not in ("postgres", "sqlite"):
        console.print(f"invalid database type: {db_type}")
        raise typer.Exit(code=2)

    manager = DatabaseManager(repo_root, config)
    try:
        output_path = manager.snapshot(record, db_type, suffix, snapshot_name)  # type: ignore[arg-type]
    except DatabaseError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"created snapshot: {output_path}")


@db_app.command("restore")
def db_restore_cmd(
    name: str,
    snapshot: str = typer.Option(..., "--snapshot", help="Path to snapshot file"),
    db_type: str = typer.Option("sqlite", "--type", "-t", help="postgres|sqlite"),
    suffix: str = typer.Option("", "--suffix", "-s", help="Database name suffix"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Restore a worktree database from a snapshot."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if db_type not in ("postgres", "sqlite"):
        console.print(f"invalid database type: {db_type}")
        raise typer.Exit(code=2)

    snapshot_path = Path(snapshot)
    manager = DatabaseManager(repo_root, config)
    try:
        manager.restore(record, db_type, snapshot_path, suffix)  # type: ignore[arg-type]
    except DatabaseError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    db_name = manager.db_name_for_worktree(record, suffix)
    console.print(f"restored {db_type} database {db_name} from {snapshot_path}")


@db_app.command("clone")
def db_clone_cmd(
    source: str,
    target: str,
    db_type: str = typer.Option("sqlite", "--type", "-t", help="postgres|sqlite"),
    suffix: str = typer.Option("", "--suffix", "-s", help="Database name suffix"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Clone a database from one worktree to another."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    source_record = _find_record(records, source)
    target_record = _find_record(records, target)

    if db_type not in ("postgres", "sqlite"):
        console.print(f"invalid database type: {db_type}")
        raise typer.Exit(code=2)

    manager = DatabaseManager(repo_root, config)
    try:
        target_name = manager.clone_database(
            source_record, target_record, db_type, suffix
        )  # type: ignore[arg-type]
    except DatabaseError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"cloned {db_type} database to: {target_name}")


@db_app.command("reset")
def db_reset_cmd(
    name: str,
    db_type: str = typer.Option("sqlite", "--type", "-t", help="postgres|sqlite"),
    suffix: str = typer.Option("", "--suffix", "-s", help="Database name suffix"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Reset (drop and recreate) a worktree database."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if db_type not in ("postgres", "sqlite"):
        console.print(f"invalid database type: {db_type}")
        raise typer.Exit(code=2)

    manager = DatabaseManager(repo_root, config)
    try:
        manager.reset_database(record, db_type, suffix)  # type: ignore[arg-type]
    except DatabaseError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    db_name = manager.db_name_for_worktree(record, suffix)
    console.print(f"reset {db_type} database: {db_name}")


@db_app.command("ls")
def db_ls_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """List database snapshots for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = DatabaseManager(repo_root, config)
    snapshots = manager.list_snapshots(record)

    if not snapshots:
        console.print(f"no snapshots for {name}")
        return

    table = Table(title=f"Snapshots for {name}")
    table.add_column("name")
    table.add_column("size")
    table.add_column("modified")

    for snapshot in snapshots:
        stat = snapshot.stat()
        size = f"{stat.st_size / 1024:.1f} KB"
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(
            sep=" ", timespec="minutes"
        )
        table.add_row(snapshot.name, size, modified)
    console.print(table)


@ctr_app.command("start")
def ctr_start_cmd(
    name: str,
    service: Optional[str] = typer.Option(
        None, "--service", "-s", help="Container service name"
    ),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Start containers for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.containers.enabled:
        console.print("container support is not enabled in config")
        raise typer.Exit(code=2)

    manager = ContainerManager(repo_root, config)
    try:
        started = manager.start(record, service)
    except ContainerError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    if started:
        console.print(f"started: {', '.join(started)}")
    else:
        console.print("no containers started (already running or none specified)")


@ctr_app.command("stop")
def ctr_stop_cmd(
    name: str,
    service: Optional[str] = typer.Option(
        None, "--service", "-s", help="Container service name"
    ),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Stop containers for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ContainerManager(repo_root, config)
    try:
        stopped = manager.stop(record, service)
    except ContainerError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    if stopped:
        console.print(f"stopped: {', '.join(stopped)}")
    else:
        console.print("no containers stopped")


@ctr_app.command("rm")
def ctr_rm_cmd(
    name: str,
    service: Optional[str] = typer.Option(
        None, "--service", "-s", help="Container service name"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force remove"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Remove containers for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ContainerManager(repo_root, config)
    try:
        removed = manager.rm(record, service, force=force)
    except ContainerError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    if removed:
        console.print(f"removed: {', '.join(removed)}")
    else:
        console.print("no containers removed")


@ctr_app.command("status")
def ctr_status_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Show container status for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ContainerManager(repo_root, config)
    containers = manager.status(record)

    if not containers:
        console.print("no containers tracked")
        return

    table = Table(title=f"Containers for {name}")
    table.add_column("name")
    table.add_column("image")
    table.add_column("status")
    table.add_column("container")
    table.add_column("started")

    for ctr in containers:
        started = (
            ctr.started_at.isoformat(sep=" ", timespec="minutes")
            if ctr.started_at
            else "-"
        )
        table.add_row(
            ctr.name,
            ctr.image,
            ctr.status,
            ctr.container_name,
            started,
        )
    console.print(table)


@ctr_app.command("ps")
def ctr_ps_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """List running containers for a worktree (live docker/podman ps)."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ContainerManager(repo_root, config)
    try:
        containers = manager.ps(record)
    except Exception as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    if not containers:
        console.print("no containers found")
        return

    table = Table(title=f"Containers for {name}")
    table.add_column("id")
    table.add_column("name")
    table.add_column("image")
    table.add_column("status")
    table.add_column("ports")

    for ctr in containers:
        table.add_row(ctr.id[:12], ctr.name, ctr.image, ctr.status, ctr.ports or "-")
    console.print(table)


@ctr_app.command("logs")
def ctr_logs_cmd(
    name: str,
    service: str = typer.Option(..., "--service", "-s", help="Container service name"),
    lines: int = typer.Option(100, "--lines", "-n", help="Number of lines"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Show logs for a container."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ContainerManager(repo_root, config)
    log_lines = manager.logs(record, service, tail=lines)

    if not log_lines:
        console.print(f"no logs available for {service}")
        return

    for line in log_lines:
        console.print(line)


@ctr_app.command("exec")
def ctr_exec_cmd(
    name: str,
    service: str = typer.Option(..., "--service", "-s", help="Container service name"),
    command: list[str] = typer.Argument(..., help="Command to run"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Execute a command in a container."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ContainerManager(repo_root, config)
    try:
        result = manager.exec(record, service, command)
    except ContainerError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    if result.stdout:
        console.print(result.stdout.rstrip())
    if result.stderr:
        console.print(result.stderr.rstrip())
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@ctr_app.command("cleanup")
def ctr_cleanup_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Remove all containers and network for a worktree."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    manager = ContainerManager(repo_root, config)
    try:
        manager.cleanup(record)
    except ContainerError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"cleaned up containers for {name}")


@secrets_app.command("get")
def secrets_get_cmd(
    name: str,
    key: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Get a secret value."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.secrets.enabled:
        console.print("secrets management is not enabled in config")
        raise typer.Exit(code=2)

    manager = SecretsManager(repo_root, config)
    value = manager.get(record, key)

    if value is None:
        console.print(f"secret not found: {key}")
        raise typer.Exit(code=1)

    console.print(value)


@secrets_app.command("set")
def secrets_set_cmd(
    name: str,
    key: str,
    value: Optional[str] = typer.Argument(None),
    stdin: bool = typer.Option(False, "--stdin", help="Read value from stdin"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Set a secret value."""
    import sys

    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.secrets.enabled:
        console.print("secrets management is not enabled in config")
        raise typer.Exit(code=2)

    if stdin:
        secret_value = sys.stdin.read().strip()
    elif value is not None:
        secret_value = value
    else:
        console.print("provide a value or use --stdin")
        raise typer.Exit(code=2)

    manager = SecretsManager(repo_root, config)
    try:
        manager.set(record, key, secret_value)
    except SecretsError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"set secret: {key}")


@secrets_app.command("delete")
def secrets_delete_cmd(
    name: str,
    key: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Delete a secret."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.secrets.enabled:
        console.print("secrets management is not enabled in config")
        raise typer.Exit(code=2)

    manager = SecretsManager(repo_root, config)
    if not manager.exists(record, key):
        console.print(f"secret not found: {key}")
        raise typer.Exit(code=1)

    manager.delete(record, key)
    console.print(f"deleted secret: {key}")


@secrets_app.command("ls")
def secrets_ls_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """List secret keys."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.secrets.enabled:
        console.print("secrets management is not enabled in config")
        raise typer.Exit(code=2)

    manager = SecretsManager(repo_root, config)
    keys = manager.list_keys(record)

    if not keys:
        console.print("no secrets stored")
        return

    for key in sorted(keys):
        console.print(key)


@secrets_app.command("sync")
def secrets_sync_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Sync secrets to worktree .env file."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.secrets.enabled:
        console.print("secrets management is not enabled in config")
        raise typer.Exit(code=2)

    manager = SecretsManager(repo_root, config)
    try:
        count = manager.sync_to_env(record)
    except SecretsError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)

    console.print(f"synced {count} secrets to {config.env.dotenv_file}")


@secrets_app.command("check")
def secrets_check_cmd(
    name: str,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Check for missing required secrets."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if not config.secrets.enabled:
        console.print("secrets management is not enabled in config")
        raise typer.Exit(code=2)

    manager = SecretsManager(repo_root, config)
    missing = manager.check_required(record)

    if not missing:
        console.print("all required secrets present")
        return

    console.print(f"missing required secrets: {', '.join(missing)}")
    raise typer.Exit(code=1)


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


@app.command("gc")
def gc_cmd(
    inactive_days: Optional[int] = typer.Option(None, "--inactive-days"),
    include_absent: bool = typer.Option(False, "--include-absent"),
    dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    force: bool = typer.Option(False, "--force"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    """Garbage collect worktrees by criteria."""
    repo_root = _repo_root()
    config = _load_config(repo_root, profile)
    init_db(repo_root)
    records = reindex(repo_root, config)
    locked = {lock.worktree_id for lock in repos.list_locks(repo_root)}

    candidates = select_gc_candidates(
        records,
        locked_ids=locked,
        inactive_days=inactive_days,
        include_absent=include_absent,
    )

    if not candidates:
        console.print("no worktrees matched gc criteria")
        return

    table = Table(title="GC Candidates")
    table.add_column("name")
    table.add_column("reason")
    table.add_column("last_accessed")
    table.add_column("path")

    for candidate in candidates:
        record = candidate.record
        last_seen = record.last_accessed_at or record.created_at
        table.add_row(
            record.name,
            candidate.reason,
            last_seen.isoformat(sep=" ", timespec="minutes"),
            str(record.path),
        )
    console.print(table)

    if dry_run:
        return

    removed = 0
    for candidate in candidates:
        record = candidate.record
        if record.lifecycle == "ABSENT":
            repos.update_worktree_state(repo_root, record.id, lifecycle="ABSENT")
            _record_event(repo_root, record.id, "GcPruned", None, "ABSENT")
            removed += 1
            continue

        if config.safety.refuse_remove_if_dirty and record.git_dirty and not force:
            console.print(f"skipping {record.name}: dirty worktree")
            continue
        if config.safety.refuse_remove_if_unpushed and record.ahead > 0 and not force:
            console.print(f"skipping {record.name}: unpushed commits")
            continue

        _run_hooks("pre_remove", config.hooks.pre_remove, repo_root, record.path)
        try:
            git.remove_worktree(repo_root, str(record.path), force=force)
        except git.GitError as exc:
            _record_event(
                repo_root, record.id, "GcFailed", None, None, message=str(exc)
            )
            console.print(f"gc failed for {record.name}: {exc}")
            continue

        _record_event(repo_root, record.id, "GcRemoved", None, "ABSENT")
        removed += 1

    console.print(f"gc removed {removed} worktree(s)")


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
