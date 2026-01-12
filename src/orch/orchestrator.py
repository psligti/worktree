from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import yaml

from .agent_service import AgentService
from .models import (
    AgentRuntimeState,
    AgentRunSpec,
    ConfigDocument,
    DefaultsConfig,
    ProjectConfig,
    ProviderConfig,
    Story,
    TaskListItem,
    TaskRuntimeState,
    TasksDocument,
)
from .state_store import StateStore
from .task_store import TaskStore
from .tmux_service import PaneInfo, TmuxService, WindowInfo
from .worktree_service import WorktreeEntry, WorktreeService


class OrchestratorError(RuntimeError):
    pass


class Orchestrator:
    def __init__(
        self,
        repo_root: Path,
        tasks_path: Path,
        state_path: Path,
        config_path: Optional[Path] = None,
        prompt_template_path: Optional[Path] = None,
        session_override: Optional[str] = None,
    ) -> None:
        self.repo_root = repo_root
        self.tasks_path = tasks_path
        self.state_path = state_path
        self.config_path = config_path
        self.prompt_template_path = prompt_template_path
        self.session_override = session_override
        self.task_store = TaskStore(tasks_path)
        self.state_store = StateStore(state_path)
        self.worktree_service = WorktreeService(repo_root)

    def bootstrap(self) -> None:
        tasks_doc = self.task_store.load()
        config = self._build_project_config(tasks_doc)
        tmux_service = TmuxService(config.tmux.session)
        state = self.state_store.load(self.repo_root, config.tmux.session)

        worktrees = {entry.path.resolve(): entry for entry in self.worktree_service.list_worktrees()}
        windows = {window.name: window for window in tmux_service.list_windows()}

        for epic in tasks_doc.epics:
            for story in epic.stories:
                runtime = self._reconcile_story(
                    story,
                    config=config,
                    tmux_service=tmux_service,
                    windows=windows,
                    worktrees=worktrees,
                    state=state,
                )
                state.tasks[story.id] = runtime

        state.repo_root = self.repo_root
        state.tmux_session = config.tmux.session
        self.state_store.write(state)
        return None

    def list_tasks(self, epic_id: Optional[str] = None, status: Optional[str] = None) -> List[TaskListItem]:
        tasks_doc = self.task_store.load()
        config = self._build_project_config(tasks_doc)
        tmux_service = TmuxService(config.tmux.session)
        state = self.state_store.load(self.repo_root, config.tmux.session)
        windows = {window.name for window in tmux_service.list_windows()}
        worktree_paths = {entry.path.resolve() for entry in self.worktree_service.list_worktrees()}

        items: List[TaskListItem] = []
        for epic in tasks_doc.epics:
            if epic_id and epic.id != epic_id:
                continue
            for story in epic.stories:
                runtime = state.tasks.get(story.id)
                worktree_path = self._worktree_path(config, story)
                tmux_window = self._tmux_window(config, story)
                item = TaskListItem(
                    story_id=story.id,
                    epic_id=epic.id,
                    title=story.title,
                    done=story.done,
                    status=runtime.status if runtime else "backlog",
                    has_worktree=worktree_path.resolve() in worktree_paths,
                    has_tmux_window=tmux_window in windows,
                    agent_status=(runtime.agent.status if runtime and runtime.agent else "unknown"),
                )
                if status and item.status != status:
                    continue
                items.append(item)
        return items

    def start_story(
        self,
        story_id: str,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        tests_cmd: Optional[str] = None,
        dry_run: bool = False,
    ) -> TaskRuntimeState:
        tasks_doc = self.task_store.load()
        config = self._build_project_config(tasks_doc)
        story = self.task_store.find_story(tasks_doc, story_id)
        if not story:
            raise OrchestratorError(f"story not found: {story_id}")

        branch = self._branch_name(config, story)
        worktree_path = self._worktree_path(config, story)
        tmux_window = self._tmux_window(config, story)
        tmux = TmuxService(config.tmux.session)

        if not dry_run:
            self.worktree_service.ensure_worktree(worktree_path, branch, "HEAD")
            tmux.ensure_session(self.repo_root)
            panes = tmux.ensure_panes(tmux_window, config.tmux.pane_titles, worktree_path, config.tmux.layout)
        else:
            panes = {}

        prompt = self._build_prompt(story, config)
        provider_key, provider = self._resolve_provider(config, provider_name)
        run_spec = AgentRunSpec(
            provider=provider_key,
            model=model or provider.model,
            prompt=prompt,
            workdir=worktree_path,
            env={"STORY_ID": story.id},
        )

        agent_state = AgentRuntimeState(provider=run_spec.provider, model=run_spec.model, status="active", started_at=_now())

        if not dry_run:
            agent_service = AgentService(tmux, self.repo_root / ".orch" / "prompts")
            codex_pane = panes.get("codex") or tmux.resolve_pane(tmux_window, "codex")
            if codex_pane:
                agent_service.start_agent(codex_pane, provider, run_spec, None)
            tests_command = tests_cmd or _story_test_command(story, config.defaults)
            if tests_command:
                tests_pane = panes.get("tests") or tmux.resolve_pane(tmux_window, "tests")
                if tests_pane:
                    tmux.send_keys(tests_pane, tests_command, enter=True)

        state = self.state_store.load(self.repo_root, config.tmux.session)
        existing = state.tasks.get(story.id)
        runtime = TaskRuntimeState(
            story_id=story.id,
            branch=branch,
            worktree_path=worktree_path,
            tmux_window=tmux_window,
            panes=panes,
            agent=agent_state,
            status="active",
            last_action="start",
            created_at=existing.created_at if existing and existing.created_at else _now(),
            updated_at=_now(),
            last_action_at=_now(),
        )
        state.tasks[story.id] = runtime
        if not dry_run:
            self.state_store.write(state)
        return runtime

    def start_epic(
        self,
        epic_id: str,
        max_concurrency: int,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        tests_cmd: Optional[str] = None,
        dry_run: bool = False,
    ) -> List[TaskRuntimeState]:
        tasks_doc = self.task_store.load()
        epic = self.task_store.find_epic(tasks_doc, epic_id)
        if not epic:
            raise OrchestratorError(f"epic not found: {epic_id}")
        started: List[TaskRuntimeState] = []
        for story in epic.stories:
            if story.done:
                continue
            if len(started) >= max_concurrency:
                break
            started.append(
                self.start_story(
                    story.id,
                    provider_name=provider_name,
                    model=model,
                    tests_cmd=tests_cmd,
                    dry_run=dry_run,
                )
            )
        return started

    def attach(self, story_id: str, pane: Optional[str] = None) -> None:
        tasks_doc = self.task_store.load()
        config = self._build_project_config(tasks_doc)
        story = self.task_store.find_story(tasks_doc, story_id)
        if not story:
            raise OrchestratorError(f"story not found: {story_id}")
        tmux_window = self._tmux_window(config, story)
        tmux = TmuxService(config.tmux.session)
        tmux.focus_window(tmux_window, pane)

    def pause(self, story_id: str) -> TaskRuntimeState:
        tasks_doc = self.task_store.load()
        config = self._build_project_config(tasks_doc)
        state = self.state_store.load(self.repo_root, config.tmux.session)
        runtime = state.tasks.get(story_id)
        if not runtime:
            raise OrchestratorError(f"story not in state: {story_id}")
        tmux = TmuxService(config.tmux.session)
        for pane_title in ("codex", "tests"):
            pane_target = runtime.panes.get(pane_title) or tmux.resolve_pane(runtime.tmux_window, pane_title)
            if pane_target:
                tmux.send_ctrl_c(pane_target)
        runtime.status = "paused"
        runtime.last_action = "pause"
        runtime.updated_at = _now()
        runtime.last_action_at = _now()
        if runtime.agent:
            runtime.agent.status = "stopped"
        state.tasks[story_id] = runtime
        self.state_store.write(state)
        return runtime

    def resume(
        self,
        story_id: str,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        tests_cmd: Optional[str] = None,
    ) -> TaskRuntimeState:
        runtime = self.start_story(story_id, provider_name=provider_name, model=model, tests_cmd=tests_cmd)
        runtime.last_action = "resume"
        return runtime

    def done(self, story_id: str, write_back_yaml: bool, cleanup_worktree: bool) -> TaskRuntimeState:
        tasks_doc = self.task_store.load()
        config = self._build_project_config(tasks_doc)
        state = self.state_store.load(self.repo_root, config.tmux.session)
        runtime = state.tasks.get(story_id)
        if not runtime:
            raise OrchestratorError(f"story not in state: {story_id}")
        runtime.status = "done"
        runtime.last_action = "done"
        runtime.updated_at = _now()
        runtime.last_action_at = _now()
        if runtime.agent:
            runtime.agent.status = "stopped"
        state.tasks[story_id] = runtime
        self.state_store.write(state)

        if write_back_yaml:
            self.task_store.mark_story_done(story_id, True)
        if cleanup_worktree:
            if self.worktree_service.is_dirty(runtime.worktree_path):
                raise OrchestratorError("worktree has uncommitted changes; cleanup refused")
            self.worktree_service.remove_worktree(runtime.worktree_path)
        return runtime

    def status_summary(self) -> Dict[str, int]:
        tasks = self.list_tasks()
        counts: Dict[str, int] = {}
        for item in tasks:
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    def next_waiting(self) -> Optional[str]:
        tasks = self.list_tasks(status="waiting_human")
        if tasks:
            return tasks[0].story_id
        return None

    def _build_project_config(self, tasks_doc: TasksDocument) -> ProjectConfig:
        settings = tasks_doc.settings
        providers = dict(tasks_doc.providers)

        if self.config_path and self.config_path.exists():
            override = ConfigDocument.model_validate(
                yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
            )
            settings = settings.model_copy(update=override.model_dump(exclude={"providers"}))
            providers.update(override.providers)

        config = ProjectConfig(
            repo_root=self.repo_root,
            branch_prefix=settings.branch_prefix,
            worktree_dir_template=settings.worktree_dir_template,
            tmux=settings.tmux,
            defaults=settings.defaults,
            providers=providers,
        )
        if self.session_override:
            config.tmux = config.tmux.model_copy(update={"session": self.session_override})
        return config

    def _reconcile_story(
        self,
        story: Story,
        config: ProjectConfig,
        tmux_service: TmuxService,
        windows: Mapping[str, WindowInfo],
        worktrees: Mapping[Path, WorktreeEntry],
        state,
    ) -> TaskRuntimeState:
        branch = self._branch_name(config, story)
        worktree_path = self._worktree_path(config, story)
        tmux_window = self._tmux_window(config, story)
        panes_map: Dict[str, str] = {}
        agent_state = None
        agent_active = False

        if tmux_window in windows:
            panes = tmux_service.list_panes(tmux_window)
            panes_map = {pane.title: pane.pane_id for pane in panes if pane.title}
            agent_active = _agent_running(panes)
            if panes_map.get("codex"):
                agent_state = AgentRuntimeState(
                    provider="codex",
                    model="DEFAULT",
                    status="active" if agent_active else "idle",
                    started_at=None,
                )

        status = "backlog"
        if story.done:
            status = "done"
        elif tmux_window in windows and agent_active:
            status = "active"
        elif worktree_path.resolve() in worktrees:
            status = "paused"

        window_flags = getattr(windows.get(tmux_window), "flags", "") if tmux_window in windows else ""
        if status in {"paused", "backlog"} and "!" in window_flags:
            status = "waiting_human"

        existing = state.tasks.get(story.id)
        runtime = TaskRuntimeState(
            story_id=story.id,
            branch=branch,
            worktree_path=worktree_path,
            tmux_window=tmux_window,
            panes=panes_map,
            agent=agent_state,
            status=status,
            last_action=existing.last_action if existing else "",
            created_at=existing.created_at if existing else _now(),
            updated_at=_now(),
            last_action_at=existing.last_action_at if existing else None,
        )
        return runtime

    def _resolve_provider(self, config: ProjectConfig, provider_name: Optional[str]) -> tuple[str, ProviderConfig]:
        provider_key = provider_name or "codex"
        provider = config.providers.get(provider_key)
        if not provider:
            raise OrchestratorError(f"provider not configured: {provider_key}")
        if not provider.enabled:
            raise OrchestratorError(f"provider disabled: {provider_key}")
        return provider_key, provider

    def _branch_name(self, config: ProjectConfig, story: Story) -> str:
        slug = slugify(story.title)
        return f"{config.branch_prefix}/{story.id}-{slug}" if slug else f"{config.branch_prefix}/{story.id}"

    def _worktree_path(self, config: ProjectConfig, story: Story) -> Path:
        slug = slugify(story.title)
        repo_name = self.repo_root.name
        template = config.worktree_dir_template
        path = template.format(repo=repo_name, story_id=story.id, slug=slug, short_slug=slug[:12])
        resolved = Path(path)
        if not resolved.is_absolute():
            return (self.repo_root / resolved).resolve()
        return resolved

    def _tmux_window(self, config: ProjectConfig, story: Story) -> str:
        slug = slugify(story.title)
        return config.tmux.window_template.format(story_id=story.id, slug=slug, short_slug=slug[:12])

    def _build_prompt(self, story: Story, config: ProjectConfig) -> str:
        test_command = _story_test_command(story, config.defaults)
        acceptance = "\n".join(f"- {item}" for item in story.acceptance_criteria)
        constraints = ["Work in this worktree only.", "Make small, reviewable commits (do not merge)."]
        if test_command:
            constraints.append(f"Prefer tests-first; run: {test_command}")
        constraints.append("Keep logs structured.")
        constraints_text = "\n".join(f"- {item}" for item in constraints)

        default_prompt = (
            f"TASK: {story.id} - {story.title}.\n\n"
            f"Acceptance Criteria:\n{acceptance}\n\n"
            f"Constraints:\n{constraints_text}\n\n"
            "Deliverables:\n"
            "1) Implementation changes\n"
            "2) Tests added/updated\n"
            "3) Notes on decisions and tradeoffs\n"
        )
        if self.prompt_template_path and self.prompt_template_path.exists():
            template = self.prompt_template_path.read_text(encoding="utf-8")
            return _render_template(
                template,
                {
                    "story_id": story.id,
                    "title": story.title,
                    "acceptance_criteria": acceptance,
                    "constraints": constraints_text,
                    "test_command": test_command,
                },
            )
        return default_prompt


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _agent_running(panes: List[PaneInfo]) -> bool:
    for pane in panes:
        if pane.title != "codex":
            continue
        command = pane.current_command.strip()
        if command and command not in {"bash", "zsh", "sh", "fish", "tmux"}:
            return True
    return False


def _story_test_command(story: Story, defaults: DefaultsConfig) -> str:
    if story.commands and story.commands.test_command:
        return story.commands.test_command
    return defaults.test_command


def _render_template(template: str, data: Dict[str, str]) -> str:
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(SafeDict(data))
