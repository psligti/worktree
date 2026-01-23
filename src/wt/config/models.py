from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class WorktreeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    root: str = ".worktrees"
    default_base: str = "main"


class EnvConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["uv", "poetry", "auto"] = "auto"
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


class OpenCodeThemesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    codex: List[str] = Field(default_factory=list)
    copilot: List[str] = Field(default_factory=list)

    def for_connection(self, connection: Optional[str]) -> List[str]:
        if connection == "codex":
            return list(self.codex)
        if connection == "copilot":
            return list(self.copilot)
        return []


class OpenCodeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    connection: Optional[str] = None
    config_path: str = ".opencode/config.json"
    themes: OpenCodeThemesConfig = Field(default_factory=OpenCodeThemesConfig)


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


class ServiceHealthCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["http", "tcp", "command"] = "http"
    target: str = ""
    interval_seconds: int = 5
    timeout_seconds: int = 30


class ServiceDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    command: str
    pane: Optional[str] = None
    port_key: Optional[str] = None
    health_check: Optional[ServiceHealthCheck] = None
    depends_on: List[str] = Field(default_factory=list)


class ServicesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    definitions: Dict[str, ServiceDefinition] = Field(default_factory=dict)


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    default_type: Literal["postgres", "sqlite"] = "sqlite"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: Optional[str] = None
    auto_create: bool = True
    auto_drop_on_remove: bool = False


class ContainerDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    image: str
    command: Optional[str] = None
    ports: Dict[str, str] = Field(default_factory=dict)
    volumes: Dict[str, str] = Field(default_factory=dict)
    environment: Dict[str, str] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    network: Optional[str] = None


class ContainerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    runtime: Literal["docker", "podman", "auto"] = "auto"
    compose_file: Optional[str] = None
    project_prefix: str = "wt"
    auto_start: bool = False
    auto_stop_on_remove: bool = True
    definitions: Dict[str, ContainerDefinition] = Field(default_factory=dict)


class SecretsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    backend: Literal["env", "keyring", "encrypted"] = "env"
    env_file: str = ".env.secrets"
    encrypted_file: str = ".wt/secrets.enc"
    key_file: str = ".wt/secrets.key"
    sync_to_env: bool = True
    required_keys: List[str] = Field(default_factory=list)


class WtConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    worktrees: WorktreeConfig = Field(default_factory=WorktreeConfig)
    env: EnvConfig = Field(default_factory=EnvConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    open: OpenConfig = Field(default_factory=OpenConfig)
    opencode: OpenCodeConfig = Field(default_factory=OpenCodeConfig)
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    containers: ContainerConfig = Field(default_factory=ContainerConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
