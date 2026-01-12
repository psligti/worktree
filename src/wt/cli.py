from __future__ import annotations

import json
import os
import subprocess
import uuid
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
from .domain.status import overall_status
from .git import adapter as git
from .ops.doctor import doctor as doctor_check
from .ops.reindex import reindex
from .persistence import repos
from .persistence.db import connect, init_db
from .tmux.adapter import TmuxError, ensure_session, focus_window, open_window, setup_layout


app = typer.Typer(add_completion=False)
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
""".strip()

UI_PROFILE_TOML = """
[hooks]
post_create = ["uv sync", "uv run ui:install"]
post_switch = ["uv sync"]

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
) -> None:
    """Create a new worktree and optionally bootstrap/open it."""
    repo_root = _repo_root()
    name = _normalize_worktree_name(name)
    if not name:
        console.print("invalid worktree name")
        raise typer.Exit(code=2)
    config = _load_config(repo_root, profile)
    init_db(repo_root)

    worktree_root = Path(repo_root) / config.worktrees.root
    worktree_root.mkdir(parents=True, exist_ok=True)
    path = worktree_root / name
    path_str = str(path)
    branch = f"wt/{name}"

    record = _seed_record(path, name, branch, config)
    with connect(repo_root) as conn:
        repos.upsert_worktree(conn, record)
    _record_event(repo_root, record.id, "CreateRequested", "ABSENT", "CREATING")

    try:
        git.add_worktree(repo_root, path_str, branch, base or config.worktrees.default_base, detached=False)
        apply_templates(repo_root, path_str, config)
        _record_event(repo_root, record.id, "CreateSucceeded", "CREATING", "READY")
    except git.GitError as exc:
        repos.update_worktree_state(repo_root, record.id, lifecycle="BROKEN", last_error=str(exc))
        _record_event(repo_root, record.id, "CreateFailed", "CREATING", "BROKEN", message=str(exc))
        raise typer.Exit(code=5)

    records = reindex(repo_root, config)
    record = _find_record(records, name)

    if bootstrap:
        _bootstrap(repo_root, record, config)
    if open_window:
        _open(repo_root, record, config, None, editor=True)

    console.print(f"created worktree {name}")


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
    _open(repo_root, record, config, layout, editor)


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
def ls_cmd(profile: Optional[str] = typer.Option(None, "--profile"), json_output: bool = typer.Option(False, "--json")) -> None:
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

    base_ref = config.worktrees.default_base
    branch = record.branch or f"wt/{name}"

    try:
        git.checkout(repo_root, base_ref)
        if run_checks:
            console.print("run checks not implemented; skipping")
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
        try:
            git.remove_worktree(repo_root, str(record.path), force=False)
        except git.GitError as exc:
            console.print(f"cleanup failed: {exc}")
            raise typer.Exit(code=5)


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

    try:
        git.remove_worktree(repo_root, str(record.path), force=force)
    except git.GitError as exc:
        _record_event(repo_root, record.id, "RemoveFailed", None, None, message=str(exc))
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


def _load_config(repo_root: str, profile: Optional[str]) -> WtConfig:
    try:
        config = load_config(repo_root, profile)
    except Exception as exc:  # pragma: no cover - defensive
        console.print(str(exc))
        raise typer.Exit(code=1)
    _ensure_default_layouts(config)
    return config


def _ensure_default_layouts(config: WtConfig) -> None:
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


def _seed_record(path: Path, name: str, branch: str, config: WtConfig) -> WorktreeRecord:
    now = datetime.now(timezone.utc)
    return WorktreeRecord(
        id=_stable_id(path),
        name=name,
        path=path,
        branch=branch,
        head_sha=None,
        base_ref=config.worktrees.default_base,
        lifecycle="CREATING",
        bootstrap="UNBOOTSTRAPPED",
        agent="DETACHED",
        runtime="STOPPED",
        git_dirty=False,
        git_sync=None,
        upstream=None,
        ahead=0,
        behind=0,
        behind_main=0,
        created_at=now,
        last_accessed_at=None,
        last_error=None,
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
    _record_event(repo_root, record.id, "BootstrapRequested", record.bootstrap, "BOOTSTRAPPING")
    try:
        bootstrap_worktree(repo_root, record, config)
    except BootstrapError as exc:
        repos.update_worktree_state(repo_root, record.id, bootstrap="BOOTSTRAP_ERROR", last_error=str(exc))
        _record_event(repo_root, record.id, "BootstrapFailed", "BOOTSTRAPPING", "BOOTSTRAP_ERROR", message=str(exc))
        raise typer.Exit(code=5)

    repos.update_worktree_state(repo_root, record.id, bootstrap="BOOTSTRAPPED")
    _record_event(repo_root, record.id, "BootstrapSucceeded", "BOOTSTRAPPING", "BOOTSTRAPPED")
    console.print(f"bootstrapped {record.name}")


def _open(repo_root: str, record: WorktreeRecord, config: WtConfig, layout: Optional[str], editor: bool) -> None:
    layout_name = layout or config.tmux.default_layout
    layout_config = config.tmux.layouts.get(layout_name)
    if not layout_config:
        console.print(f"unknown layout: {layout_name}")
        raise typer.Exit(code=2)

    session = config.tmux.session
    if session == "repo":
        session = os.path.basename(repo_root)

    try:
        ensure_session(session)
        window_id = open_window(session, record.name, str(record.path))
        setup_layout(window_id, str(record.path), layout_config.layout, layout_config.panes, layout_config.commands)
        focus_window(window_id, session)
    except TmuxError as exc:
        console.print(str(exc))
        raise typer.Exit(code=5)

    repos.update_worktree_state(repo_root, record.id, last_accessed_at=datetime.now(timezone.utc).isoformat())

    if editor:
        _open_editor(str(record.path), config)

    console.print(f"opened {record.name} in tmux session {session}")


def _open_editor(path: str, config: WtConfig) -> None:
    if not config.open.editor_cmd:
        return
    subprocess.Popen([*config.open.editor_cmd, path])


def _ensure_repo_layout(repo_root: str) -> None:
    root = Path(repo_root) / ".wt"
    config_dir = root / "config"
    templates_dir = root / "templates"
    profiles_dir = config_dir / "profiles"
    hooks_dir = config_dir / "hooks.d"

    (hooks_dir / "post_create.d").mkdir(parents=True, exist_ok=True)
    (hooks_dir / "post_switch.d").mkdir(parents=True, exist_ok=True)
    (hooks_dir / "pre_remove.d").mkdir(parents=True, exist_ok=True)

    (templates_dir / "env").mkdir(parents=True, exist_ok=True)
    (templates_dir / "agent").mkdir(parents=True, exist_ok=True)
    (templates_dir / "worktree").mkdir(parents=True, exist_ok=True)
    profiles_dir.mkdir(parents=True, exist_ok=True)

    _write_if_missing(config_dir / "wt.toml", DEFAULT_CONFIG_TOML)
    _write_if_missing(profiles_dir / "default.toml", DEFAULT_PROFILE_TOML)
    _write_if_missing(profiles_dir / "ui-dev.toml", UI_PROFILE_TOML)
    _write_if_missing(profiles_dir / "agent.toml", AGENT_PROFILE_TOML)

    _write_if_missing(templates_dir / "env" / ".env.base", ENV_TEMPLATE)
    _write_if_missing(templates_dir / "agent" / "context.md", CONTEXT_TEMPLATE)
    _write_if_missing(templates_dir / "agent" / "runbook.md", RUNBOOK_TEMPLATE)
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
