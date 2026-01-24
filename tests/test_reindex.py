from __future__ import annotations

import unittest
from pathlib import Path

from wt.domain.models import WorktreeRecord
from wt.ops.reindex import _maybe_record_sync_event


def _make_record(path: Path, git_sync: str | None) -> WorktreeRecord:
    return WorktreeRecord(
        id="wt-1",
        name="wt-1",
        path=path,
        branch="wt/test",
        git_sync=git_sync,
    )


class TestReindexSyncEvents(unittest.TestCase):
    def test_records_event_for_diverged(self) -> None:
        events = []
        record = _make_record(Path("/tmp/wt-1"), "DIVERGED")

        _maybe_record_sync_event(None, record, events)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.type, "SyncOutOfDate")
        self.assertIsNone(event.from_state)
        self.assertEqual(event.to_state, "DIVERGED")

    def test_skips_event_when_up_to_date(self) -> None:
        events = []
        record = _make_record(Path("/tmp/wt-1"), "UP_TO_DATE")

        _maybe_record_sync_event("BEHIND_MAIN", record, events)

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
