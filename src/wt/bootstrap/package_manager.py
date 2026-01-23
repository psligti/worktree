from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal, Optional

PackageManagerKind = Literal["uv", "poetry"]


class PackageManagerError(RuntimeError):
    """Raised when a package manager operation fails."""

    pass


class PackageManager(ABC):
    """Abstract base class for package manager implementations."""

    @property
    @abstractmethod
    def name(self) -> PackageManagerKind:
        """Return the package manager name."""
        ...

    @abstractmethod
    def create_venv(self, worktree_path: Path, venv_dir: str) -> None:
        """Create a virtual environment in the worktree."""
        ...

    @abstractmethod
    def sync(self, worktree_path: Path) -> None:
        """Sync/install dependencies."""
        ...

    @abstractmethod
    def run(self, worktree_path: Path, script: str) -> subprocess.CompletedProcess[str]:
        """Run a script/command through the package manager."""
        ...


class UvPackageManager(PackageManager):
    """UV package manager implementation."""

    @property
    def name(self) -> PackageManagerKind:
        return "uv"

    def create_venv(self, worktree_path: Path, venv_dir: str) -> None:
        venv_path = worktree_path / venv_dir
        if not venv_path.exists():
            _run(["uv", "venv", str(venv_path)], cwd=str(worktree_path))

    def sync(self, worktree_path: Path) -> None:
        _run(["uv", "sync"], cwd=str(worktree_path))

    def run(self, worktree_path: Path, script: str) -> subprocess.CompletedProcess[str]:
        return _run(["uv", "run", script], cwd=str(worktree_path), check=False)


class PoetryPackageManager(PackageManager):
    """Poetry package manager implementation."""

    @property
    def name(self) -> PackageManagerKind:
        return "poetry"

    def create_venv(self, worktree_path: Path, venv_dir: str) -> None:
        _run(
            ["poetry", "config", "virtualenvs.in-project", "true", "--local"],
            cwd=str(worktree_path),
        )

    def sync(self, worktree_path: Path) -> None:
        _run(["poetry", "install"], cwd=str(worktree_path))

    def run(self, worktree_path: Path, script: str) -> subprocess.CompletedProcess[str]:
        return _run(["poetry", "run", script], cwd=str(worktree_path), check=False)


def detect_package_manager(worktree_path: Path) -> PackageManagerKind:
    """
    Auto-detect the package manager from project files.

    Detection order:
    1. poetry.lock -> poetry
    2. uv.lock -> uv
    3. pyproject.toml with [tool.poetry] -> poetry
    4. Default to uv
    """
    if (worktree_path / "poetry.lock").exists():
        return "poetry"
    if (worktree_path / "uv.lock").exists():
        return "uv"

    pyproject = worktree_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            if "[tool.poetry]" in content:
                return "poetry"
        except OSError:
            pass

    return "uv"


def get_package_manager(kind: PackageManagerKind) -> PackageManager:
    """Get a package manager instance by name."""
    if kind == "poetry":
        return PoetryPackageManager()
    return UvPackageManager()


def get_package_manager_for_worktree(
    worktree_path: Path, kind: Optional[Literal["uv", "poetry", "auto"]] = None
) -> PackageManager:
    """
    Get the appropriate package manager for a worktree.

    If kind is "auto" or None, auto-detect from project files.
    """
    if kind is None or kind == "auto":
        detected = detect_package_manager(worktree_path)
        return get_package_manager(detected)
    return get_package_manager(kind)


def _run(
    cmd: list[str], cwd: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a command and handle errors."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        stdout = result.stdout.strip() if result.stdout else ""
        message = stderr or stdout or f"command failed: {' '.join(cmd)}"
        raise PackageManagerError(message)
    return result
