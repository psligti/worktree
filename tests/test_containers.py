from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from wt.config.models import ContainerConfig, ContainerDefinition, WtConfig
from wt.containers.adapters import ContainerInfo, DockerAdapter
from wt.containers.manager import ContainerError, ContainerManager
from wt.domain.models import WorktreeRecord


def _make_worktree(path: Path, name: str = "test-wt") -> WorktreeRecord:
    return WorktreeRecord(
        id="wt-123",
        name=name,
        path=path,
        branch="wt/test",
    )


def _make_config_with_containers(
    containers: dict[str, ContainerDefinition], enabled: bool = True
) -> WtConfig:
    return WtConfig(
        containers=ContainerConfig(
            enabled=enabled,
            runtime="docker",
            definitions=containers,
        ),
    )


class TestContainerManagerContainerName(unittest.TestCase):
    def test_generates_prefixed_name(self) -> None:
        ctr = ContainerDefinition(name="db", image="postgres:15")
        config = _make_config_with_containers({"db": ctr})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-api")
            name = manager.container_name(worktree, "db")
            self.assertEqual(name, "wt-feat-api-db")

    def test_handles_slashes_in_worktree_name(self) -> None:
        ctr = ContainerDefinition(name="db", image="postgres:15")
        config = _make_config_with_containers({"db": ctr})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "wt/feat-api")
            name = manager.container_name(worktree, "db")
            self.assertEqual(name, "wt-wt-feat-api-db")


class TestContainerManagerNetworkName(unittest.TestCase):
    def test_generates_network_name(self) -> None:
        config = _make_config_with_containers({})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-api")
            name = manager.network_name(worktree)
            self.assertEqual(name, "wt-feat-api-net")


class TestContainerManagerGetDefinitions(unittest.TestCase):
    def test_returns_all_definitions_when_no_name(self) -> None:
        db = ContainerDefinition(name="db", image="postgres:15")
        redis = ContainerDefinition(name="redis", image="redis:7")
        config = _make_config_with_containers({"db": db, "redis": redis})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            result = manager._get_definitions(None)
            self.assertEqual(len(result), 2)
            self.assertIn("db", result)
            self.assertIn("redis", result)

    def test_returns_single_definition_when_name_provided(self) -> None:
        db = ContainerDefinition(name="db", image="postgres:15")
        redis = ContainerDefinition(name="redis", image="redis:7")
        config = _make_config_with_containers({"db": db, "redis": redis})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            result = manager._get_definitions("db")
            self.assertEqual(len(result), 1)
            self.assertIn("db", result)

    def test_raises_error_for_unknown_container(self) -> None:
        db = ContainerDefinition(name="db", image="postgres:15")
        config = _make_config_with_containers({"db": db})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            with self.assertRaises(ContainerError) as ctx:
                manager._get_definitions("unknown")
            self.assertIn("not found", str(ctx.exception))


class TestContainerManagerDependencySort(unittest.TestCase):
    def test_sorts_by_dependencies(self) -> None:
        db = ContainerDefinition(name="db", image="postgres:15")
        api = ContainerDefinition(name="api", image="app:latest", depends_on=["db"])
        config = _make_config_with_containers({"api": api, "db": db})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            definitions = {"api": api, "db": db}
            sorted_list = manager._sort_by_dependencies(definitions)
            names = [name for name, _ in sorted_list]
            self.assertEqual(names.index("db"), 0)
            self.assertGreater(names.index("api"), names.index("db"))

    def test_handles_no_dependencies(self) -> None:
        db = ContainerDefinition(name="db", image="postgres:15")
        redis = ContainerDefinition(name="redis", image="redis:7")
        config = _make_config_with_containers({"db": db, "redis": redis})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            definitions = {"db": db, "redis": redis}
            sorted_list = manager._sort_by_dependencies(definitions)
            self.assertEqual(len(sorted_list), 2)


class TestContainerManagerExpandEnvVars(unittest.TestCase):
    def test_expands_env_vars_dollar_syntax(self) -> None:
        config = _make_config_with_containers({})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / ".env").write_text("DB_HOST=localhost\n")
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(path)
            result = manager._expand_env_vars({"HOST": "$DB_HOST"}, worktree)
            self.assertEqual(result, {"HOST": "localhost"})

    def test_expands_env_vars_brace_syntax(self) -> None:
        config = _make_config_with_containers({})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / ".env").write_text("DB_HOST=127.0.0.1\n")
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(path)
            result = manager._expand_env_vars({"HOST": "${DB_HOST}"}, worktree)
            self.assertEqual(result, {"HOST": "127.0.0.1"})

    def test_leaves_unmatched_vars_unchanged(self) -> None:
        config = _make_config_with_containers({})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(path)
            result = manager._expand_env_vars({"HOST": "$UNKNOWN"}, worktree)
            self.assertEqual(result, {"HOST": "$UNKNOWN"})


