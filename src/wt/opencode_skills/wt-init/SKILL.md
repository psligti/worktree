---
name: wt-init
description: Initialize .wt configuration, templates, and database for a Git worktree repo
---

When to use
-----------
Use `wt init` when:
- Starting to use `wt` in a new Git repository
- Setting up worktree management for the first time in a repo
- After cloning a repo that uses `wt` but the `.wt/` directory is missing
- Re-initializing after deleting `.wt/` directory (safe to re-run)

DO NOT use `wt init` when:
- Already initialized in the current repo (it's safe but unnecessary)
- Working in a non-Git repository (will fail to find repo root)
- Trying to migrate between `wt` versions (use `wt reindex` instead)

Primary commands
----------------
```bash
# Initialize .wt configuration and database in current repo
wt init
```

The command:
- Creates `.wt/` directory structure at repo root
- Generates default config files and templates
- Initializes SQLite database at `.wt/state/wt.db`
- Updates `.gitignore` with `.wt/` entries

Common workflows
----------------

First-time setup
```bash
# In your Git repository
git clone https://github.com/user/repo.git
cd repo
wt init
wt new feat-x --bootstrap --open
```

Recovering deleted config
```bash
# .wt/ directory accidentally deleted
wt init  # Re-creates all missing files
```

Fresh start in existing repo
```bash
# Want to reset to default configuration
rm -rf .wt/
wt init  # Fresh default setup
```

Safety checks
-------------
Before running `wt init`:
1. Verify you're in a Git repository (`git rev-parse --show-toplevel`)
2. Check `.wt/` doesn't already exist (or you're okay with skipping existing files)
3. Ensure you have write permissions in the repository root

After running `wt init`:
1. Verify `.wt/config/wt.toml` exists
2. Verify `.wt/state/wt.db` was created
3. Check `.gitignore` contains `.wt/state/`, `.wt/logs/`, `.wt/cache/`, `.worktrees/`

"Don't do" guardrails
--------------------
- DON'T run `wt init` inside a subdirectory of a Git repo (it finds the root automatically)
- DON'T expect it to modify existing `.wt/` files (it only creates missing files)
- DON'T use it to upgrade configurations (edit files manually or use version control)
- DON'T run as a different user than the repo owner (permission issues may occur)

Examples
--------

Basic initialization
```bash
$ cd my-repo
$ wt init
initialized .wt configuration and database
```

What gets created
```
.wt/
├── config/
│   ├── wt.toml                    # Main config
│   ├── profiles/
│   │   ├── default.toml
│   │   ├── ui-dev.toml
│   │   └── agent.toml
│   └── hooks.d/
│       ├── post_create.d/
│       ├── post_switch.d/
│       ├── pre_remove.d/
│       └── run_checks.d/
├── templates/
│   ├── env/
│   │   └── .env.base
│   ├── agent/
│   │   ├── context.md
│   │   └── runbook.md
│   ├── opencode/
│   │   ├── codex.json
│   │   └── copilot.json
│   └── worktree/
│       └── .envrc
└── state/
    └── wt.db                     # SQLite database
```

Idempotent behavior (safe to re-run)
```bash
$ wt init
initialized .wt configuration and database

$ wt init  # Run again - no changes to existing files
initialized .wt configuration and database

$ # If you delete specific files, they get recreated
$ rm .wt/config/wt.toml
$ wt init  # Only wt.toml is recreated
initialized .wt configuration and database
```

Integration with `.gitignore`
```bash
$ cat .gitignore
...existing entries...
.wt/state/
.wt/logs/
.wt/cache/
.worktrees/
```
