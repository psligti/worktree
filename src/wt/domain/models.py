from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


WorktreeLifecycle = Literal["ABSENT", "CREATING", "READY", "BROKEN", "REMOVING"]
BootstrapState = Literal["UNBOOTSTRAPPED", "BOOTSTRAPPING", "BOOTSTRAPPED", "BOOTSTRAP_ERROR"]
AgentState = Literal["DETACHED", "ATTACHING", "ATTACHED", "ATTACH_ERROR"]
RuntimeState = Literal["STOPPED", "STARTING", "RUNNING", "CRASHED", "STOPPING"]
GitSyncState = Literal["UP_TO_DATE", "BEHIND_MAIN", "AHEAD_MAIN", "DIVERGED", "NO_UPSTREAM"]


class WorktreeRecord(BaseModel):
    id: str
    name: str
    path: Path
    branch: Optional[str] = None
    purpose: Optional[str] = None
    head_sha: Optional[str] = None
    base_ref: Optional[str] = None

    lifecycle: WorktreeLifecycle = "ABSENT"
    bootstrap: BootstrapState = "UNBOOTSTRAPPED"
    agent: AgentState = "DETACHED"
    runtime: RuntimeState = "STOPPED"

    git_dirty: bool = False
    git_sync: Optional[GitSyncState] = None
    upstream: Optional[str] = None
    ahead: int = 0
    behind: int = 0
    behind_main: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: Optional[datetime] = None

    last_error: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventRecord(BaseModel):
    id: str
    worktree_id: str
    at: datetime
    type: str
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    cmd: Optional[list[str]] = None
    exit_code: Optional[int] = None
    message: Optional[str] = None


class RunRecord(BaseModel):
    id: str
    worktree_id: str
    cmd: str
    status: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    output_path: Optional[str] = None


class LockRecord(BaseModel):
    worktree_id: str
    owner: Optional[str] = None
    locked_at: Optional[datetime] = None
