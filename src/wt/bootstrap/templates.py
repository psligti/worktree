from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..config.models import WtConfig


def apply_templates(repo_root: str, worktree_path: str, config: WtConfig) -> int:
    """Apply templates to a newly created worktree.

    Args:
        repo_root: Path to the repository root.
        worktree_path: Path to the worktree directory.
        config: Worktree configuration.

    Returns:
        Number of skills installed to the worktree.
    """
    templates_root = Path(repo_root) / ".wt" / "templates"
    target_root = Path(worktree_path)

    _copy_if_missing(
        templates_root / "env" / ".env.base", target_root / config.env.dotenv_file
    )
    _copy_if_missing(
        templates_root / "worktree" / config.env.direnv_file,
        target_root / config.env.direnv_file,
    )

    if config.agent.enabled:
        agent_root = target_root / config.agent.root_dir
        agent_root.mkdir(parents=True, exist_ok=True)
        _copy_if_missing(
            templates_root / "agent" / "context.md", agent_root / "context.md"
        )
        _copy_if_missing(
            templates_root / "agent" / "runbook.md", agent_root / "runbook.md"
        )

    apply_opencode_config(repo_root, worktree_path, config)

    return _apply_skills(templates_root, target_root)


def apply_opencode_config(repo_root: str, worktree_path: str, config: WtConfig) -> bool:
    return _apply_opencode_config(repo_root, Path(worktree_path), config)


def _apply_opencode_config(repo_root: str, target_root: Path, config: WtConfig) -> bool:
    if not config.opencode.enabled:
        return False
    connection = config.opencode.connection
    if connection is None or connection == "":
        return False
    themes = config.opencode.themes.for_connection(connection)
    if not themes:
        return False
    config_path = target_root / config.opencode.config_path
    if config_path.exists():
        return False
    theme = _next_opencode_theme(repo_root, connection, themes)
    template_path = (
        Path(repo_root) / ".wt" / "templates" / "opencode" / f"{connection}.json"
    )
    config_data = _load_opencode_template(template_path)
    config_data["theme"] = theme
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return True


def _load_opencode_template(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return dict(data)


def _next_opencode_theme(repo_root: str, connection: str, themes: list[str]) -> str:
    state_path = Path(repo_root) / ".wt" / "cache" / "opencode_theme_state.json"
    state = _load_theme_state(state_path)
    index = state.get(connection, 0)
    if not isinstance(index, int):
        index = 0
    theme = themes[index % len(themes)]
    state[connection] = index + 1
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return theme


def _load_theme_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    state: dict[str, int] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, int):
            state[key] = value
    return state


def _copy_if_missing(src: Path, dst: Path) -> None:
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _apply_skills(templates_root: Path, target_root: Path) -> int:
    skills_installed = 0
    source_skills = templates_root / "skills"
    target_skills = target_root / ".opencode" / "skills"

    if not source_skills.exists():
        return skills_installed

    target_skills.mkdir(parents=True, exist_ok=True)

    for skill_dir in source_skills.iterdir():
        if not skill_dir.is_dir():
            continue

        dest_dir = target_skills / skill_dir.name

        if dest_dir.exists():
            continue

        try:
            shutil.copytree(skill_dir, dest_dir)
            skills_installed += 1
        except OSError:
            continue

    return skills_installed
