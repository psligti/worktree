from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .models import Epic, Story, TasksDocument


class TaskStoreError(RuntimeError):
    pass


class TaskStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> TasksDocument:
        if not self.path.exists():
            raise TaskStoreError(f"tasks file not found: {self.path}")
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return TasksDocument.model_validate(data)

    def write(self, doc: TasksDocument) -> None:
        data = doc.model_dump(mode="json")
        self.path.write_text(
            yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    def mark_story_done(self, story_id: str, done: bool = True) -> bool:
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        updated = False
        for epic in raw.get("epics", []) or []:
            for story in epic.get("stories", []) or []:
                if story.get("id") == story_id:
                    story["done"] = done
                    updated = True
        if updated:
            self.path.write_text(
                yaml.safe_dump(raw, sort_keys=False, default_flow_style=False),
                encoding="utf-8",
            )
        return updated

    def find_story(self, doc: TasksDocument, story_id: str) -> Optional[Story]:
        for epic in doc.epics:
            for story in epic.stories:
                if story.id == story_id:
                    return story
        return None

    def find_epic(self, doc: TasksDocument, epic_id: str) -> Optional[Epic]:
        for epic in doc.epics:
            if epic.id == epic_id:
                return epic
        return None