class TestContainerManagerExpandVolumes(unittest.TestCase):
    def test_expands_worktree_variable(self) -> None:
        config = _make_config_with_containers({})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            result = manager._expand_volumes({"$WORKTREE/data": "/data"}, worktree)
            expected_key = str(worktree.path / "data")
            self.assertEqual(result, {expected_key: "/data"})

    def test_expands_relative_paths(self) -> None:
        config = _make_config_with_containers({})

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ContainerManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            result = manager._expand_volumes({"./data": "/data"}, worktree)
            expected_key = str(worktree.path / "./data")
            self.assertEqual(result, {expected_key: "/data"})


class TestContainerManagerLoadEnvFile(unittest.TestCase):
    def test_loads_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text("FOO=bar\nBAZ=qux\n")
            config = WtConfig()
            manager = ContainerManager(tmpdir, config)
            result = manager._load_env_file(path)
            self.assertEqual(result, {"FOO": "bar", "BAZ": "qux"})

    def test_skips_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text("# comment\n\nFOO=bar\n  \n")
            config = WtConfig()
            manager = ContainerManager(tmpdir, config)
            result = manager._load_env_file(path)
            self.assertEqual(result, {"FOO": "bar"})

    def test_returns_empty_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            config = WtConfig()
            manager = ContainerManager(tmpdir, config)
            result = manager._load_env_file(path)
            self.assertEqual(result, {})


class TestDockerAdapterCommandBuilding(unittest.TestCase):
    @patch("wt.containers.adapters.subprocess.run")
    def test_builds_run_command_with_ports(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")
        adapter = DockerAdapter()

        adapter.run(
            name="test-container",
            image="postgres:15",
            ports={"5432": "5432"},
        )

        call_args = mock_run.call_args[0][0]
        self.assertIn("-p", call_args)
        self.assertIn("5432:5432", call_args)
        self.assertIn("--name", call_args)
        self.assertIn("test-container", call_args)
        self.assertIn("postgres:15", call_args)

    @patch("wt.containers.adapters.subprocess.run")
    def test_builds_run_command_with_volumes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")
        adapter = DockerAdapter()

        adapter.run(
            name="test-container",
            image="postgres:15",
            volumes={"/host/path": "/container/path"},
        )

        call_args = mock_run.call_args[0][0]
        self.assertIn("-v", call_args)
        self.assertIn("/host/path:/container/path", call_args)

    @patch("wt.containers.adapters.subprocess.run")
    def test_builds_run_command_with_environment(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")
        adapter = DockerAdapter()

        adapter.run(
            name="test-container",
            image="postgres:15",
            environment={"POSTGRES_PASSWORD": "secret"},
        )

        call_args = mock_run.call_args[0][0]
        self.assertIn("-e", call_args)
        self.assertIn("POSTGRES_PASSWORD=secret", call_args)

    @patch("wt.containers.adapters.subprocess.run")
    def test_builds_run_command_with_network(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")
        adapter = DockerAdapter()

        adapter.run(
            name="test-container",
            image="postgres:15",
            network="my-network",
        )

        call_args = mock_run.call_args[0][0]
        self.assertIn("--network", call_args)
        self.assertIn("my-network", call_args)


class TestDockerAdapterPs(unittest.TestCase):
    @patch("wt.containers.adapters.subprocess.run")
    def test_parses_ps_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123|my-container|postgres:15|Up 2 hours|5432/tcp|2024-01-01 00:00:00\n",
            stderr="",
        )
        adapter = DockerAdapter()

        result = adapter.ps()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "abc123")
        self.assertEqual(result[0].name, "my-container")
        self.assertEqual(result[0].image, "postgres:15")
        self.assertEqual(result[0].status, "Up 2 hours")

    @patch("wt.containers.adapters.subprocess.run")
    def test_handles_empty_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adapter = DockerAdapter()

        result = adapter.ps()

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
