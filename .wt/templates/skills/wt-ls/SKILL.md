---
name: wt-ls
description: List all worktrees with their status (branch, purpose, lock status, run info)
---

When to use
-----------
Use `wt ls` when:
- Need an overview of all worktrees in the repository
- Want to check the status of specific worktrees (dirty, sync state)
- Looking for available worktrees to work on
- Checking which worktrees are bootstrapped, running, or have errors
- Need machine-readable output for scripts (use `--json`)

DO NOT use `wt ls` when:
- Need to create a new worktree (use `wt new` or `wt add`)
- Want to open/attach to a worktree (use `wt open`)
- Need to modify worktree state (use `wt`, `wt sync`, `wt bootstrap`)
- Want detailed info about a single worktree (use `wt status` or `wt tui`)

Primary commands
----------------
```bash
# List all worktrees with status in table format
wt ls

# List worktrees with specific profile config
wt ls --profile ui-dev

# Output as JSON for scripting
wt ls --json
```

The command displays:
- `name`: Worktree name
- `branch`: Branch name (or "(detached)" if no branch)
- `status`: Derived overall status (see Status indicators below)
- `dirty`: "yes" if uncommitted changes, "no" if clean
- `sync`: Git sync state summary
- `path`: Full filesystem path to worktree

Common workflows
----------------

Quick overview of all worktrees
```bash
$ wt ls
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ name       ┃ branch              ┃ status     ┃ dirty ┃ sync  ┃ path                        ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ feat-x     │ wt/feat-x           │ READY      │ no    │ ✓     │ .worktrees/feat-x           │
│ bug-fix    │ wt/bug-fix          │ DIRTY      │ yes   │ ✓     │ .worktrees/bug-fix          │
│ refactor   │ wt/refactor         │ BEHIND_MAIN│ no    │ -3    │ .worktrees/refactor        │
└────────────┴─────────────────────┴────────────┴───────┴───────┴──────────────────────────────┘
```

Find worktrees with issues
```bash
# Run wt ls and look for non-READY statuses
wt ls | grep -E "DIRTY|ERROR|BROKEN|DIVERGED|BEHIND_MAIN"
```

Scripting with JSON output
```bash
# Get all READY worktrees as JSON
wt ls --json | jq -r '.[] | select(.status == "READY") | .name'

# Find dirty worktrees
wt ls --json | jq -r '.[] | select(.git_dirty == true) | .name'

# Get paths for all worktrees
wt ls --json | jq -r '.[].path'
```

Status indicators
-----------------
The `status` column is derived from multiple factors:

- `READY`: Clean, up-to-date, bootstrapped, no errors
- `DIRTY`: Has uncommitted changes
- `ERROR`: Bootstrap failed, agent attach failed, or runtime crashed
- `BROKEN`: Worktree lifecycle is broken
- `IN_PROGRESS`: Currently creating, removing, bootstrapping, starting, or stopping
- `UNBOOTSTRAPPED`: Not yet bootstrapped
- `DIVERGED`: Git history diverged from upstream
- `BEHIND_MAIN`: Behind main branch

Git sync states (`sync` column):
- `✓`: UP_TO_DATE
- `+<n>`: AHEAD_MAIN (n commits ahead)
- `‑<n>`: BEHIND_MAIN (n commits behind)
- `DIVERGED`: History diverged
- `-`: NO_UPSTREAM

Safety checks
-------------
Before running `wt ls`:
1. Verify `wt init` has been run in the repository
2. Ensure you're in a Git repository (uses repo root detection)

After running `wt ls`:
1. Check the `status` column for worktrees needing attention
2. Note `dirty` worktrees that may need commits or stashing
3. Review `sync` column for worktrees needing rebasing or merging

"Don't do" guardrails
--------------------
- DON'T parse the table output programmatically (use `--json` instead)
- DON'T use `wt ls` to check if a worktree exists before operations (let `wt` handle errors)
- DON'T assume status values are stable (they may change between versions)
- DON'T use path output for shell escaping issues (use JSON output for scripts)

Examples
--------

Basic listing
```bash
$ cd my-repo
$ wt ls
initialized .wt configuration and database
[Output: Table showing all worktrees]
```

With custom profile
```bash
$ wt ls --profile agent-dev
[Output: Uses agent-dev profile config to reindex and list]
```

JSON output for scripts
```bash
$ wt ls --json | jq '.'
[
  {
    "id": "uuid-1",
    "name": "feat-x",
    "path": ".worktrees/feat-x",
    "branch": "wt/feat-x",
    "purpose": "Add feature X",
    "status": "READY",
    "git_dirty": false,
    "git_sync": "UP_TO_DATE",
    "ahead": 0,
    "behind": 0,
    "lifecycle": "READY",
    "bootstrap": "BOOTSTRAPPED",
    ...
  }
]
```

Filtering with jq
```bash
# Find worktrees by purpose
$ wt ls --json | jq -r '.[] | select(.purpose | contains("api")) | .name'

# Get worktrees ahead of upstream
$ wt ls --json | jq -r '.[] | select(.ahead > 0) | "\(.name) (\(.ahead) ahead)"'
```

Integration with other commands
```bash
# Open the first READY worktree
$ WT=$(wt ls --json | jq -r '.[] | select(.status == "READY") | .name' | head -1)
$ wt open $WT

# Sync all worktrees behind main
$ wt ls --json | jq -r '.[] | select(.git_sync == "BEHIND_MAIN") | .name' | xargs -I {} wt sync {} --strategy rebase
```
