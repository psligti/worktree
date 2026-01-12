from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .orchestrator import Orchestrator, OrchestratorError


app = typer.Typer(add_completion=False)
console = Console()


def _build_orchestrator(
    repo_root: Optional[Path],
    tasks_path: Optional[Path],
    session: Optional[str] = None,
) -> Orchestrator:
    root = Path(repo_root or Path.cwd())
    tasks = Path(tasks_path) if tasks_path else root / "tasks.yaml"
    if tasks.exists():
        try:
            from .task_store import TaskStore

            doc = TaskStore(tasks).load()
            if not repo_root:
                root = (tasks.parent / doc.project.repo_root).resolve()
        except Exception:
            pass
    config_path = root / ".orch" / "config.yaml"
    state_path = root / ".orch" / "state.json"
    prompt_template = root / ".orch" / "templates" / "task_prompt.md"
    return Orchestrator(
        repo_root=root,
        tasks_path=tasks,
        state_path=state_path,
        config_path=config_path,
        prompt_template_path=prompt_template,
        session_override=session,
    )


@app.command("bootstrap")
def bootstrap(
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Parse tasks, scan runtime, and reconcile state."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    orch.bootstrap()
    console.print("bootstrap complete")


@app.command("list")
def list_cmd(
    epic: Optional[str] = typer.Option(None, "--epic"),
    status: Optional[str] = typer.Option(None, "--status"),
    as_json: bool = typer.Option(False, "--json"),
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """List stories with runtime info."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    items = orch.list_tasks(epic_id=epic, status=status)
    if as_json:
        console.print(json.dumps([item.model_dump(mode="json") for item in items], indent=2))
        return
    table = Table(title="Stories")
    table.add_column("Story")
    table.add_column("Epic")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Worktree")
    table.add_column("tmux")
    table.add_column("Agent")
    for item in items:
        table.add_row(
            item.story_id,
            item.epic_id,
            item.title,
            item.status,
            "yes" if item.has_worktree else "no",
            "yes" if item.has_tmux_window else "no",
            item.agent_status,
        )
    console.print(table)


@app.command("start")
def start_cmd(
    story_id: Optional[str] = typer.Argument(None),
    epic: Optional[str] = typer.Option(None, "--epic"),
    max_concurrency: int = typer.Option(1, "--max-concurrency"),
    provider: Optional[str] = typer.Option(None, "--provider"),
    model: Optional[str] = typer.Option(None, "--model"),
    tests_cmd: Optional[str] = typer.Option(None, "--tests-cmd"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Start a story or batch start an epic."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    try:
        if epic:
            started = orch.start_epic(
                epic,
                max_concurrency=max_concurrency,
                provider_name=provider,
                model=model,
                tests_cmd=tests_cmd,
                dry_run=dry_run,
            )
            console.print(f"started {len(started)} stories from {epic}")
        elif story_id:
            orch.start_story(
                story_id,
                provider_name=provider,
                model=model,
                tests_cmd=tests_cmd,
                dry_run=dry_run,
            )
            console.print(f"started {story_id}")
        else:
            raise OrchestratorError("provide STORY_ID or --epic")
    except OrchestratorError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)


@app.command("attach")
def attach_cmd(
    story_id: str,
    pane: Optional[str] = typer.Option(None, "--pane"),
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Attach or switch to the story window/pane."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    orch.attach(story_id, pane=pane)
    if not os.environ.get("TMUX"):
        config = orch._build_project_config(orch.task_store.load())
        subprocess.run(["tmux", "attach", "-t", config.tmux.session], check=False)


@app.command("pause")
def pause_cmd(
    story_id: str,
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Pause agent/tests in tmux panes."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    try:
        orch.pause(story_id)
        console.print(f"paused {story_id}")
    except OrchestratorError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)


@app.command("resume")
def resume_cmd(
    story_id: str,
    provider: Optional[str] = typer.Option(None, "--provider"),
    model: Optional[str] = typer.Option(None, "--model"),
    tests_cmd: Optional[str] = typer.Option(None, "--tests-cmd"),
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Resume agent/tests in tmux panes."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    try:
        orch.resume(story_id, provider_name=provider, model=model, tests_cmd=tests_cmd)
        console.print(f"resumed {story_id}")
    except OrchestratorError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)


@app.command("done")
def done_cmd(
    story_id: str,
    write_back_yaml: bool = typer.Option(False, "--write-back-yaml"),
    cleanup_worktree: bool = typer.Option(False, "--cleanup-worktree"),
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Mark done and optionally write back YAML/cleanup worktree."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    try:
        orch.done(story_id, write_back_yaml=write_back_yaml, cleanup_worktree=cleanup_worktree)
        console.print(f"done {story_id}")
    except OrchestratorError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)


@app.command("status")
def status_cmd(
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    as_json: bool = typer.Option(False, "--json"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Show status summary."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    summary = orch.status_summary()
    waiting = orch.list_tasks(status="waiting_human")
    if as_json:
        console.print(
            json.dumps(
                {"summary": summary, "waiting_human": [item.model_dump(mode="json") for item in waiting]},
                indent=2,
            )
        )
        return
    for key, value in summary.items():
        console.print(f"{key}: {value}")
    if waiting:
        console.print("waiting_human queue:")
        for item in waiting:
            console.print(f"- {item.story_id} {item.title}")


@app.command("prompt")
def prompt_cmd(
    story_id: str,
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Render the prompt for a story."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    try:
        prompt = orch.render_prompt(story_id)
    except OrchestratorError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1)
    console.print(prompt)


@app.command("next")
def next_cmd(
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Attach to next waiting_human task."""
    orch = _build_orchestrator(repo_root, tasks_path, session)
    story_id = orch.next_waiting()
    if not story_id:
        console.print("no waiting_human tasks")
        return
    orch.attach(story_id, pane="codex")
    if not os.environ.get("TMUX"):
        config = orch._build_project_config(orch.task_store.load())
        subprocess.run(["tmux", "attach", "-t", config.tmux.session], check=False)


@app.command("tui")
def tui_cmd(
    repo_root: Optional[Path] = typer.Option(None, "--repo-root"),
    tasks_path: Optional[Path] = typer.Option(None, "--tasks"),
    session: Optional[str] = typer.Option(None, "--session"),
) -> None:
    """Launch the Textual TUI."""
    from .tui import run_tui

    run_tui(repo_root=repo_root, tasks_path=tasks_path, session=session)
