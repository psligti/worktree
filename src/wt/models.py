from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GitWorktree:
    path: str
    head_sha: str
    branch: Optional[str]
    detached: bool
    locked: bool
    lock_reason: Optional[str]
    prunable: Optional[bool]
    prunable_reason: Optional[str]
