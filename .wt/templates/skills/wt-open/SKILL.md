---
name: wt-open
description: Open an existing worktree in tmux with configured layout and optionally launch editor
---

When to use
-----------
Use `wt open` when:
- You have an existing worktree created via `wt new` or `wt add`
- You want to switch to a worktree in tmux with a specific layout
- You need to open an editor (e.g., PyCharm, VS Code) for a worktree
- Returning to work on a previously created worktree
- You want to run `post_switch` hooks before working on a worktree

DO NOT use `wt open` when:
- The worktree doesn't exist yet (use `wt new` or `wt add` to create it first)
- You're not in a `wt`-initialized repository (run `wt init` first)
- You only want to list worktrees (use `wt ls` instead)
- tmux is not available or desired (you can still cd into the worktree directly)

Prerequisites
-------------
`wt open` requires:
1. `wt init` has been run in the repository
2. The worktree exists (created via `wt new` or `wt add`)
3. tmux is installed and available (if using `prefer_tmux` config)
4. Configured layout exists in `.wt/config/wt.toml` (if using `--layout`)

Primary commands
----------------
```bash
# Basic usage: open worktree with default layout and editor
wt open <name>

# Open with specific layout
wt open <name> --layout three-pane

# Open without launching editor
wt open <name> --no-editor

# Open with specific config profile
wt open <name> --profile <profile>

# Combine flags
wt open <name> --layout two-pane --no-editor --profile postgres
```

Required arguments:
- `<name>`: The worktree name to open

Optional flags:
- `--layout <layout>`: Override default layout (must exist in config)
- `--editor/--no-editor`: Enable/disable editor launch (default: `--editor`)
- `--profile <profile>`: Use specific configuration profile

Common workflows
----------------

Open with default layout
```bash
# Uses default_layout from config (default: "single")
wt open feat-auth
opened feat-auth in tmux session repo (window: repo/wt/feat-auth)
```

Open with multi-pane layout
```bash
# Assumes [tmux.layouts.two-pane] exists in config
wt open api-refactor --layout two-pane
opened api-refactor in tmux session repo (window: repo/wt/api-refactor)
```

Open without editor
```bash
# Useful when you already have the worktree open in your editor
wt open frontend-update --no-editor
opened frontend-update in tmux session repo (window: repo/wt/frontend-update)
```

Using different profiles
```bash
# Profile may have different default layout or editor_cmd
wt open db-migration --profile postgres
opened db-migration in tmux session repo (window: repo/wt/db-migration)
```

Re-attaching to existing window
```bash
# If window already exists, attaches without re-applying layout
wt open feat-x  # First time
opened feat-x in tmux session repo (window: repo/wt/feat-x)

# Later, open again - attaches to existing window
wt open feat-x
attached to feat-x in tmux session repo (window: repo/wt/feat-x)
```

What happens when you run `wt open`
-----------------------------------
1. Loads configuration from `.wt/config/wt.toml` (or profile)
2. Reindexes worktrees from Git to get current state
3. Finds worktree record by name in database
4. Runs `post_switch` hooks from config
5. Resolves layout name (uses `--layout` flag or `default_layout` from config)
6. Creates or finds tmux session (defaults to "repo" or project basename)
7. Creates or attaches to tmux window with unique name:
   - Format: `{project}/{branch or purpose or name}`
8. If new window: applies layout configuration:
   - Splits panes according to layout spec
   - Runs startup commands for named panes
   - Sets pane titles for identification
9. Focuses the window in tmux
10. Updates worktree's `last_accessed_at` timestamp in database
11. If `--editor`: launches configured editor (from `editor_cmd` in config)
12. Outputs confirmation message

Layout configuration
-------------------
Layouts are defined in `.wt/config/wt.toml` under `[tmux.layouts.<name>]`:

```toml
[tmux]
session = "repo"
default_layout = "single"

[tmux.layouts.single]
layout = "even-horizontal"
panes = ["shell"]

[tmux.layouts.two-pane]
layout = "even-horizontal"
panes = ["shell", "api"]
commands = { api = "uv run api:dev" }

[tmux.layouts.three-pane]
layout = "main-vertical"
panes = ["shell", "api", "ui"]
commands = { api = "uv run api:dev", ui = "uv run ui:dev" }
```

Layout options:
- `layout`: tmux layout string (e.g., "even-horizontal", "main-vertical", "tiled")
- `panes`: list of pane names (used for titles and command lookup)
- `commands`: optional mapping of pane names to startup commands

Editor configuration
---------------------
Editor is configured in `.wt/config/wt.toml` under `[open]`:

