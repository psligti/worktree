from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from ..config.models import WtConfig
from ..domain.models import WorktreeRecord
from .adapters import (
    EncryptedFileAdapter,
    EnvFileAdapter,
    KeyringAdapter,
    SecretsAdapter,
)


class SecretsError(RuntimeError):
    pass


BackendType = Literal["env", "keyring", "encrypted"]


class SecretsManager:
    def __init__(self, repo_root: str, config: WtConfig):
        self.repo_root = repo_root
        self.config = config

    def get_adapter(self, worktree: WorktreeRecord) -> SecretsAdapter:
        backend = self.config.secrets.backend

        if backend == "env":
            env_file = worktree.path / self.config.secrets.env_file
            return EnvFileAdapter(env_file)
        elif backend == "encrypted":
            encrypted_file = Path(self.repo_root) / self.config.secrets.encrypted_file
            key_file = Path(self.repo_root) / self.config.secrets.key_file
            return EncryptedFileAdapter(encrypted_file, key_file)
        elif backend == "keyring":
            service_name = f"wt-{worktree.name}"
            return KeyringAdapter(service_name)
        else:
            raise SecretsError(f"unsupported secrets backend: {backend}")

    def get(self, worktree: WorktreeRecord, key: str) -> Optional[str]:
        adapter = self.get_adapter(worktree)
        return adapter.get(key)

    def set(self, worktree: WorktreeRecord, key: str, value: str) -> None:
        adapter = self.get_adapter(worktree)
        adapter.set(key, value)

    def delete(self, worktree: WorktreeRecord, key: str) -> None:
        adapter = self.get_adapter(worktree)
        adapter.delete(key)

    def list_keys(self, worktree: WorktreeRecord) -> list[str]:
        adapter = self.get_adapter(worktree)
        return adapter.list_keys()

    def exists(self, worktree: WorktreeRecord, key: str) -> bool:
        adapter = self.get_adapter(worktree)
        return adapter.exists(key)

    def sync_to_env(self, worktree: WorktreeRecord) -> int:
        """Sync secrets to worktree .env file. Returns count of secrets synced."""
        adapter = self.get_adapter(worktree)
        keys = adapter.list_keys()

        if not keys:
            return 0

        dotenv_path = worktree.path / self.config.env.dotenv_file
        existing = self._load_env_file(dotenv_path)

        synced = 0
        for key in keys:
            value = adapter.get(key)
            if value is not None:
                existing[key] = value
                synced += 1

        self._save_env_file(dotenv_path, existing)
        return synced

    def check_required(self, worktree: WorktreeRecord) -> list[str]:
        """Check for missing required keys. Returns list of missing keys."""
        required = self.config.secrets.required_keys
        if not required:
            return []

        adapter = self.get_adapter(worktree)
        missing = []
        for key in required:
            if not adapter.exists(key):
                missing.append(key)

        return missing

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

    def _save_env_file(self, path: Path, secrets: dict[str, str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{key}={value}" for key, value in sorted(secrets.items())]
        path.write_text("\n".join(lines) + "\n" if lines else "")
