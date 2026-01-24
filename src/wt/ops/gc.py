from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..domain.models import WorktreeRecord


@dataclass(frozen=True)
class GcCandidate:
    record: WorktreeRecord
    reason: str


def select_gc_candidates(
    records: list[WorktreeRecord],
    locked_ids: set[str],
    inactive_days: Optional[int],
    include_absent: bool,
) -> list[GcCandidate]:
    now = datetime.now(timezone.utc)
    cutoff = None
    if inactive_days is not None:
        cutoff = now - timedelta(days=inactive_days)

    candidates: list[GcCandidate] = []
    for record in records:
        if record.id in locked_ids:
            continue

        if record.lifecycle == "ABSENT":
            if include_absent:
                candidates.append(GcCandidate(record=record, reason="absent"))
            continue

        if cutoff is None:
            continue

        last_seen = record.last_accessed_at or record.created_at
        if last_seen <= cutoff:
            candidates.append(GcCandidate(record=record, reason="inactive"))

    return candidates
