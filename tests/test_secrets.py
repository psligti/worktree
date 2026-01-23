from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wt.config.models import SecretsConfig, WtConfig
from wt.domain.models import WorktreeRecord
from wt.secrets.adapters import EncryptedFileAdapter, EnvFileAdapter
from wt.secrets.manager import SecretsError, SecretsManager


def _make_worktree(path: Path, name: str = "test-wt") -> WorktreeRecord:
    return WorktreeRecord(
        id="wt-123",
        name=name,
        path=path,
        branch="wt/test",
    )


def _make_config(
    backend: str = "env",
    env_file: str = ".env.secrets",
    required_keys: list[str] | None = None,
) -> WtConfig:
    return WtConfig(
        secrets=SecretsConfig(
            enabled=True,
            backend=backend,  # type: ignore[arg-type]
            env_file=env_file,
            required_keys=required_keys or [],
        ),
    )


class TestEnvFileAdapter(unittest.TestCase):
    def test_set_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.secrets"
            adapter = EnvFileAdapter(env_file)

            adapter.set("API_KEY", "secret123")
            self.assertEqual(adapter.get("API_KEY"), "secret123")

    def test_get_nonexistent_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.secrets"
            adapter = EnvFileAdapter(env_file)

            self.assertIsNone(adapter.get("MISSING"))

    def test_delete_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.secrets"
            adapter = EnvFileAdapter(env_file)

            adapter.set("API_KEY", "secret123")
            adapter.delete("API_KEY")
            self.assertIsNone(adapter.get("API_KEY"))

    def test_list_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.secrets"
            adapter = EnvFileAdapter(env_file)

            adapter.set("KEY1", "val1")
            adapter.set("KEY2", "val2")
            keys = adapter.list_keys()
            self.assertEqual(sorted(keys), ["KEY1", "KEY2"])

    def test_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.secrets"
            adapter = EnvFileAdapter(env_file)

            self.assertFalse(adapter.exists("KEY1"))
            adapter.set("KEY1", "val1")
            self.assertTrue(adapter.exists("KEY1"))

    def test_handles_comments_and_empty_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.secrets"
            env_file.write_text("# comment\n\nKEY1=val1\n")
            adapter = EnvFileAdapter(env_file)

            self.assertEqual(adapter.get("KEY1"), "val1")
            self.assertEqual(adapter.list_keys(), ["KEY1"])


class TestEncryptedFileAdapter(unittest.TestCase):
    def test_set_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_file = Path(tmpdir) / "secrets.enc"
            key_file = Path(tmpdir) / "secrets.key"
            adapter = EncryptedFileAdapter(encrypted_file, key_file)

            adapter.set("DB_PASSWORD", "supersecret")
            self.assertEqual(adapter.get("DB_PASSWORD"), "supersecret")

    def test_creates_key_file_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_file = Path(tmpdir) / "secrets.enc"
            key_file = Path(tmpdir) / "secrets.key"
            adapter = EncryptedFileAdapter(encrypted_file, key_file)

            adapter.set("KEY1", "val1")
            self.assertTrue(key_file.exists())

    def test_delete_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_file = Path(tmpdir) / "secrets.enc"
            key_file = Path(tmpdir) / "secrets.key"
            adapter = EncryptedFileAdapter(encrypted_file, key_file)

            adapter.set("KEY1", "val1")
            adapter.delete("KEY1")
            self.assertIsNone(adapter.get("KEY1"))

    def test_list_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            encrypted_file = Path(tmpdir) / "secrets.enc"
            key_file = Path(tmpdir) / "secrets.key"
            adapter = EncryptedFileAdapter(encrypted_file, key_file)

            adapter.set("KEY1", "val1")
            adapter.set("KEY2", "val2")
            keys = adapter.list_keys()
            self.assertEqual(sorted(keys), ["KEY1", "KEY2"])


class TestSecretsManagerGetAdapter(unittest.TestCase):
    def test_returns_env_adapter_for_env_backend(self) -> None:
        config = _make_config(backend="env")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            adapter = manager.get_adapter(worktree)
            self.assertIsInstance(adapter, EnvFileAdapter)

    def test_returns_encrypted_adapter_for_encrypted_backend(self) -> None:
        config = _make_config(backend="encrypted")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            adapter = manager.get_adapter(worktree)
            self.assertIsInstance(adapter, EncryptedFileAdapter)


class TestSecretsManagerOperations(unittest.TestCase):
    def test_get_set_delete_workflow(self) -> None:
        config = _make_config(backend="env")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            manager.set(worktree, "API_KEY", "secret123")
            self.assertEqual(manager.get(worktree, "API_KEY"), "secret123")

            manager.delete(worktree, "API_KEY")
            self.assertIsNone(manager.get(worktree, "API_KEY"))

    def test_list_keys(self) -> None:
        config = _make_config(backend="env")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            manager.set(worktree, "KEY1", "val1")
            manager.set(worktree, "KEY2", "val2")
            keys = manager.list_keys(worktree)
            self.assertEqual(sorted(keys), ["KEY1", "KEY2"])

    def test_exists(self) -> None:
        config = _make_config(backend="env")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            self.assertFalse(manager.exists(worktree, "KEY1"))
            manager.set(worktree, "KEY1", "val1")
            self.assertTrue(manager.exists(worktree, "KEY1"))


class TestSecretsManagerSyncToEnv(unittest.TestCase):
    def test_syncs_secrets_to_dotenv(self) -> None:
        config = _make_config(backend="env", env_file=".secrets")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            manager.set(worktree, "DB_PASSWORD", "secret")
            manager.set(worktree, "API_KEY", "key123")

            count = manager.sync_to_env(worktree)
            self.assertEqual(count, 2)

            dotenv_path = wt_path / ".env"
            content = dotenv_path.read_text()
            self.assertIn("DB_PASSWORD=secret", content)
            self.assertIn("API_KEY=key123", content)

    def test_returns_zero_when_no_secrets(self) -> None:
        config = _make_config(backend="env")

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            count = manager.sync_to_env(worktree)
            self.assertEqual(count, 0)


class TestSecretsManagerCheckRequired(unittest.TestCase):
    def test_returns_empty_when_all_present(self) -> None:
        config = _make_config(
            backend="env",
            required_keys=["KEY1", "KEY2"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            manager.set(worktree, "KEY1", "val1")
            manager.set(worktree, "KEY2", "val2")

            missing = manager.check_required(worktree)
            self.assertEqual(missing, [])

    def test_returns_missing_keys(self) -> None:
        config = _make_config(
            backend="env",
            required_keys=["KEY1", "KEY2", "KEY3"],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            manager.set(worktree, "KEY1", "val1")

            missing = manager.check_required(worktree)
            self.assertEqual(sorted(missing), ["KEY2", "KEY3"])

    def test_returns_empty_when_no_required_keys_configured(self) -> None:
        config = _make_config(backend="env", required_keys=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            wt_path = Path(tmpdir) / "worktree"
            wt_path.mkdir()
            worktree = _make_worktree(wt_path)
            manager = SecretsManager(tmpdir, config)

            missing = manager.check_required(worktree)
            self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
