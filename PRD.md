# Worktree Orchestrator v2 PRD

## 1. Overview
A state-machine-driven worktree orchestrator with repo-local configuration, tmux-based window management, and a Textual TUI. Git is the source of truth; the SQLite DB is a rebuildable cache.

## 2. Goals
- One-command “ready to work” worktrees: create + bootstrap + open.
- Explicit state machines for lifecycle, bootstrap, agent, and runtime.
- Repo-local `.wt/` config/templates committed; runtime state ignored.
- tmux integration for session/window/pane management.
- TUI that shows “what’s missing” and the next action.

## 3. Non-goals
- Full PR automation across hosts.
- Always-on daemon for correctness.
- Non-tmux GUI window management.

## 4. Key Principles
- Git is authoritative; DB is a cache.
- Idempotent actions.
- Derived Git status is not stored as truth.
- Repo-local config and templates for portability.

## 5. CLI Surface Area
- `wt init`
- `wt new <name> [--base main] [--profile X] [--open] [--bootstrap]`
- `wt open <name> [--layout X]`
- `wt bootstrap <name>`
- `wt ls [--json]`
- `wt sync <name> [--strategy rebase|merge] [--from origin/main]`
- `wt land <name> [--strategy merge] [--run-checks] [--cleanup]`
- `wt rm <name> [--force]`
- `wt reindex`
- `wt doctor`
- `wt tui`

## 6. Repo Layout
Committed:
- `.wt/config/**`
- `.wt/templates/**`

Ignored:
- `.wt/state/**`
- `.wt/logs/**`
- `.wt/cache/**`
- `.worktrees/**`

## 7. State Machines
Controlled:
- Worktree lifecycle
- Bootstrap readiness
- Agent attachment (optional)
- Runtime services (optional)

Derived:
- Git dirty status
- Sync state vs upstream/main

## 8. Persistence
- SQLite at `.wt/state/wt.db`
- Tables: worktrees, events, runs, locks, ports, settings_cache
- `wt reindex` rebuilds cache from git worktree list.

## 9. tmux Integration
- `wt open` creates/uses session and opens window at worktree path.
- Layouts configurable in TOML.

## 10. TUI
- Worktree list, detail preview, logs/diagnostics.
- Keybindings for open/bootstrap/sync/land/remove.
