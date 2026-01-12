from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

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
        content = self.path.read_text(encoding="utf-8")
        normalized = _normalize_yaml_indent(content)
        data = yaml.safe_load(normalized) or {}
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


def _normalize_yaml_indent(content: str) -> str:
    dedented = textwrap.dedent(content)
    lines = dedented.splitlines()
    if len(lines) < 2:
        return dedented
    first_indent = len(lines[0]) - len(lines[0].lstrip())
    other_indents = [len(line) - len(line.lstrip()) for line in lines[1:] if line.strip()]
    if first_indent == 0 and other_indents:
        common = min(other_indents)
        if common:
            adjusted = [lines[0]]
            for line in lines[1:]:
                if line.startswith(" " * common):
                    adjusted.append(line[common:])
                else:
                    adjusted.append(line.lstrip())
            return "\n".join(adjusted)
    return dedented
