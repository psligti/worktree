# Worktree tools

This repo ships two local CLIs:
- `orch`: task-based worktree orchestration with YAML task plans, tmux panes, and Codex/LLM sessions.
- `wt`: state-machine worktree manager with repo-local config, tmux layouts, and a Textual TUI.

## orch

### Features
- Load epics/stories/acceptance criteria from `tasks.yaml`
- Deterministic branch, worktree, tmux window naming
- Human-triggered start/attach/pause/resume/done flows
- Batch start from an epic with concurrency limits
- Runtime overlay in `.orch/state.json`

### Requirements
- Python 3.12
- Git
- Optional: tmux, Textual, Codex/LLM CLI

### Install (local dev)
```
uv pip install -e .
```

### Quickstart
```
orch bootstrap
orch list
orch prompt E1-S1
orch start E1-S1 --provider codex
orch attach E1-S1 --pane codex
orch pause E1-S1
orch resume E1-S1
orch done E1-S1 --write-back-yaml
orch status
orch tui
```

### Task file
`tasks.yaml` is the source of truth. Example fields:
- `project`: name + repo_root
- `settings`: branch_prefix, worktree template, tmux settings, defaults
- `providers`: start command templates and prompt modes
- `epics`: stories with acceptance criteria

### Config
Optional overrides live in `.orch/config.yaml` and templates in `.orch/templates/`.
Runtime state is stored in `.orch/state.json`.

### TUI
```
orch tui
```
Key bindings: `r` refresh, `n` next attention, `a` actions, `q` quit.

## wt

A state-machine worktree orchestrator with repo-local config, tmux integration, and a Textual TUI. Git remains the source of truth; the SQLite DB is a cache you can rebuild at any time.

### Features
- One-command worktree setup: create, template, bootstrap, open
- Repo-local config and templates in `.wt/`
- Reindexable SQLite cache at `.wt/state/wt.db`
- Lockable worktrees with purpose metadata and per-worktree runs
- Optional FastAPI server for worktree metadata
- TUI for fast browsing and actions
- tmux windows/panes managed from Python (no AppleScript)

### Requirements
- Python 3.12
- Git
- Optional: tmux, uv, Textual

### Quickstart
```
wt init
wt new feat-x --bootstrap --open
wt add feat-x --branch feature/api-cleanup
wt ls
wt open feat-x --layout three-pane
wt sync feat-x --strategy rebase
wt land feat-x --cleanup
wt rm feat-x
wt reindex
wt doctor
wt tui
```

### Config
Repo-local config lives in `.wt/config/wt.toml` with optional profiles in `.wt/config/profiles/*.toml`.
Templates are in `.wt/templates/` and applied on create/bootstrap.

### TUI
```
wt tui
```
Key bindings: `n` create, `o` open, `e` edit config, `c` copy branch, `p` copy path, `b` bootstrap, `s` sync, `l` land, `x` remove, `R` reindex, `d` doctor, `r` refresh, `q` quit.
