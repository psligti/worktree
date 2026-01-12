from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field


class WorktreeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root: str = ".worktrees"
    default_base: str = "main"


class EnvConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str = "uv"
    venv_dir: str = ".venv"
    dotenv_file: str = ".env"
    direnv_file: str = ".envrc"
    unique_ports: bool = True
    port_keys: List[str] = Field(default_factory=lambda: ["APP_PORT", "UI_PORT"])


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    root_dir: str = ".agent"


class OpenConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    editor_cmd: List[str] = Field(default_factory=lambda: ["pycharm"])
    prefer_tmux: bool = True


class TmuxLayoutConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    layout: str = "even-horizontal"
    panes: List[str] = Field(default_factory=lambda: ["shell"])
    commands: Dict[str, str] = Field(default_factory=dict)


class TmuxConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session: str = "repo"
    default_layout: str = "single"
    layouts: Dict[str, TmuxLayoutConfig] = Field(default_factory=dict)


class HooksConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    post_create: List[str] = Field(default_factory=list)
    post_switch: List[str] = Field(default_factory=list)
    pre_remove: List[str] = Field(default_factory=list)
    run_checks: List[str] = Field(default_factory=list)


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    refuse_remove_if_dirty: bool = True
    refuse_remove_if_unpushed: bool = True


class WtConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    worktrees: WorktreeConfig = Field(default_factory=WorktreeConfig)
    env: EnvConfig = Field(default_factory=EnvConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    open: OpenConfig = Field(default_factory=OpenConfig)
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
