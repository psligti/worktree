from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from ..config.models import ServiceDefinition, WtConfig
from ..domain.models import ServiceRecord, WorktreeRecord
from ..persistence import repos
from ..persistence.db import connect
from ..tmux import adapter as tmux


class ServiceError(RuntimeError):
    pass


class ServiceManager:
    def __init__(self, repo_root: str, config: WtConfig):
        self.repo_root = repo_root
        self.config = config

    def start(
        self,
        worktree: WorktreeRecord,
        service_name: Optional[str] = None,
        window_id: Optional[str] = None,
    ) -> list[str]:
        started: list[str] = []
        definitions = self._get_definitions(service_name)

        for name, definition in self._sort_by_dependencies(definitions):
            existing = repos.get_service(self.repo_root, worktree.id, name)
            if existing and existing.status == "running":
                continue

            pane_id = self._start_service_in_pane(worktree, definition, window_id)
            self._record_service_start(worktree.id, name, pane_id)
            started.append(name)

        return started

    def stop(
        self,
        worktree: WorktreeRecord,
        service_name: Optional[str] = None,
    ) -> list[str]:
        stopped: list[str] = []
        services = repos.list_services(self.repo_root, worktree.id)

        for service in services:
            if service_name and service.name != service_name:
                continue
            if service.status != "running":
                continue
            if service.pane_id:
                tmux.send_signal(service.pane_id, "C-c")
            repos.update_service_status(
                self.repo_root, worktree.id, service.name, "stopped"
            )
            stopped.append(service.name)

        return stopped

    def restart(
        self,
        worktree: WorktreeRecord,
        service_name: str,
        window_id: Optional[str] = None,
    ) -> None:
        self.stop(worktree, service_name)
        self.start(worktree, service_name, window_id)

    def status(self, worktree: WorktreeRecord) -> list[ServiceRecord]:
        return repos.list_services(self.repo_root, worktree.id)

    def logs(
        self, worktree: WorktreeRecord, service_name: str, lines: int = 50
    ) -> list[str]:
        service = repos.get_service(self.repo_root, worktree.id, service_name)
        if not service or not service.pane_id:
            return []
        try:
            return tmux.capture_pane(service.pane_id, lines)
        except tmux.TmuxError:
            return []

    def ensure_service_records(self, worktree: WorktreeRecord) -> None:
        for name, definition in self.config.services.definitions.items():
            existing = repos.get_service(self.repo_root, worktree.id, name)
            if not existing:
                record = ServiceRecord(
                    id=str(uuid.uuid4()),
                    worktree_id=worktree.id,
                    name=name,
                )
                repos.upsert_service(self.repo_root, record)

    def _get_definitions(
        self, service_name: Optional[str]
    ) -> dict[str, ServiceDefinition]:
        if service_name:
            if service_name not in self.config.services.definitions:
                raise ServiceError(f"service not found: {service_name}")
            return {service_name: self.config.services.definitions[service_name]}
        return dict(self.config.services.definitions)

    def _sort_by_dependencies(
        self, definitions: dict[str, ServiceDefinition]
    ) -> list[tuple[str, ServiceDefinition]]:
        result: list[tuple[str, ServiceDefinition]] = []
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            definition = definitions.get(name)
            if not definition:
                return
            for dep in definition.depends_on:
                if dep in definitions:
                    visit(dep)
            result.append((name, definition))

        for name in definitions:
            visit(name)

        return result

    def _start_service_in_pane(
        self,
        worktree: WorktreeRecord,
        definition: ServiceDefinition,
        window_id: Optional[str],
    ) -> str:
        worktree_path = str(worktree.path)
        pane_title = f"{worktree.name}:{definition.name}"

        if window_id:
            existing_pane = tmux.find_pane_by_title(window_id, definition.name)
            if existing_pane:
                pane_id = existing_pane
            else:
                pane_id = tmux.split_window(window_id, worktree_path, pane_title)
        else:
            session = self._get_session_name()
            tmux.ensure_session(session)
            win_id, _ = tmux.open_or_attach_window(
                session, worktree.name, worktree_path
            )
            pane_id = tmux.split_window(win_id, worktree_path, pane_title)

        command = self._expand_command(definition.command, worktree)
        tmux.send_keys(pane_id, command)

        return pane_id

    def _expand_command(self, command: str, worktree: WorktreeRecord) -> str:
        env_path = Path(worktree.path) / self.config.env.dotenv_file
        env_vars = self._load_env_file(env_path)

        result = command
        for key, value in env_vars.items():
            result = result.replace(f"${key}", value)
            result = result.replace(f"${{{key}}}", value)

        return result

    def _load_env_file(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        env: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
        return env

    def _record_service_start(self, worktree_id: str, name: str, pane_id: str) -> None:
        existing = repos.get_service(self.repo_root, worktree_id, name)
        if not existing:
            record = ServiceRecord(
                id=str(uuid.uuid4()),
                worktree_id=worktree_id,
                name=name,
                pane_id=pane_id,
                status="running",
            )
            repos.upsert_service(self.repo_root, record)
        else:
            repos.update_service_status(
                self.repo_root, worktree_id, name, "running", pane_id=pane_id
            )

    def _get_session_name(self) -> str:
        session = self.config.tmux.session
        if session == "repo":
            return os.path.basename(self.repo_root)
        return session
