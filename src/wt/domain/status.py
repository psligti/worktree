from __future__ import annotations

from .models import WorktreeRecord


def overall_status(record: WorktreeRecord) -> str:
    if record.lifecycle == "BROKEN":
        return "BROKEN"

    if record.bootstrap == "BOOTSTRAP_ERROR" or record.agent == "ATTACH_ERROR" or record.runtime == "CRASHED":
        return "ERROR"

    if (
        record.lifecycle in {"CREATING", "REMOVING"}
        or record.bootstrap == "BOOTSTRAPPING"
        or record.agent == "ATTACHING"
        or record.runtime in {"STARTING", "STOPPING"}
    ):
        return "IN_PROGRESS"

    if record.bootstrap == "UNBOOTSTRAPPED":
        return "UNBOOTSTRAPPED"

    if record.git_sync in {"DIVERGED", "BEHIND_MAIN"}:
        return record.git_sync

    if record.git_dirty:
        return "DIRTY"

    return "READY"
