from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wt.config.models import DatabaseConfig, WtConfig
from wt.database.adapters import SqliteAdapter
from wt.database.manager import DatabaseError, DatabaseManager
from wt.domain.models import WorktreeRecord


def _make_worktree(path: Path, name: str = "test-wt") -> WorktreeRecord:
    return WorktreeRecord(
        id="wt-123",
        name=name,
        path=path,
        branch="wt/test",
    )


def _make_config(enabled: bool = True) -> WtConfig:
    return WtConfig(
        database=DatabaseConfig(enabled=enabled),
    )


class TestSqliteAdapterCreate(unittest.TestCase):
    def test_creates_database_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)
            adapter.create("testdb")
            self.assertTrue((base_dir / "testdb.db").exists())

    def test_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "nested" / "databases"
            adapter = SqliteAdapter(base_dir)
            adapter.create("testdb")
            self.assertTrue((base_dir / "testdb.db").exists())


class TestSqliteAdapterDrop(unittest.TestCase):
    def test_removes_database_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)
            adapter.create("testdb")
            self.assertTrue(adapter.exists("testdb"))
            adapter.drop("testdb")
            self.assertFalse(adapter.exists("testdb"))

    def test_no_error_for_missing_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)
            adapter.drop("nonexistent")


class TestSqliteAdapterExists(unittest.TestCase):
    def test_returns_true_when_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)
            adapter.create("testdb")
            self.assertTrue(adapter.exists("testdb"))

    def test_returns_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)
            self.assertFalse(adapter.exists("testdb"))


class TestSqliteAdapterSnapshot(unittest.TestCase):
    def test_copies_database_to_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)
            adapter.create("testdb")
            (base_dir / "testdb.db").write_text("data")

            output_path = Path(tmpdir) / "snapshot.sql"
            adapter.snapshot("testdb", output_path)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_text(), "data")


class TestSqliteAdapterRestore(unittest.TestCase):
    def test_restores_from_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)

            snapshot_path = Path(tmpdir) / "snapshot.sql"
            snapshot_path.write_text("restored_data")

            adapter.restore("testdb", snapshot_path)
            self.assertTrue(adapter.exists("testdb"))
            self.assertEqual((base_dir / "testdb.db").read_text(), "restored_data")


class TestSqliteAdapterClone(unittest.TestCase):
    def test_clones_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "databases"
            adapter = SqliteAdapter(base_dir)
            adapter.create("source")
            (base_dir / "source.db").write_text("source_data")

            adapter.clone("source", "target")
            self.assertTrue(adapter.exists("target"))
            self.assertEqual((base_dir / "target.db").read_text(), "source_data")


class TestDatabaseManagerDbName(unittest.TestCase):
    def test_generates_name_from_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "my-feature")
            name = manager.db_name_for_worktree(worktree)
            self.assertEqual(name, "my_feature")

    def test_appends_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "my-feature")
            name = manager.db_name_for_worktree(worktree, "test")
            self.assertEqual(name, "my_feature_test")

    def test_handles_slashes_in_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "wt/my-feature")
            name = manager.db_name_for_worktree(worktree)
            self.assertEqual(name, "wt_my_feature")


class TestDatabaseManagerCreate(unittest.TestCase):
    def test_creates_sqlite_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            db_name = manager.create_database(worktree, "sqlite")
            self.assertEqual(db_name, "feat_x")
            self.assertTrue(manager.database_exists(worktree, "sqlite"))

    def test_raises_if_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            manager.create_database(worktree, "sqlite")
            with self.assertRaises(DatabaseError) as ctx:
                manager.create_database(worktree, "sqlite")
            self.assertIn("already exists", str(ctx.exception))


class TestDatabaseManagerDrop(unittest.TestCase):
    def test_drops_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            manager.create_database(worktree, "sqlite")
            self.assertTrue(manager.database_exists(worktree, "sqlite"))
            manager.drop_database(worktree, "sqlite")
            self.assertFalse(manager.database_exists(worktree, "sqlite"))


class TestDatabaseManagerSnapshot(unittest.TestCase):
    def test_creates_snapshot_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            manager.create_database(worktree, "sqlite")

            snapshot_path = manager.snapshot(worktree, "sqlite", snapshot_name="test")
            self.assertTrue(snapshot_path.exists())
            self.assertEqual(snapshot_path.name, "test.sql")

    def test_auto_generates_timestamp_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            manager.create_database(worktree, "sqlite")

            snapshot_path = manager.snapshot(worktree, "sqlite")
            self.assertTrue(snapshot_path.exists())
            self.assertIn("feat_x_", snapshot_path.name)


class TestDatabaseManagerRestore(unittest.TestCase):
    def test_restores_from_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            manager.create_database(worktree, "sqlite")

            snapshot_path = manager.snapshot(worktree, "sqlite", snapshot_name="backup")
            manager.drop_database(worktree, "sqlite")
            self.assertFalse(manager.database_exists(worktree, "sqlite"))

            manager.restore(worktree, "sqlite", snapshot_path)
            self.assertTrue(manager.database_exists(worktree, "sqlite"))

    def test_raises_for_missing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            missing_path = Path(tmpdir) / "missing.sql"
            with self.assertRaises(DatabaseError) as ctx:
                manager.restore(worktree, "sqlite", missing_path)
            self.assertIn("not found", str(ctx.exception))


class TestDatabaseManagerClone(unittest.TestCase):
    def test_clones_between_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            source = _make_worktree(Path(tmpdir), "source-wt")
            target = _make_worktree(Path(tmpdir), "target-wt")

            manager.create_database(source, "sqlite")
            target_name = manager.clone_database(source, target, "sqlite")
            self.assertEqual(target_name, "target_wt")
            self.assertTrue(manager.database_exists(target, "sqlite"))

    def test_raises_for_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            source = _make_worktree(Path(tmpdir), "source-wt")
            target = _make_worktree(Path(tmpdir), "target-wt")

            with self.assertRaises(DatabaseError) as ctx:
                manager.clone_database(source, target, "sqlite")
            self.assertIn("not found", str(ctx.exception))


class TestDatabaseManagerReset(unittest.TestCase):
    def test_drops_and_recreates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            manager.create_database(worktree, "sqlite")

            db_path = Path(tmpdir) / ".wt" / "databases" / "feat_x.db"
            db_path.write_text("old_data")

            manager.reset_database(worktree, "sqlite")
            self.assertTrue(manager.database_exists(worktree, "sqlite"))
            self.assertEqual(db_path.read_text(), "")


class TestDatabaseManagerListSnapshots(unittest.TestCase):
    def test_lists_snapshots_for_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            manager.create_database(worktree, "sqlite")

            manager.snapshot(worktree, "sqlite", snapshot_name="snap1")
            manager.snapshot(worktree, "sqlite", snapshot_name="snap2")

            snapshots = manager.list_snapshots(worktree)
            self.assertEqual(len(snapshots), 2)
            names = [s.name for s in snapshots]
            self.assertIn("snap1.sql", names)
            self.assertIn("snap2.sql", names)

    def test_returns_empty_for_no_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = _make_config()
            manager = DatabaseManager(tmpdir, config)
            worktree = _make_worktree(Path(tmpdir), "feat-x")
            snapshots = manager.list_snapshots(worktree)
            self.assertEqual(snapshots, [])


if __name__ == "__main__":
    unittest.main()
