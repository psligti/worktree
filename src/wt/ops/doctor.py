from __future__ import annotations

from pathlib import Path

from ..config.models import WtConfig
from ..persistence import repos


def doctor(repo_root: str, config: WtConfig) -> list[str]:
    issues: list[str] = []
    for record in repos.list_worktrees(repo_root):
        path = Path(record.path)
        if not path.exists():
            issues.append(f"{record.name}: missing path")
            continue
        venv_path = path / config.env.venv_dir
        if config.env.kind and not venv_path.exists():
            issues.append(f"{record.name}: missing venv")
        if record.upstream is None:
            issues.append(f"{record.name}: no upstream")
    return issues
