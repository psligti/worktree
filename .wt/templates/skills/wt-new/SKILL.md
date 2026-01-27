---
name: wt-new
description: Create a new worktree with a new branch, optionally bootstrapping and opening it
---

When to use
-----------
Use `wt new` when:
- Starting a new feature or fix in an isolated worktree
- Creating a clean environment for development work
- Setting up a new task or experiment without disrupting the main branch
- You need a fresh workspace with its own branch (automatically named `wt/{name}`)

DO NOT use `wt new` when:
- You want to add a worktree for an existing branch (use `wt add --branch <branch>`)
- You want to clone an existing worktree (use `wt clone <source> <name>`)
- Working in a non-Git repository (will fail)
- Repository hasn't been initialized with `wt init` yet

Prerequisite
------------
Before using `wt new`, ensure the repository is initialized:

```bash
wt init
```

This creates the `.wt/` configuration and database required for worktree management.

Primary commands
----------------
```bash
# Create a new worktree with default settings
wt new <name>

# Create from a specific base branch
wt new <name> --base <branch>

# Create with a custom profile configuration
wt new <name> --profile <profile>

# Create and automatically bootstrap the worktree
wt new <name> --bootstrap

# Create and automatically open in tmux/editor
wt new <name> --open

# Create with purpose metadata
wt new <name> --purpose "<description>"

# Full example with all options
wt new feat-auth --base develop --profile ui-dev --bootstrap --open --purpose "Add OAuth2 authentication"
```

Command details:

- `<name>`: Worktree name (required, normalized to `wt/{name}` for the branch)
- `--base <branch>`: Base branch for the new worktree (defaults to `main` or repo default)
- `--profile <profile>`: Use profile-specific configuration from `.wt/config/profiles/*.toml`
- `--bootstrap`: Run bootstrap after creation (venv, env setup, dependencies)
- `--open`: Open the worktree in tmux and launch editor
- `--purpose`: Store purpose metadata in the worktree record

What happens when you run `wt new`
-----------------------------------
1. **Validates and normalizes** the worktree name
2. **Creates database record** for the new worktree
3. **Creates a new branch** named `wt/{name}` from the specified base
4. **Creates the worktree** at `.worktrees/<name>/`
5. **Applies templates** from `.wt/templates/`:
   - `.env` (if missing, from `.wt/templates/env/.env.base`)
   - `.envrc` (if missing, from `.wt/templates/worktree/.envrc`)
   - `.agent/context.md` and `.agent/runbook.md` (if agent enabled)
   - `.opencode/config.json` (if opencode enabled)
6. **Runs post-create hooks** from `.wt/config/hooks.d/post_create.d/`
7. **Optionally bootstraps** the worktree if `--bootstrap` is set
8. **Optionally opens** the worktree if `--open` is set

Error handling
--------------
The command includes robust error handling:

- If creating the worktree with a new branch fails, it falls back to creating the worktree from the current branch without creating a new branch
- Git errors are recorded in the database with proper state transitions
- Invalid worktree names are rejected with a clear error message

Common workflows
----------------

Basic feature worktree
```bash
# Create a new feature worktree from main
wt new feat-auth
cd .worktrees/feat-auth
# Now work in isolated environment
```

Full setup in one command
```bash
# Create, bootstrap, and open in one step
wt new feat-api --bootstrap --open
# This creates the worktree, sets up the environment, and opens it in tmux
```

UI development with profile
```bash
# Use a profile with UI-specific settings (ports, venv, etc.)
wt new feat-dashboard --profile ui-dev --bootstrap --open
```

Hotfix from a release branch
```bash
# Create from a specific base branch for hotfix work
wt new hotfix-login --base release/v1.2.0 --bootstrap
```

Experiment without persistence
```bash
# Quick experiment with purpose metadata
wt new exp-redis-caching --purpose "Test Redis caching layer"
```

Safety checks
-------------
Before running `wt new`:
1. Verify repository is initialized: `wt init` should have been run
2. Check the worktree name doesn't already exist: `wt ls`
3. Ensure base branch exists: `git branch -r` or `git branch`
4. Verify you have write permissions in the repository

