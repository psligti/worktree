from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TypedDict

from ..config.models import WtConfig
from ..persistence import repos


def resolve_global_skills_path() -> Path:
    """Resolve the global skills installation path.

    Uses XDG_CONFIG_HOME with fallback to ~/.config/opencode.

    Returns:
        Path to the global skills directory.
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "opencode" / "skills"
    return Path.home() / ".config" / "opencode" / "skills"


class LocalTargets(TypedDict):
    """Typed dictionary for local installation targets."""

    templates: Path
    worktrees: list[Path]


def resolve_local_targets(repo_root: str, config: WtConfig) -> LocalTargets:
    """Resolve local targets for skills installation.

    Args:
        repo_root: Path to the repository root.
        config: Worktree configuration.

    Returns:
        Dictionary with 'templates' key containing Path to .wt/templates/skills/
        and 'worktrees' key containing list of worktree paths.
    """
    repo_path = Path(repo_root)
    templates_path = repo_path / ".wt" / "templates" / "skills"

    worktree_records = repos.list_worktrees(repo_root)
    worktree_paths = [Path(record.path) for record in worktree_records]

    return LocalTargets(templates=templates_path, worktrees=worktree_paths)


def install_skills(
    repo_root: str,
    config: WtConfig,
    global_only: bool = False,
    local_only: bool = False,
    force: bool = False,
) -> dict[str, int]:
    """Install skills to global and local targets.

    Args:
        repo_root: Path to the repository root.
        config: Worktree configuration.
        global_only: If True, only install to global path.
        local_only: If True, only install to local targets.
        force: If True, overwrite existing files.

    Returns:
        Dictionary with counts: {'created': n, 'skipped': n, 'overwritten': n, 'errors': n}
    """
    results = {"created": 0, "skipped": 0, "overwritten": 0, "errors": 0}

    source_path = Path(repo_root) / ".wt" / "templates" / "skills"
    if not source_path.exists():
        return results

    if not local_only:
        _install_to_target(source_path, resolve_global_skills_path(), force, results)

    if not global_only:
        targets = resolve_local_targets(repo_root, config)

        _install_to_target(source_path, targets["templates"], force, results)

        for worktree_path in targets["worktrees"]:
            target_path = worktree_path / ".wt" / "templates" / "skills"
            _install_to_target(source_path, target_path, force, results)

    return results


def _install_to_target(
    source: Path, target: Path, force: bool, results: dict[str, int]
) -> None:
    """Install skills from source to target directory.

    Args:
        source: Source skills directory.
        target: Target directory.
        force: If True, overwrite existing files.
        results: Dictionary to update with counts.
    """
    if not source.exists():
        return

    target.mkdir(parents=True, exist_ok=True)

    for skill_dir in source.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_name = skill_dir.name
        dest_dir = target / skill_name

        if dest_dir.exists():
            if not force:
                results["skipped"] += 1
                continue

            try:
                shutil.rmtree(dest_dir)
                results["overwritten"] += 1
            except OSError:
                results["errors"] += 1
                continue

        try:
            shutil.copytree(skill_dir, dest_dir)
            results["created"] += 1
        except OSError:
            results["errors"] += 1
