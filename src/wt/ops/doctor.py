from __future__ import annotations

from pathlib import Path

from ..bootstrap.templates import apply_opencode_config
from ..config.models import WtConfig
from ..persistence import repos


def doctor(repo_root: str, config: WtConfig) -> list[str]:
    issues: list[str] = []
    issues.extend(_opencode_issues(repo_root, config))
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


def repair_opencode(repo_root: str, config: WtConfig) -> int:
    if not config.opencode.enabled:
        return 0
    if not config.opencode.connection:
        return 0
    themes = config.opencode.themes.for_connection(config.opencode.connection)
    if not themes:
        return 0
    updated = 0
    for record in repos.list_worktrees(repo_root):
        path = Path(record.path)
        if not path.exists():
            continue
        if apply_opencode_config(repo_root, str(path), config):
            updated += 1
    return updated


def _opencode_issues(repo_root: str, config: WtConfig) -> list[str]:
    if not config.opencode.enabled:
        return []
    if not config.opencode.connection:
        return ["opencode: connection not set in .wt/config/wt.toml"]
    themes = config.opencode.themes.for_connection(config.opencode.connection)
    if not themes:
        return [f"opencode: no themes configured for {config.opencode.connection}"]
    template_path = (
        Path(repo_root)
        / ".wt"
        / "templates"
        / "opencode"
        / f"{config.opencode.connection}.json"
    )
    if not template_path.exists():
        return [f"opencode: missing template {template_path}"]
    return []
