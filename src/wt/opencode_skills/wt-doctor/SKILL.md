---
name: wt-doctor
description: Diagnose and report issues in worktrees, OpenCode config, and templates
---

When to use
-----------
Use `wt doctor` when:
- Worktrees are not behaving as expected
- OpenCode configuration appears broken or missing
- You've recently changed `.wt/config/wt.toml` settings
- After running `wt reindex` to verify everything is healthy
- Before starting work to ensure your environment is clean
- Seeing unexpected errors with worktrees or OpenCode integration

DO NOT use `wt doctor` when:
- You need to actually fix issues (use `wt reindex` or manual repair in TUI)
- Worktree doesn't exist at all (use `wt ls` first)
- Not in a Git repository or `wt` not initialized (run `wt init` first)
- Looking for Git-specific issues (use `git status` or `git worktree` commands)

Primary commands
----------------
```bash
# Run diagnostics on all worktrees
wt doctor

# Run with specific config profile
wt doctor --profile <profile-name>
```

The command checks:
- **OpenCode configuration**: connection setting, themes, template files
- **Worktree paths**: verifies each worktree directory exists
- **Virtual environments**: checks for `.venv` if `env.kind` is configured
- **Git upstream**: verifies each worktree has an upstream branch set

Common workflows
----------------

Checking health before work
```bash
# Verify everything is in good shape
wt doctor

# If no issues, proceed with work
wt open feat-x
```

Diagnosing OpenCode issues
```bash
# Run doctor to identify OpenCode config problems
wt doctor

# Typical output for OpenCode issues:
# opencode: connection not set in .wt/config/wt.toml
# opencode: no themes configured for codex
# opencode: missing template .wt/templates/opencode/codex.json

# Fix OpenCode config in .wt/config/wt.toml
# Then re-run doctor
wt doctor
```

After config changes
```bash
# You modified .wt/config/wt.toml
# Run doctor to check for issues
wt doctor

# Run TUI doctor with automatic OpenCode repair (press 'd' in TUI)
wt tui
# Press 'd' to run doctor (this also repairs OpenCode configs)
```

Troubleshooting missing worktrees
```bash
# Run doctor to find broken worktrees
wt doctor

# Output might show:
# feat-x: missing path
# feat-y: missing venv

# Repair missing worktree path:
wt reindex  # Syncs DB with actual Git worktrees

# If worktree is truly missing, remove from DB and recreate:
wt rm feat-x
wt add feat-x --branch feat-x
```

Safety checks
-------------
Before running `wt doctor`:
1. Verify you're in a Git repository with `wt` initialized
2. Check that `.wt/config/wt.toml` exists (run `wt init` if not)
3. Understand that `wt doctor` only REPORTS issues, it doesn't fix them

After running `wt doctor`:
1. Review each issue and understand what it means
2. For OpenCode issues: check `.wt/config/wt.toml` and `.wt/templates/opencode/`
3. For missing paths: run `wt reindex` or `wt add` to recreate worktrees
4. For missing venv: run `wt bootstrap <name>` to create it

"Don't do" guardrails
--------------------
- DON'T expect `wt doctor` to automatically fix issues (use TUI for automatic OpenCode repair)
- DON'T run `wt doctor` without understanding what the issues mean before fixing
- DON'T ignore OpenCode config issues—they break agent integration
- DON'T run doctor inside a worktree (run from repo root)
- DON'T use `wt doctor` to diagnose Git-specific problems (use `git worktree list`)

Examples
--------

Clean run - no issues
```bash
$ wt doctor
no issues found
```

OpenCode configuration issues
```bash
$ wt doctor
opencode: connection not set in .wt/config/wt.toml
opencode: no themes configured for codex
opencode: missing template .wt/templates/opencode/codex.json

# Fix: Edit .wt/config/wt.toml to set opencode.connection and themes
# Fix: Create or ensure template file exists at .wt/templates/opencode/codex.json
```

Missing worktree paths
```bash
$ wt doctor
feat-x: missing path
feat-y: missing path

# This means the worktree path in DB doesn't match filesystem
# Usually after manual deletion or moving worktree directories

# Fix: Reindex to sync DB with actual worktrees
wt reindex

# Or remove from DB and recreate
wt rm feat-x
wt add feat-x --branch wt/feat-x
```

Missing virtual environments
```bash
$ wt doctor
feat-api: missing venv
feat-ui: missing venv

# This means env.kind is set but .venv doesn't exist
# Usually after creating worktree without --bootstrap

# Fix: Bootstrap the worktrees
wt bootstrap feat-api
wt bootstrap feat-ui
```

No upstream branch
```bash
$ wt doctor
feat-x: no upstream

# This means the branch isn't tracking a remote branch
# Fix by pushing or setting upstream
cd .worktrees/feat-x
git push -u origin wt/feat-x

# Or from repo root:
cd .worktrees/feat-x && git branch --set-upstream-to=origin/wt/feat-x wt/feat-x
```

Mixed issues
```bash
$ wt doctor
opencode: missing template .wt/templates/opencode/codex.json
feat-x: missing path
feat-y: missing venv
old-feature: no upstream

# Address each issue:
# 1. Fix OpenCode template (check .wt/templates/opencode/)
# 2. Reindex to sync worktree paths: wt reindex
# 3. Bootstrap missing venv: wt bootstrap feat-y
# 4. Set upstream for old branch: cd .worktrees/old-feature && git push -u origin wt/old-feature
```

Automatic repair in TUI
```bash
# Open TUI and press 'd' to run doctor with automatic OpenCode repair
wt tui
# Press 'd' key
# Output: opencode: updated 3 worktree(s)
# Output: No issues found.

# Note: TUI doctor automatically calls repair_opencode() before checking
# This only repairs OpenCode config templates, not other issues
```

What gets checked
-----------------

OpenCode issues
- Connection not set in `.wt/config/wt.toml` (`opencode.connection`)
- No themes configured for the connection
- Missing template file at `.wt/templates/opencode/{connection}.json`

Worktree integrity
- Worktree path exists on filesystem
- Virtual environment exists if `env.kind` is configured
- Git upstream branch is set

What doctor does NOT fix
-------------------------
- Missing worktree paths (use `wt reindex` or `wt add`)
- Missing virtual environments (use `wt bootstrap`)
- No upstream branch (use `git push -u`)
- Missing templates (create manually or restore from version control)

Related commands
----------------
```bash
# Initialize wt in a new repo
wt init

# Reindex worktrees (syncs DB with Git)
wt reindex

# Bootstrap a worktree (creates venv, .env, runs templates)
wt bootstrap <name>

# TUI with automatic OpenCode repair
wt tui  # Press 'd' for doctor with repair

# List all worktrees
wt ls
```
