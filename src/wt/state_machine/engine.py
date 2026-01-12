from __future__ import annotations

from typing import Mapping


class TransitionError(RuntimeError):
    pass


def apply_transition(current: str, event: str, transitions: Mapping[str, Mapping[str, str]]) -> str:
    next_state = transitions.get(current, {}).get(event)
    if not next_state:
        raise TransitionError(f"invalid transition: {current} -> {event}")
    return next_state


def can_transition(current: str, event: str, transitions: Mapping[str, Mapping[str, str]]) -> bool:
    return event in transitions.get(current, {})
