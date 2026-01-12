# Implementation Plan (v2)

This plan turns the v2 spec into milestones with acceptance criteria.

## Epic A: Repo-local config + templates
**Scope**
- `wt init` creates `.wt/config`, `.wt/templates`, `.wt/state/wt.db`.
- `.gitignore` updated with `.wt/state`, `.wt/logs`, `.wt/cache`, `.worktrees`.

**Acceptance Criteria**
- Repo-local config and templates are committed.
- Runtime state is ignored.

## Epic B: Git adapter + reindex
**Scope**
- Parse `git worktree list --porcelain -z`.
- Derived git status (dirty, ahead/behind, behind main).
- `wt reindex` rebuilds DB cache.

**Acceptance Criteria**
- Manual worktrees are discovered.
- Missing paths become BROKEN or ABSENT.

## Epic C: State machine engine
**Scope**
- Transition rules for lifecycle/bootstrap/agent/runtime.
- Events stored for actions.

**Acceptance Criteria**
- Invalid transitions are rejected.
- Events recorded for success/failure.

## Epic D: Bootstrap + templates
**Scope**
- Idempotent template application.
- `uv`-based venv creation and `uv sync`.
- Deterministic port allocation.

**Acceptance Criteria**
- Re-running bootstrap is safe.
- Ports are stable and stored in DB.

## Epic E: tmux integration
**Scope**
- `wt open` creates session + window.
- Optional pane layouts driven from config.

**Acceptance Criteria**
- Works with existing or new tmux session.
- Layouts configurable via TOML.

## Epic F: Sync + land workflows
**Scope**
- `wt sync` brings main changes into worktree.
- `wt land` merges back to main and optional cleanup.

**Acceptance Criteria**
- Guardrails for dirty/unpushed branches.

## Epic G: TUI (Textual)
**Scope**
- Worktree list, detail preview, actions.

**Acceptance Criteria**
- Actions map to CLI behavior.
- Derived statuses visible.
