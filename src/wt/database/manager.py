from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from ..config.models import WtConfig
from ..domain.models import WorktreeRecord
from .adapters import DatabaseAdapter, PostgresAdapter, SqliteAdapter


class DatabaseError(RuntimeError):
    pass


DatabaseType = Literal["postgres", "sqlite"]


class DatabaseManager:
    def __init__(self, repo_root: str, config: WtConfig):
        self.repo_root = repo_root
        self.config = config
        self._adapters: dict[str, DatabaseAdapter] = {}

    def get_adapter(self, db_type: DatabaseType) -> DatabaseAdapter:
        if db_type in self._adapters:
            return self._adapters[db_type]

        if db_type == "postgres":
            db_config = self.config.database
            adapter = PostgresAdapter(
                host=db_config.postgres_host,
                port=db_config.postgres_port,
                user=db_config.postgres_user,
                password=db_config.postgres_password,
            )
        elif db_type == "sqlite":
            base_dir = Path(self.repo_root) / ".wt" / "databases"
            adapter = SqliteAdapter(base_dir)
        else:
            raise DatabaseError(f"unsupported database type: {db_type}")

        self._adapters[db_type] = adapter
        return adapter

    def db_name_for_worktree(self, worktree: WorktreeRecord, suffix: str = "") -> str:
        base = worktree.name.replace("-", "_").replace("/", "_")
        if suffix:
            return f"{base}_{suffix}"
        return base

    def create_database(
        self,
        worktree: WorktreeRecord,
        db_type: DatabaseType,
        suffix: str = "",
    ) -> str:
        adapter = self.get_adapter(db_type)
        name = self.db_name_for_worktree(worktree, suffix)

        if adapter.exists(name):
            raise DatabaseError(f"database already exists: {name}")

        adapter.create(name)
        return name

    def drop_database(
        self,
        worktree: WorktreeRecord,
        db_type: DatabaseType,
        suffix: str = "",
    ) -> None:
        adapter = self.get_adapter(db_type)
        name = self.db_name_for_worktree(worktree, suffix)
        adapter.drop(name)

    def snapshot(
        self,
        worktree: WorktreeRecord,
        db_type: DatabaseType,
        suffix: str = "",
        snapshot_name: Optional[str] = None,
    ) -> Path:
        adapter = self.get_adapter(db_type)
        name = self.db_name_for_worktree(worktree, suffix)

        snapshots_dir = Path(self.repo_root) / ".wt" / "snapshots" / worktree.name
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        if snapshot_name:
            filename = f"{snapshot_name}.sql"
        else:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.sql"

        output_path = snapshots_dir / filename
        adapter.snapshot(name, output_path)
        return output_path

    def restore(
        self,
        worktree: WorktreeRecord,
        db_type: DatabaseType,
        snapshot_path: Path,
        suffix: str = "",
    ) -> None:
        adapter = self.get_adapter(db_type)
        name = self.db_name_for_worktree(worktree, suffix)

        if not snapshot_path.exists():
            raise DatabaseError(f"snapshot not found: {snapshot_path}")

        adapter.restore(name, snapshot_path)

    def clone_database(
        self,
        source_worktree: WorktreeRecord,
        target_worktree: WorktreeRecord,
        db_type: DatabaseType,
        suffix: str = "",
    ) -> str:
        adapter = self.get_adapter(db_type)
        source_name = self.db_name_for_worktree(source_worktree, suffix)
        target_name = self.db_name_for_worktree(target_worktree, suffix)

        if not adapter.exists(source_name):
            raise DatabaseError(f"source database not found: {source_name}")

        adapter.clone(source_name, target_name)
        return target_name

    def reset_database(
        self,
        worktree: WorktreeRecord,
        db_type: DatabaseType,
        suffix: str = "",
    ) -> None:
        adapter = self.get_adapter(db_type)
        name = self.db_name_for_worktree(worktree, suffix)
        adapter.drop(name)
        adapter.create(name)

    def list_snapshots(self, worktree: WorktreeRecord) -> list[Path]:
        snapshots_dir = Path(self.repo_root) / ".wt" / "snapshots" / worktree.name
        if not snapshots_dir.exists():
            return []
        return sorted(
            snapshots_dir.glob("*.sql"), key=lambda p: p.stat().st_mtime, reverse=True
        )

    def database_exists(
        self,
        worktree: WorktreeRecord,
        db_type: DatabaseType,
        suffix: str = "",
    ) -> bool:
        adapter = self.get_adapter(db_type)
        name = self.db_name_for_worktree(worktree, suffix)
        return adapter.exists(name)
