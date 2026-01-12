import unittest
from pathlib import Path

from wt.domain.models import WorktreeRecord
from wt.domain.status import overall_status


class TestOverallStatus(unittest.TestCase):
    def test_broken_has_priority(self) -> None:
        record = WorktreeRecord(
            id="1",
            name="feat-x",
            path=Path("/repo/.worktrees/feat-x"),
            lifecycle="BROKEN",
            bootstrap="UNBOOTSTRAPPED",
            agent="DETACHED",
            runtime="STOPPED",
        )
        self.assertEqual(overall_status(record), "BROKEN")

    def test_unbootstrapped(self) -> None:
        record = WorktreeRecord(
            id="1",
            name="feat-x",
            path=Path("/repo/.worktrees/feat-x"),
            lifecycle="READY",
            bootstrap="UNBOOTSTRAPPED",
            agent="DETACHED",
            runtime="STOPPED",
        )
        self.assertEqual(overall_status(record), "UNBOOTSTRAPPED")

    def test_dirty_ready(self) -> None:
        record = WorktreeRecord(
            id="1",
            name="feat-x",
            path=Path("/repo/.worktrees/feat-x"),
            lifecycle="READY",
            bootstrap="BOOTSTRAPPED",
            agent="DETACHED",
            runtime="STOPPED",
            git_dirty=True,
        )
        self.assertEqual(overall_status(record), "DIRTY")


if __name__ == "__main__":
    unittest.main()
