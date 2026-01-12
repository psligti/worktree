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
