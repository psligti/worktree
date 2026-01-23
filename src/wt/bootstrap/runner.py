from __future__ import annotations

from pathlib import Path

from ..config.models import WtConfig
from ..domain.models import WorktreeRecord
from .package_manager import PackageManagerError, get_package_manager_for_worktree
from .ports import allocate_ports
from .templates import apply_templates


class BootstrapError(RuntimeError):
    pass


def bootstrap_worktree(
    repo_root: str, worktree: WorktreeRecord, config: WtConfig
) -> None:
    worktree_path = Path(worktree.path)
    apply_templates(repo_root, str(worktree_path), config)

    if config.env.unique_ports:
        ports = allocate_ports(repo_root, worktree.id, config.env.port_keys)
        _ensure_env_ports(worktree_path / config.env.dotenv_file, ports)

    try:
        pm = get_package_manager_for_worktree(worktree_path, config.env.kind)
        pm.create_venv(worktree_path, config.env.venv_dir)
        pm.sync(worktree_path)
    except PackageManagerError as exc:
        raise BootstrapError(str(exc)) from exc


def _ensure_env_ports(dotenv_path: Path, ports: dict[str, int]) -> None:
    lines: list[str] = []
    existing_keys: set[str] = set()

    if dotenv_path.exists():
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if "=" in line:
                key = line.split("=", 1)[0].strip()
                if key:
                    existing_keys.add(key)

    for key, port in ports.items():
        if key in existing_keys:
            continue
        lines.append(f"{key}={port}")

    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
