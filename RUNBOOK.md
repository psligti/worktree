# RUNBOOK

Operational guidance for the `wt` tool (v2).

## Setup
```
uv pip install -e .
```

## Initialize repo-local config
```
wt init
```

## Create and bootstrap a worktree
```
wt new feat-x --bootstrap
wt new feat-x --bootstrap --open
wt new feat-x --purpose "API cleanup"
```

## Open in tmux
```
wt open feat-x
wt open feat-x --layout three-pane
```

## List and inspect
```
wt ls
wt ls --json
```

## Sync from main
```
wt sync feat-x --strategy rebase
wt sync feat-x --strategy merge --from origin/main
```

## Land back to main (local merge-first)
```
wt land feat-x --cleanup
wt land feat-x --run-checks
```
- `--run-checks` runs hook commands/scripts from `.wt/config/hooks.d/run_checks.d` and `hooks.run_checks`.

## Worktree purpose
```
wt purpose feat-x "API cleanup"
wt purpose feat-x
wt purpose feat-x --clear
```

## Lock/unlock worktrees
```
wt lock feat-x --reason "focus work"
wt unlock feat-x
```

## Run a command in a worktree
```
wt run feat-x --lock-on-run -- uv run pytest -q
wt run feat-x --artifacts .wt/runs -- uv run pytest -q
```

## Remove worktrees
```
wt rm feat-x
wt rm feat-x --force
```

## Reindex and doctor
```
wt reindex
wt doctor
```

## API server
```
wt api
```

## TUI
```
wt tui
```

## Exit Codes
- `0`: Success
- `1`: General error
- `2`: Usage error
- `3`: Not found
- `4`: Conflict/guardrail
- `5`: Git failure
