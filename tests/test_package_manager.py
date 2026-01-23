from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wt.bootstrap.package_manager import (
    PackageManagerError,
    PoetryPackageManager,
    UvPackageManager,
    detect_package_manager,
    get_package_manager,
    get_package_manager_for_worktree,
)


class TestDetectPackageManager(unittest.TestCase):
    def test_detects_poetry_from_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "poetry.lock").touch()
            self.assertEqual(detect_package_manager(path), "poetry")

    def test_detects_uv_from_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "uv.lock").touch()
            self.assertEqual(detect_package_manager(path), "uv")

    def test_detects_poetry_from_pyproject_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n")
            self.assertEqual(detect_package_manager(path), "poetry")

    def test_defaults_to_uv_when_no_indicators(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            self.assertEqual(detect_package_manager(path), "uv")

    def test_defaults_to_uv_with_generic_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
            self.assertEqual(detect_package_manager(path), "uv")

    def test_poetry_lock_takes_precedence_over_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "poetry.lock").touch()
            (path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
            self.assertEqual(detect_package_manager(path), "poetry")

    def test_uv_lock_takes_precedence_over_poetry_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "uv.lock").touch()
            (path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n")
            self.assertEqual(detect_package_manager(path), "uv")


class TestGetPackageManager(unittest.TestCase):
    def test_returns_uv_manager(self) -> None:
        pm = get_package_manager("uv")
        self.assertIsInstance(pm, UvPackageManager)
        self.assertEqual(pm.name, "uv")

    def test_returns_poetry_manager(self) -> None:
        pm = get_package_manager("poetry")
        self.assertIsInstance(pm, PoetryPackageManager)
        self.assertEqual(pm.name, "poetry")


class TestGetPackageManagerForWorktree(unittest.TestCase):
    def test_explicit_uv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            pm = get_package_manager_for_worktree(path, "uv")
            self.assertIsInstance(pm, UvPackageManager)

    def test_explicit_poetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            pm = get_package_manager_for_worktree(path, "poetry")
            self.assertIsInstance(pm, PoetryPackageManager)

    def test_auto_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "poetry.lock").touch()
            pm = get_package_manager_for_worktree(path, "auto")
            self.assertIsInstance(pm, PoetryPackageManager)

    def test_none_triggers_auto_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "uv.lock").touch()
            pm = get_package_manager_for_worktree(path, None)
            self.assertIsInstance(pm, UvPackageManager)


class TestUvPackageManager(unittest.TestCase):
    @patch("wt.bootstrap.package_manager._run")
    def test_create_venv_when_not_exists(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            pm = UvPackageManager()
            pm.create_venv(path, ".venv")
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[0], "uv")
            self.assertEqual(call_args[1], "venv")

    @patch("wt.bootstrap.package_manager._run")
    def test_create_venv_skips_when_exists(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / ".venv").mkdir()
            pm = UvPackageManager()
            pm.create_venv(path, ".venv")
            mock_run.assert_not_called()

    @patch("wt.bootstrap.package_manager._run")
    def test_sync(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            pm = UvPackageManager()
            pm.sync(path)
            mock_run.assert_called_once_with(["uv", "sync"], cwd=str(path))


class TestPoetryPackageManager(unittest.TestCase):
    @patch("wt.bootstrap.package_manager._run")
    def test_create_venv_configures_in_project(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            pm = PoetryPackageManager()
            pm.create_venv(path, ".venv")
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[0], "poetry")
            self.assertEqual(call_args[1], "config")
            self.assertIn("virtualenvs.in-project", call_args)

    @patch("wt.bootstrap.package_manager._run")
    def test_sync(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            pm = PoetryPackageManager()
            pm.sync(path)
            mock_run.assert_called_once_with(["poetry", "install"], cwd=str(path))


if __name__ == "__main__":
    unittest.main()
