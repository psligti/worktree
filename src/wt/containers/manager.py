from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config.models import ContainerDefinition, WtConfig
from ..domain.models import ContainerRecord, WorktreeRecord
from ..persistence import repos
from .adapters import ContainerAdapter, ContainerInfo, get_adapter


class ContainerError(RuntimeError):
    pass


class ContainerManager:
    def __init__(self, repo_root: str, config: WtConfig):
        self.repo_root = repo_root
        self.config = config
        self._adapter: Optional[ContainerAdapter] = None

    @property
    def adapter(self) -> ContainerAdapter:
        if self._adapter is None:
            self._adapter = get_adapter(self.config.containers.runtime)
        return self._adapter

    def container_name(self, worktree: WorktreeRecord, service: str) -> str:
        prefix = self.config.containers.project_prefix
        wt_name = worktree.name.replace("/", "-").replace("_", "-")
        return f"{prefix}-{wt_name}-{service}"

    def network_name(self, worktree: WorktreeRecord) -> str:
        prefix = self.config.containers.project_prefix
        wt_name = worktree.name.replace("/", "-").replace("_", "-")
        return f"{prefix}-{wt_name}-net"

    def _get_definitions(
        self, service_name: Optional[str]
    ) -> dict[str, ContainerDefinition]:
        definitions = self.config.containers.definitions
        if service_name is None:
            return dict(definitions)
        if service_name not in definitions:
            raise ContainerError(f"container definition not found: {service_name}")
        return {service_name: definitions[service_name]}

    def _sort_by_dependencies(
        self, definitions: dict[str, ContainerDefinition]
    ) -> list[tuple[str, ContainerDefinition]]:
        result: list[tuple[str, ContainerDefinition]] = []
        added: set[str] = set()

        def add_with_deps(name: str, defn: ContainerDefinition) -> None:
            if name in added:
                return
            for dep in defn.depends_on:
                if dep in definitions and dep not in added:
                    add_with_deps(dep, definitions[dep])
            result.append((name, defn))
            added.add(name)

        for name, defn in definitions.items():
            add_with_deps(name, defn)

        return result

    def _expand_env_vars(
        self, env: dict[str, str], worktree: WorktreeRecord
    ) -> dict[str, str]:
        dotenv_path = worktree.path / ".env"
        wt_env = self._load_env_file(dotenv_path)
        result = {}
        for key, value in env.items():
            expanded = value
            for env_key, env_val in wt_env.items():
                expanded = expanded.replace(f"${env_key}", env_val)
                expanded = expanded.replace(f"${{{env_key}}}", env_val)
            result[key] = expanded
        return result

    def _load_env_file(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        result = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
        return result

    def _expand_volumes(
        self, volumes: dict[str, str], worktree: WorktreeRecord
    ) -> dict[str, str]:
        result = {}
        for host_path, container_path in volumes.items():
            expanded = host_path.replace("$WORKTREE", str(worktree.path))
            expanded = expanded.replace("${WORKTREE}", str(worktree.path))
            if not expanded.startswith("/"):
                expanded = str(worktree.path / expanded)
            result[expanded] = container_path
        return result

    def ensure_network(self, worktree: WorktreeRecord) -> str:
        network = self.network_name(worktree)
        if not self.adapter.network_exists(network):
            self.adapter.network_create(network)
        return network

    def start(
        self,
        worktree: WorktreeRecord,
        service_name: Optional[str] = None,
    ) -> list[str]:
        definitions = self._get_definitions(service_name)
        sorted_defs = self._sort_by_dependencies(definitions)
        network = self.ensure_network(worktree)

        started: list[str] = []
        for name, defn in sorted_defs:
            container_name = self.container_name(worktree, name)

            if self.adapter.is_running(container_name):
                continue

            if self.adapter.exists(container_name):
                self.adapter.rm(container_name, force=True)

            env = self._expand_env_vars(defn.environment, worktree)
            volumes = self._expand_volumes(defn.volumes, worktree)

            container_id = self.adapter.run(
                name=container_name,
                image=defn.image,
                command=defn.command,
                ports=defn.ports or {},
                volumes=volumes,
                environment=env,
                network=defn.network or network,
            )

            record = ContainerRecord(
                id=str(uuid.uuid4()),
                worktree_id=worktree.id,
                name=name,
                container_id=container_id,
                container_name=container_name,
                image=defn.image,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            repos.upsert_container(self.repo_root, record)
            started.append(name)

        return started

    def stop(
        self,
        worktree: WorktreeRecord,
        service_name: Optional[str] = None,
    ) -> list[str]:
        definitions = self._get_definitions(service_name)
        stopped: list[str] = []

        for name in definitions:
            container_name = self.container_name(worktree, name)
            if self.adapter.is_running(container_name):
                self.adapter.stop(container_name)
                repos.update_container_status(
                    self.repo_root, worktree.id, name, "stopped"
                )
                stopped.append(name)

        return stopped

    def rm(
        self,
        worktree: WorktreeRecord,
        service_name: Optional[str] = None,
        force: bool = False,
    ) -> list[str]:
        definitions = self._get_definitions(service_name)
        removed: list[str] = []

        for name in definitions:
            container_name = self.container_name(worktree, name)
            if self.adapter.exists(container_name):
                self.adapter.rm(container_name, force=force)
                repos.delete_container(self.repo_root, worktree.id, name)
                removed.append(name)

        return removed

    def status(self, worktree: WorktreeRecord) -> list[ContainerRecord]:
        return repos.list_containers(self.repo_root, worktree.id)

    def ps(self, worktree: WorktreeRecord) -> list[ContainerInfo]:
        prefix = (
            f"{self.config.containers.project_prefix}-{worktree.name.replace('/', '-')}"
        )
        return self.adapter.ps(name_filter=prefix, all_containers=True)

    def logs(
        self,
        worktree: WorktreeRecord,
        service_name: str,
        tail: int = 100,
    ) -> list[str]:
        container_name = self.container_name(worktree, service_name)
        if not self.adapter.exists(container_name):
            return []
        return self.adapter.logs(container_name, tail=tail)

    def exec(
        self,
        worktree: WorktreeRecord,
        service_name: str,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        container_name = self.container_name(worktree, service_name)
        if not self.adapter.is_running(container_name):
            raise ContainerError(f"container not running: {container_name}")
        return self.adapter.exec(container_name, command)

    def cleanup(self, worktree: WorktreeRecord) -> None:
        self.rm(worktree, force=True)
        network = self.network_name(worktree)
        if self.adapter.network_exists(network):
            self.adapter.network_rm(network)
