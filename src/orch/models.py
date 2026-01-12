from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


PromptMode = Literal["stdin", "arg", "file"]
TaskStatus = Literal["backlog", "active", "paused", "waiting_human", "done", "blocked"]
AgentStatus = Literal["active", "idle", "stopped", "unknown"]


class ProjectMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    repo_root: Path = Path(".")


class DefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    test_command: str = ""
    git_command: str = ""
    editor_command: str = ""


class StoryCommands(BaseModel):
    model_config = ConfigDict(extra="ignore")

    test_command: Optional[str] = None
    git_command: Optional[str] = None
    editor_command: Optional[str] = None


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    start_command_template: str = ""
    model: str = "DEFAULT"
    prompt_mode: PromptMode = "stdin"


class TmuxConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session: str = "repo"
    window_template: str = "{story_id}"
    layout: str = "tiled"
    pane_titles: List[str] = Field(default_factory=lambda: ["editor", "codex", "tests", "git"])


class SettingsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    branch_prefix: str = "task"
    worktree_dir_template: str = "../{repo}-{story_id}"
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)


class Story(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    done: bool = False
    acceptance_criteria: List[str] = Field(default_factory=list)
    owner: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    commands: Optional[StoryCommands] = None


class Epic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    done: bool = False
    stories: List[Story] = Field(default_factory=list)


class TasksDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    project: ProjectMeta = Field(default_factory=ProjectMeta)
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    epics: List[Epic] = Field(default_factory=list)


class ConfigDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    branch_prefix: str = "task"
    worktree_dir_template: str = "../{repo}-{story_id}"
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repo_root: Path
    branch_prefix: str
    worktree_dir_template: str
    tmux: TmuxConfig
    defaults: DefaultsConfig
    providers: Dict[str, ProviderConfig]


class AgentRunSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    model: str
    prompt: str
    workdir: Path
    env: Dict[str, str] = Field(default_factory=dict)


class PaneRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session: str
    window: str
    pane_title: str
    target: str


class AgentRuntimeState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    model: str
    status: AgentStatus = "unknown"
    started_at: Optional[datetime] = None


class TaskRuntimeState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    story_id: str
    branch: str
    worktree_path: Path
    tmux_window: str
    panes: Dict[str, str] = Field(default_factory=dict)
    agent: Optional[AgentRuntimeState] = None
    status: TaskStatus = "backlog"
    last_action: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_action_at: Optional[datetime] = None


class StateFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    repo_root: Path
    tmux_session: str
    tasks: Dict[str, TaskRuntimeState] = Field(default_factory=dict)


class TaskListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    story_id: str
    epic_id: str
    title: str
    done: bool
    status: str
    has_worktree: bool
    has_tmux_window: bool
    agent_status: str
