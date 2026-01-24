from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wt.domain.models import WorktreeRecord
from wt.ops.gc import select_gc_candidates


def _make_record(
    worktree_id: str,
    name: str,
    created_at: datetime,
    last_accessed_at: datetime | None = None,
    lifecycle: str = "READY",
) -> WorktreeRecord:
    return WorktreeRecord(
        id=worktree_id,
        name=name,
        path=Path(f"/tmp/{name}"),
        branch=f"wt/{name}",
        lifecycle=lifecycle,
        bootstrap="UNBOOTSTRAPPED",
        agent="DETACHED",
        runtime="STOPPED",
        created_at=created_at,
        last_accessed_at=last_accessed_at,
        updated_at=created_at,
    )


class TestGcCandidates(unittest.TestCase):
    def test_selects_inactive_worktrees(self) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=10)
        recent = now - timedelta(days=1)

        records = [
            _make_record("1", "old", created_at=old),
            _make_record("2", "recent", created_at=recent),
        ]

        candidates = select_gc_candidates(
            records,
            locked_ids=set(),
            inactive_days=7,
            include_absent=False,
        )

        self.assertEqual([c.record.name for c in candidates], ["old"])
        self.assertEqual(candidates[0].reason, "inactive")

    def test_uses_last_accessed_at_when_present(self) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=12)
        recent = now - timedelta(days=2)

        record = _make_record(
            "1",
            "with-access",
            created_at=old,
            last_accessed_at=recent,
        )

        candidates = select_gc_candidates(
            [record],
            locked_ids=set(),
            inactive_days=7,
            include_absent=False,
        )

        self.assertEqual(candidates, [])

    def test_skips_locked_worktrees(self) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=10)
        record = _make_record("1", "locked", created_at=old)

        candidates = select_gc_candidates(
            [record],
            locked_ids={"1"},
            inactive_days=7,
            include_absent=False,
        )

        self.assertEqual(candidates, [])

    def test_includes_absent_when_requested(self) -> None:
        now = datetime.now(timezone.utc)
        record = _make_record(
            "1",
            "gone",
            created_at=now - timedelta(days=1),
            lifecycle="ABSENT",
        )

        candidates = select_gc_candidates(
            [record],
            locked_ids=set(),
            inactive_days=None,
            include_absent=True,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].reason, "absent")

    def test_excludes_absent_by_default(self) -> None:
        now = datetime.now(timezone.utc)
        record = _make_record(
            "1",
            "gone",
            created_at=now - timedelta(days=1),
            lifecycle="ABSENT",
        )

        candidates = select_gc_candidates(
            [record],
            locked_ids=set(),
            inactive_days=None,
            include_absent=False,
        )

        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
