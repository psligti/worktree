from __future__ import annotations

import subprocess
from pathlib import Path

from ..config.models import WtConfig
from ..domain.models import WorktreeRecord
from .ports import allocate_ports
from .templates import apply_templates


class BootstrapError(RuntimeError):
    pass


def bootstrap_worktree(repo_root: str, worktree: WorktreeRecord, config: WtConfig) -> None:
    worktree_path = str(worktree.path)
    apply_templates(repo_root, worktree_path, config)

    if config.env.unique_ports:
        ports = allocate_ports(repo_root, worktree.id, config.env.port_keys)
        _ensure_env_ports(Path(worktree_path) / config.env.dotenv_file, ports)

    if config.env.kind == "uv":
        _ensure_uv_env(worktree_path, config)
    elif config.env.kind:
        raise BootstrapError(f"unsupported env kind: {config.env.kind}")


def _ensure_uv_env(worktree_path: str, config: WtConfig) -> None:
    venv_path = Path(worktree_path) / config.env.venv_dir
    if not venv_path.exists():
        _run(["uv", "venv", str(venv_path)], cwd=worktree_path)

    _run(["uv", "sync"], cwd=worktree_path)


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


def _run(cmd: list[str], cwd: str) -> None:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise BootstrapError(stderr or "command failed")
