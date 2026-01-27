---
name: wt-add
description: Add a worktree for an existing branch in the repository
---

When to use
-----------
Use `wt add` when:
- You have an existing branch you want to work on in a separate worktree
- You want to create a named worktree for a feature/bugfix branch created elsewhere
- Switching between branches without checking out/stashing in your main worktree
- You need to review or work on someone else's branch
- You have a remote branch that needs local worktree setup

DO NOT use `wt add` when:
- Creating a new branch from scratch (use `wt new` instead)
- The branch doesn't exist yet (create it first or use `wt new`)
- You want to clone from an existing worktree (use `wt clone` instead)
- Branch doesn't exist locally or remotely (Git will fail)

Prerequisite
------------
`wt add` requires `wt init` to have been run in the repository first.

Primary commands
----------------
```bash
# Basic usage: add a worktree for an existing branch
wt add <name> --branch <branch-name>

# With bootstrap and open flags
wt add <name> --branch <branch-name> --bootstrap --open

# With profile and purpose
wt add <name> --branch <branch-name> --profile <profile> --purpose "Description"

# Add worktree for remote branch (git fetch first)
git fetch origin <branch-name>
wt add my-work --branch origin/<branch-name>
```

Required flags:
- `--branch <branch-name>`: The existing branch to checkout (required)

Optional flags:
- `--profile <profile>`: Use a specific configuration profile from `.wt/config/profiles/`
- `--bootstrap`: Automatically bootstrap the worktree (venv, env, templates) after creation
- `--open`: Open the worktree in tmux with configured layout after creation
- `--purpose <description>`: Add purpose metadata to the worktree

Common workflows
----------------

Adding a worktree for existing feature branch
```bash
# Branch already exists locally or remotely
wt add auth-refactor --branch feature/auth-refactor
added worktree auth-refactor from feature/auth-refactor
```

Adding with full setup (bootstrap and open)
```bash
wt add api-cleanup --branch feature/api-cleanup --bootstrap --open
# Creates worktree, applies templates, sets up venv/env, and opens in tmux
```

Adding remote branch after fetch
```bash
# Remote branch exists but not checked out locally
git fetch origin
wt add pr-123 --branch origin/pr-123
added worktree pr-123 from origin/pr-123
```

Adding with purpose metadata
```bash
wt add fix-login --branch bugfix/login-issue --purpose "Fix login timeout error"
added worktree fix-login from bugfix/login-issue
```

Using a specific profile
```bash
# Worktree needs different config (e.g., database isolation)
wt add db-migration --branch feature/db-migration --profile postgres
added worktree db-migration from feature/db-migration
```

What happens when you run `wt add`
----------------------------------
1. Normalizes worktree name (removes invalid characters)
2. Creates worktree directory under `.worktrees/<name>/`
3. Creates database record for the worktree
4. Calls `git worktree add` with the specified existing branch
5. Applies templates from `.wt/templates/`:
   - `.env.base` → `.env` (if missing)
   - `.envrc` (direnv) (if missing)
   - Agent templates (`context.md`, `runbook.md`) if agent enabled
   - OpenCode config if opencode enabled
6. Runs `post_create` hooks from config
7. If `--bootstrap` flag: runs bootstrap (creates venv, sets up env)
8. If `--open` flag: opens in tmux with configured layout

Safety checks
-------------
Before running `wt add`:
1. Verify `wt init` has been run in the repository
2. Confirm the branch exists (run `git branch -a` to see all branches)
3. Ensure the worktree name doesn't already exist (run `wt ls`)
4. Check you have write permissions in the repo root
5. Verify `.wt/` directory is not excluded by `.gitignore` for tracked branches

After running `wt add`:
1. Verify worktree appears in `wt ls`
2. Check the worktree directory exists: `.worktrees/<name>/`
3. Confirm the correct branch is checked out in the new worktree
4. Verify templates were applied (`.env`, `.envrc`, `.agent/`, `.opencode/`)
5. Test that you can navigate and work in the worktree

"Don't do" guardrails
--------------------
- DON'T use `wt add` for creating new branches (use `wt new` instead)
- DON'T specify a branch that doesn't exist (Git error: invalid branch name)
- DON'T reuse an existing worktree name (error: path already exists)
- DON'T forget `--branch` flag (it's required, not optional)
- DON'T use `wt add` inside a worktree (run from repo root)
- DON'T assume remote branches are available without `git fetch` first
- DON'T expect `wt add` to create a new branch (it only adds existing ones)
- DON'T use special characters in worktree name (normalized, but keep it simple)

Examples
--------

Basic example
```bash
$ wt add auth-updates --branch feature/auth-updates
added worktree auth-updates from feature/auth-updates

$ wt ls
name            branch                      status  path
auth-updates    feature/auth-updates        READY   .worktrees/auth-updates
```

With bootstrap and open
```bash
$ wt add payment-gateway --branch feature/payment-gateway --bootstrap --open
added worktree payment-gateway from feature/payment-gateway

# Worktree is now:
# - Created at .worktrees/payment-gateway/
# - Bootstrapped with venv and env setup
# - Opened in tmux with configured layout
```

Adding remote branch
```bash
# First fetch to get remote branch info
$ git fetch origin
remote: Counting objects: 42, done.
remote: Compressing objects: 100% (15/15), done.
remote: Total 42 (delta 27), reused 34 (delta 20)
...

# Now add worktree for remote branch
$ wt add pr-456 --branch origin/pr-456
added worktree pr-456 from origin/pr-456
```

Error case: branch doesn't exist
```bash
$ wt add my-feature --branch nonexistent-branch
error: invalid branch: 'nonexistent-branch'
exit code 5
```

Error case: worktree already exists
```bash
$ wt add existing --branch feature/existing
error: worktree path already exists: .worktrees/existing
exit code 2
```

Error case: missing required flag
```bash
$ wt add my-worktree
Error: Missing option '--branch'.
Usage: wt add [OPTIONS] NAME
  ...
```

Template verification
```bash
$ wt add template-test --branch feature/test
added worktree template-test from feature/test

$ ls -la .worktrees/template-test/
.env          # Created from template if missing
.envrc       # Created from template if missing
.git         # Git worktree link
.opencode/    # Created if opencode enabled
.agent/       # Created if agent enabled
```

Difference between `wt add` and `wt new`
---------------------------------------
`wt add`: Adds worktree for EXISTING branch
- Branch must already exist (locally or remotely)
- Use when working on someone else's branch or branch created outside `wt`
- Required flag: `--branch <existing-branch>`

`wt new`: Creates NEW branch and worktree
- Creates new branch (defaults to `wt/<name>`)
- Use when starting fresh work
- Optional flag: `--base <base-branch>` (defaults to main/master)

Integration with other commands
--------------------------------
After adding a worktree, you can:
- `wt open <name>`: Open in tmux (if not opened with `--open`)
- `wt bootstrap <name>`: Bootstrap manually (if not done with `--bootstrap`)
- `wt purpose <name> <description>`: Set purpose metadata
- `wt sync <name>`: Sync worktree with upstream
- `wt rm <name>`: Remove worktree when done
- `wt ls`: List all worktrees to verify
