from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import StateFile, TaskRuntimeState


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, repo_root: Path, tmux_session: str) -> StateFile:
        if not self.path.exists():
            return StateFile(repo_root=repo_root, tmux_session=tmux_session)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return StateFile.model_validate(data)

    def write(self, state: StateFile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    def get_task(self, state: StateFile, story_id: str) -> Optional[TaskRuntimeState]:
        return state.tasks.get(story_id)

    def upsert_task(self, state: StateFile, task_state: TaskRuntimeState) -> None:
        state.tasks[task_state.story_id] = task_state
