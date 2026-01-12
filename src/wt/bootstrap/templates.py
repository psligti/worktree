from __future__ import annotations

import shutil
from pathlib import Path

from ..config.models import WtConfig


def apply_templates(repo_root: str, worktree_path: str, config: WtConfig) -> None:
    templates_root = Path(repo_root) / ".wt" / "templates"
    target_root = Path(worktree_path)

    _copy_if_missing(templates_root / "env" / ".env.base", target_root / config.env.dotenv_file)
    _copy_if_missing(templates_root / "worktree" / config.env.direnv_file, target_root / config.env.direnv_file)

    if config.agent.enabled:
        agent_root = target_root / config.agent.root_dir
        agent_root.mkdir(parents=True, exist_ok=True)
        _copy_if_missing(templates_root / "agent" / "context.md", agent_root / "context.md")
        _copy_if_missing(templates_root / "agent" / "runbook.md", agent_root / "runbook.md")


def _copy_if_missing(src: Path, dst: Path) -> None:
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
