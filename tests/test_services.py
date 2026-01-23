from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wt.config.models import ServiceDefinition, ServicesConfig, WtConfig
from wt.domain.models import ServiceRecord, WorktreeRecord
from wt.services.manager import ServiceError, ServiceManager


def _make_worktree(path: Path, name: str = "test-wt") -> WorktreeRecord:
    return WorktreeRecord(
        id="wt-123",
        name=name,
        path=path,
        branch="wt/test",
    )


def _make_config_with_services(services: dict[str, ServiceDefinition]) -> WtConfig:
    return WtConfig(
        services=ServicesConfig(definitions=services),
    )


class TestServiceManagerGetDefinitions(unittest.TestCase):
    def test_returns_all_definitions_when_no_name(self) -> None:
        svc1 = ServiceDefinition(name="api", command="python api.py")
        svc2 = ServiceDefinition(name="worker", command="python worker.py")
        config = _make_config_with_services({"api": svc1, "worker": svc2})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            result = manager._get_definitions(None)
            self.assertEqual(len(result), 2)
            self.assertIn("api", result)
            self.assertIn("worker", result)

    def test_returns_single_definition_when_name_provided(self) -> None:
        svc1 = ServiceDefinition(name="api", command="python api.py")
        svc2 = ServiceDefinition(name="worker", command="python worker.py")
        config = _make_config_with_services({"api": svc1, "worker": svc2})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            result = manager._get_definitions("api")
            self.assertEqual(len(result), 1)
            self.assertIn("api", result)

    def test_raises_error_for_unknown_service(self) -> None:
        svc1 = ServiceDefinition(name="api", command="python api.py")
        config = _make_config_with_services({"api": svc1})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            with self.assertRaises(ServiceError) as ctx:
                manager._get_definitions("unknown")
            self.assertIn("not found", str(ctx.exception))


class TestServiceManagerDependencySort(unittest.TestCase):
    def test_sorts_by_dependencies(self) -> None:
        db = ServiceDefinition(name="db", command="pg_start")
        api = ServiceDefinition(name="api", command="python api.py", depends_on=["db"])
        config = _make_config_with_services({"api": api, "db": db})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            definitions = {"api": api, "db": db}
            sorted_list = manager._sort_by_dependencies(definitions)
            names = [name for name, _ in sorted_list]
            self.assertEqual(names.index("db"), 0)
            self.assertGreater(names.index("api"), names.index("db"))

    def test_handles_no_dependencies(self) -> None:
        svc1 = ServiceDefinition(name="api", command="python api.py")
        svc2 = ServiceDefinition(name="worker", command="python worker.py")
        config = _make_config_with_services({"api": svc1, "worker": svc2})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            definitions = {"api": svc1, "worker": svc2}
            sorted_list = manager._sort_by_dependencies(definitions)
            self.assertEqual(len(sorted_list), 2)

    def test_handles_missing_dependency(self) -> None:
        api = ServiceDefinition(
            name="api", command="python api.py", depends_on=["missing"]
        )
        config = _make_config_with_services({"api": api})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            definitions = {"api": api}
            sorted_list = manager._sort_by_dependencies(definitions)
            self.assertEqual(len(sorted_list), 1)


class TestServiceManagerExpandCommand(unittest.TestCase):
    def test_expands_env_vars_dollar_syntax(self) -> None:
        svc = ServiceDefinition(name="api", command="python api.py --port=$APP_PORT")
        config = _make_config_with_services({"api": svc})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / ".env").write_text("APP_PORT=3000\n")
            manager = ServiceManager(tmpdir, config)
            worktree = _make_worktree(path)
            result = manager._expand_command(svc.command, worktree)
            self.assertEqual(result, "python api.py --port=3000")

    def test_expands_env_vars_brace_syntax(self) -> None:
        svc = ServiceDefinition(name="api", command="python api.py --port=${APP_PORT}")
        config = _make_config_with_services({"api": svc})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / ".env").write_text("APP_PORT=4000\n")
            manager = ServiceManager(tmpdir, config)
            worktree = _make_worktree(path)
            result = manager._expand_command(svc.command, worktree)
            self.assertEqual(result, "python api.py --port=4000")

    def test_leaves_unmatched_vars_unchanged(self) -> None:
        svc = ServiceDefinition(name="api", command="python api.py --port=$UNKNOWN")
        config = _make_config_with_services({"api": svc})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            manager = ServiceManager(tmpdir, config)
            worktree = _make_worktree(path)
            result = manager._expand_command(svc.command, worktree)
            self.assertEqual(result, "python api.py --port=$UNKNOWN")


class TestServiceManagerLoadEnvFile(unittest.TestCase):
    def test_loads_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text("FOO=bar\nBAZ=qux\n")
            config = WtConfig()
            manager = ServiceManager(tmpdir, config)
            result = manager._load_env_file(path)
            self.assertEqual(result, {"FOO": "bar", "BAZ": "qux"})

    def test_skips_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text("# comment\n\nFOO=bar\n  \n")
            config = WtConfig()
            manager = ServiceManager(tmpdir, config)
            result = manager._load_env_file(path)
            self.assertEqual(result, {"FOO": "bar"})

    def test_returns_empty_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            config = WtConfig()
            manager = ServiceManager(tmpdir, config)
            result = manager._load_env_file(path)
            self.assertEqual(result, {})


class TestServiceManagerStatus(unittest.TestCase):
    @patch("wt.services.manager.repos")
    def test_returns_service_list(self, mock_repos: MagicMock) -> None:
        svc_record = ServiceRecord(
            id="svc-1", worktree_id="wt-123", name="api", status="running"
        )
        mock_repos.list_services.return_value = [svc_record]

        config = WtConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir))
            result = manager.status(worktree)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "api")
            mock_repos.list_services.assert_called_once_with(tmpdir, "wt-123")


class TestServiceManagerLogs(unittest.TestCase):
    @patch("wt.services.manager.tmux")
    @patch("wt.services.manager.repos")
    def test_captures_pane_output(
        self, mock_repos: MagicMock, mock_tmux: MagicMock
    ) -> None:
        svc_record = ServiceRecord(
            id="svc-1", worktree_id="wt-123", name="api", status="running", pane_id="%5"
        )
        mock_repos.get_service.return_value = svc_record
        mock_tmux.capture_pane.return_value = ["line1", "line2", "line3"]

        config = WtConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir))
            result = manager.logs(worktree, "api", lines=10)
            self.assertEqual(result, ["line1", "line2", "line3"])
            mock_tmux.capture_pane.assert_called_once_with("%5", 10)

    @patch("wt.services.manager.repos")
    def test_returns_empty_for_missing_service(self, mock_repos: MagicMock) -> None:
        mock_repos.get_service.return_value = None

        config = WtConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir))
            result = manager.logs(worktree, "api")
            self.assertEqual(result, [])

    @patch("wt.services.manager.repos")
    def test_returns_empty_for_no_pane(self, mock_repos: MagicMock) -> None:
        svc_record = ServiceRecord(
            id="svc-1", worktree_id="wt-123", name="api", status="stopped", pane_id=None
        )
        mock_repos.get_service.return_value = svc_record

        config = WtConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServiceManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir))
            result = manager.logs(worktree, "api")
            self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
