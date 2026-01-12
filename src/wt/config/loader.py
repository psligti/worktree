from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import tomllib

from .models import WtConfig


def config_root(repo_root: str) -> str:
    return os.path.join(repo_root, ".wt", "config")


def load_config(repo_root: str, profile: str | None = None) -> WtConfig:
    base_path = os.path.join(config_root(repo_root), "wt.toml")
    base_data = _load_toml(base_path)
    merged = dict(base_data)

    if profile:
        profile_path = os.path.join(config_root(repo_root), "profiles", f"{profile}.toml")
        profile_data = _load_toml(profile_path)
        merged = _merge_dicts(merged, profile_data)

    config = WtConfig.model_validate(merged)
    _write_resolved_config(repo_root, config)
    return config


def _load_toml(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _write_resolved_config(repo_root: str, config: WtConfig) -> None:
    cache_dir = Path(repo_root) / ".wt" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "resolved_config.json"
    data = config.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
