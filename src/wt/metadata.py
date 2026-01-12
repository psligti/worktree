from __future__ import annotations

import json
import os
from typing import Any


METADATA_VERSION = 1


def metadata_path(repo_root: str) -> str:
    return os.path.join(repo_root, ".wt", "metadata.json")


def load_metadata(repo_root: str) -> dict[str, Any]:
    path = metadata_path(repo_root)
    if not os.path.exists(path):
        return {"version": METADATA_VERSION, "tasks": {}}

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        return {"version": METADATA_VERSION, "tasks": {}}

    if data.get("version") != METADATA_VERSION or not isinstance(data.get("tasks"), dict):
        return {"version": METADATA_VERSION, "tasks": {}}

    return data


def save_metadata(repo_root: str, data: dict[str, Any]) -> None:
    path = metadata_path(repo_root)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def upsert_task(
    data: dict[str, Any],
    task_id: str,
    path: str,
    branch: str | None,
    last_run_id: str | None = None,
) -> None:
    tasks = data.setdefault("tasks", {})
    existing = tasks.get(task_id, {})
    tasks[task_id] = {
        "path": path,
        "branch": branch,
        "last_run_id": last_run_id or existing.get("last_run_id"),
    }


def remove_task(data: dict[str, Any], task_id: str) -> None:
    tasks = data.get("tasks")
    if isinstance(tasks, dict):
        tasks.pop(task_id, None)


def update_task_run_id(data: dict[str, Any], task_id: str, run_id: str) -> None:
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        return
    task = tasks.get(task_id)
    if not isinstance(task, dict):
        return
    task["last_run_id"] = run_id


def sync_metadata(data: dict[str, Any], valid_paths: set[str]) -> bool:
    tasks = data.get("tasks")
    if not isinstance(tasks, dict):
        return False

    stale = [task_id for task_id, info in tasks.items() if info.get("path") not in valid_paths]
    for task_id in stale:
        tasks.pop(task_id, None)

    return bool(stale)