After running `wt new`:
1. Verify the worktree was created: `wt ls`
2. Check the branch was created: `git branch` (look for `wt/<name>`)
3. Verify templates were applied: check for `.env`, `.envrc` in the worktree
4. If `--bootstrap` was used, verify the venv exists: `ls -la .venv/`

"Don't do" guardrails
--------------------
- DON'T use `wt new` when you want to work on an existing branch (use `wt add`)
- DON'T use spaces or special characters in the worktree name (will be normalized)
- DON'T forget to run `wt init` first in a new repository
- DON'T create worktrees with names that conflict with existing git branches
- DON'T assume the worktree will be on `main` by default (check `--base`)
- DON'T use `wt new` for worktrees you plan to share (they're local)

Integration with other commands
------------------------------
After creating a worktree:

```bash
# Open it later if you didn't use --open
wt open feat-auth

# Bootstrap it later if you didn't use --bootstrap
wt bootstrap feat-auth

# List all worktrees
wt ls

# Sync with upstream
wt sync feat-auth

# Land the worktree (merge and cleanup)
wt land feat-auth

# Remove when done
wt rm feat-auth
```

Examples
--------

Basic creation
```bash
$ wt new feat-auth
created worktree feat-auth

$ wt ls
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ name       ┃ branch      ┃ status ┃ dirty ┃ sync  ┃ path                     ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ feat-auth  │ wt/feat-auth│ READY  │ no    │ yes   │ .worktrees/feat-auth     │
└────────────┴─────────────┴────────┴───────┴───────┴───────────────────────────┘
```

Creation with base branch
```bash
$ wt new feat-api --base develop
created worktree feat-api

$ git branch
* main
  develop
  wt/feat-api
```

Full setup with all options
```bash
$ wt new feat-dashboard --profile ui-dev --bootstrap --open --purpose "Add dashboard UI"
created worktree feat-dashboard

# Worktree is created, bootstrapped (venv, env), and opened in tmux
```

Template application
```bash
$ wt new feat-test
created worktree feat-test

$ ls .worktrees/feat-test/
.env            .envrc          README.md       src/            .wt/

$ cat .worktrees/feat-test/.wt/config.json
{
  "theme": "copilot",
  "connection": "copilot",
  ...
}
```

Error handling example
```bash
# If base branch doesn't exist or there's a git error
$ wt new broken --base nonexistent
# Command attempts fallback to current branch
# If that fails, exits with error code 5
```

Post-create hooks
```bash
# Hooks run automatically after creation
$ cat .wt/config/hooks.d/post_create.d/00-notify.sh
#!/bin/bash
echo "Worktree created: $1"
```

Database record details
-----------------------
When you run `wt new`, a worktree record is created in the SQLite database:

- `id`: Unique UUID for the worktree
- `name`: Worktree name (e.g., `feat-auth`)
- `path`: Full path to worktree (e.g., `.worktrees/feat-auth`)
- `branch`: Branch name (e.g., `wt/feat-auth`)
- `purpose`: Purpose metadata (if provided)
- `created_at`: Creation timestamp
- `status`: Initial state (READY, ERROR)

You can view records in the TUI: `wt tui` and navigate to the worktree.

Template details
----------------
Templates are applied from `.wt/templates/`:

1. **Environment templates**: `.wt/templates/env/.env.base` → `.env`
2. **Direnv template**: `.wt/templates/worktree/.envrc` → `.envrc`
3. **Agent templates** (if `agent.enabled`):
   - `.wt/templates/agent/context.md` → `.agent/context.md`
   - `.wt/templates/agent/runbook.md` → `.agent/runbook.md`
4. **OpenCode config** (if `opencode.enabled`):
   - `.wt/templates/opencode/{connection}.json` → `.opencode/config.json`
   - Theme is selected automatically from configured themes

Templates are only applied if the target file doesn't exist, preserving manual changes.

Profile-specific behavior
------------------------
Profiles in `.wt/config/profiles/*.toml` can override:

- Base branch selection
- Template paths
- Environment variable keys (ports, etc.)
- Bootstrap behavior
- Hook configurations

Example profile usage:
```bash
# UI development profile with specific ports and services
wt new feat-ui --profile ui-dev
```
