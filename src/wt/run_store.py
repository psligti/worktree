from __future__ import annotations

import json
import os
from typing import Any


def run_record_path(repo_root: str, run_id: str) -> str:
    return os.path.join(repo_root, ".wt", "runs", f"{run_id}.json")


def save_run_record(repo_root: str, run_id: str, record: dict[str, Any]) -> str:
    path = run_record_path(repo_root, run_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)
    return path