```toml
[open]
editor_cmd = ["pycharm"]
prefer_tmux = true
```

Common editors:
- `["pycharm"]` - JetBrains PyCharm
- `["code"]` - VS Code
- `["vim"]` - Vim
- `["nvim"]` - Neovim
- `["subl"]` - Sublime Text

Safety checks
-------------
Before running `wt open`:
1. Verify `wt init` has been run in the repository
2. Confirm worktree exists (run `wt ls` to list all worktrees)
3. Check that tmux is installed (if `prefer_tmux` is true in config)
4. Verify layout exists in config (if using `--layout` flag)
5. Ensure you have write permissions for database updates

After running `wt open`:
1. Verify tmux session exists (`tmux ls`)
2. Check that window was created/attached in tmux
3. Confirm editor launched (if `--editor` was used)
4. Verify worktree `last_accessed_at` was updated
5. Test that you can work in the opened panes

"Don't do" guardrails
--------------------
- DON'T use `wt open` on non-existent worktrees (run `wt ls` first)
- DON'T use it before `wt init` (configuration will be missing)
- DON'T specify a layout that doesn't exist in config (error: unknown layout)
- DON'T expect `wt open` to create a worktree (use `wt new` or `wt add`)
- DON'T use it inside a worktree (run from repo root)
- DON'T assume tmux window will be re-layouted (layout only applies to new windows)
- DON'T run without tmux installed if `prefer_tmux` is enabled
- DON'T forget that `post_switch` hooks run before opening (they may fail)

Examples
--------

Basic open with default settings
```bash
$ wt open feat-login
opened feat-login in tmux session repo (window: repo/wt/feat-login)
```

Open with custom layout
```bash
# Using three-pane layout for full development environment
$ wt open feature/auth --layout three-pane
opened feature/auth in tmux session repo (window: repo/wt/feature/auth)
```

Open without editor
```bash
# Already have project open in IDE, just need tmux
$ wt open bug-fix --no-editor
opened bug-fix in tmux session repo (window: repo/bug-fix)
```

Re-attach to existing window
```bash
# First time: creates new window with layout
$ wt open api-work
opened api-work in tmux session repo (window: repo/wt/api-work)

# Later: attaches to existing window
$ wt open api-work
attached to api-work in tmux session repo (window: repo/wt/api-work)
```

Error case: worktree doesn't exist
```bash
$ wt open nonexistent
error: worktree not found: nonexistent
exit code 2
```

Error case: layout doesn't exist
```bash
$ wt open feat-x --layout invalid-layout
error: unknown layout: invalid-layout
exit code 2
```

Error case: not initialized
```bash
$ wt open my-worktree
error: .wt not found
exit code 1
```

Tmux session behavior
```bash
# Default session name is "repo" or project basename
$ wt open feat-x
opened feat-x in tmux session repo (window: repo/wt/feat-x)

# Check tmux sessions
$ tmux ls
repo: 1 windows

# The window name format is {project}/{branch or purpose or name}
$ tmux list-windows -t repo
repo/wt/feat-x: 1 panes [100x40]
```

Layout with startup commands
```bash
# Config has commands for api and ui panes
[tmux.layouts.dev]
layout = "main-vertical"
panes = ["shell", "api", "ui"]
commands = { api = "uv run api:dev", ui = "uv run ui:dev" }

$ wt open dev-work --layout dev
opened dev-work in tmux session repo (window: repo/wt/dev-work)

# Panes api and ui will automatically start their services
```

Integration with other commands
--------------------------------
Before `wt open`:
- `wt new <name> --open`: Creates and opens in one command
- `wt add <name> --branch <branch> --open`: Adds and opens in one command
- `wt ls`: List worktrees to find the right name

After `wt open`:
- `wt bootstrap <name>`: If worktree not bootstrapped yet
- `wt sync <name>`: Sync with upstream changes
- `wt land <name>`: Merge and cleanup when done
- `wt rm <name>`: Remove worktree when no longer needed
- `wt tmux next-waiting`: Jump to next waiting pane across worktrees

Tmux integration
---------------
The `wt open` command integrates with tmux status line:
- Window names follow pattern: `{project}/{branch or purpose or name}`
- Pane titles are set to `{window}:{pane-name}` for identification
- `wt tmux status-line` shows aggregate status of all worktree panes
- `wt tmux next-waiting` jumps to the next pane waiting for input

Add to `~/.tmux.conf`:
```
set -g status-right "#(wt tmux status-line)"
bind-key W run-shell "wt tmux next-waiting"
```
