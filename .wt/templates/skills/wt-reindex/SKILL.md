---
name: wt-reindex
description: Rebuild the SQLite database cache by scanning all git worktrees and computing sync state
---

When to use
-----------
Use `wt reindex` when:
- The SQLite database at `.wt/state/wt.db` is corrupted or out of sync with git
- Worktrees were added/removed manually via git commands (not through `wt`)
- After switching between branches or major git operations that affect worktrees
- Git sync state appears incorrect in `wt ls` output
- Database errors occur when running other `wt` commands
- After restoring from a backup where worktree state may be inconsistent

DO NOT use `wt reindex` when:
- Database is already accurate (waste of time, though safe to run)
- Looking for a specific worktree (use `wt ls` or `wt tui` instead)
- Trying to recover deleted worktrees (reindex only marks them as absent)
- Want to modify worktree metadata (use `wt purpose` or other specific commands)

Primary commands
----------------
```bash
# Rebuild the entire database cache from git worktree list
wt reindex

# Rebuild database using a specific config profile
wt reindex --profile ui-dev
```

The command:
- Runs `git worktree list --porcelain -z` to discover all worktrees
- Scans each worktree for: path, HEAD SHA, branch, detached state, lock state
- Computes sync state: upstream, ahead/behind counts, behind_main, git_dirty
- Preserves existing metadata: purpose, bootstrap, agent, runtime, created_at
- Marks worktrees missing from git as "absent" in database
- Records sync state change events (when git_sync changes to DIVERGED or BEHIND_MAIN)
- Updates `updated_at` timestamp for all processed worktrees

Common workflows
----------------

Recover from manual worktree changes
```bash
# Added worktree manually with git worktree add
git worktree add .worktrees/manual-feat main

# Database doesn't know about it
wt ls  # Shows only wt-managed worktrees

# Reindex to sync database with git
wt reindex
wt ls  # Now shows manual-feat
```

Fix corrupted database
```bash
# Database errors appearing
wt ls
Error: database is locked or corrupted

# Reindex rebuilds from git source of truth
wt reindex
reindexed 3 worktrees

# Database is now fresh and accurate
wt ls
```

After major git operations
```bash
# Performed branch deletions, rebases, or remote updates
git fetch --all
git branch -d wt/old-feature

# Database may have stale references
wt reindex
reindexed 2 worktrees  # old-feature marked absent
```

Sync with profile changes
```bash
# Modified .wt/config/wt.toml worktree settings
# Changed default_base from main to develop

# Reindex picks up new configuration
wt reindex --profile updated-config
reindexed 5 worktrees
```

Safety checks
-------------
Before running `wt reindex`:
1. Verify you're in a Git repository (`wt init` must have been run first)
2. No long-running git operations in progress (worktree list may block)
3. Network is available if tracking remote branches (needed for sync state)

Performance considerations:
- Scans all worktrees via git porcelain - can take 1-5 seconds per 100 worktrees
- Computes sync state for each worktree (upstream lookups, ahead/behind counts)
- Large repos with many worktrees may take longer to reindex

After running `wt reindex`:
1. Verify worktree count matches expectation (`git worktree list | wc -l`)
2. Check `wt ls` output for correct sync states
3. Review any worktrees marked as "absent" (may need manual cleanup)

"Don't do" guardrails
--------------------
- DON'T interrupt a running reindex (may leave database in inconsistent state)
- DON'T assume database is correct before reindexing (always verify with `wt ls`)
- DON'T use `wt reindex` to create worktrees (use `wt new` or `wt add`)
- DON'T expect reindex to restore deleted worktrees (git worktree list won't show them)
- DON'T run multiple concurrent `wt reindex` commands (database lock contention)
- DON'T rely on reindex to fix git errors (it only rebuilds the cache)
- DON'T use reindex to modify metadata (use `wt purpose` for that)

Examples
--------

Basic reindex
```bash
$ cd my-repo
$ wt reindex
reindexed 4 worktrees
```

With custom profile
```bash
$ wt reindex --profile agent-dev
reindexed 7 worktrees
```

Recovering from manual worktree operations
```bash
# Manually added worktree outside wt
$ git worktree add ../external-feat feat-branch
Preparing worktree (new branch 'feat-branch')

# wt doesn't know about it
$ wt ls
[Shows only wt-managed worktrees]

# Reindex brings it into database
$ wt reindex
reindexed 5 worktrees

# Now it's tracked
$ wt ls
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ name       ┃ branch              ┃ status     ┃ dirty ┃ sync  ┃ path                        ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ external-feat │ feat-branch       │ READY      │ no    │ ✓     │ ../external-feat            │
└────────────┴─────────────────────┴────────────┴───────┴───────┴──────────────────────────────┘
```

Sync state recalculation
```bash
# Sync state seems off
$ wt ls
name    | branch    | sync
feat-x  | wt/feat-x | ✓ (actually 3 commits behind)

# Force recalculation
$ wt reindex
reindexed 1 worktrees

# Sync state is now accurate
$ wt ls
name    | branch    | sync
feat-x  | wt/feat-x | -3 (BEHIND_MAIN)
```

Marking absent worktrees
```bash
# Deleted worktree via git
$ git worktree remove .worktrees/old-feature

# Database still shows it
$ wt ls
name        | branch    | lifecycle
old-feature | wt/old    | READY

# Reindex marks as absent
$ wt reindex
reindexed 2 worktrees

# Now correctly marked
$ wt ls
name        | branch    | lifecycle
old-feature | wt/old    | ABSENT
```

Integration with other commands
```bash
# Workflow: reindex before operations
$ wt reindex && wt sync feat-x --strategy rebase
reindexed 5 worktrees
synced feat-x from origin/main

# Reindex to ensure fresh data before status checks
$ wt reindex
reindexed 3 worktrees
$ wt doctor
no issues found

# Reindex after external changes
$ git fetch --all
$ git worktree prune
$ wt reindex
reindexed 4 worktrees
```

What gets rebuilt
-----------------
The reindex operation rebuilds the entire SQLite cache from git:

1. **Worktree discovery** (from `git worktree list`):
   - path
   - head_sha
   - branch (if attached)
   - detached (bool)
   - locked (bool)
   - prunable (bool)

2. **Sync state computation** (per worktree):
   - upstream (from `git rev-parse --abbrev-ref @{u}`)
   - ahead (commits ahead of upstream)
   - behind (commits behind upstream)
   - behind_main (commits behind default base branch)
   - git_sync (derived state: UP_TO_DATE, AHEAD_MAIN, BEHIND_MAIN, DIVERGED, NO_UPSTREAM)
   - git_dirty (from `git status --porcelain`)

3. **Preserved metadata** (from existing database records):
   - purpose (free-form description)
   - bootstrap (UNBOOTSTRAPPED, BOOTSTRAPPED, FAILED)
   - agent (ATTACHED, DETACHED)
   - runtime (STOPPED, RUNNING, CRASHED)
   - created_at (original creation timestamp)
   - last_accessed_at (last opened/attached timestamp)
   - last_error (most recent error message)

4. **Event recording** (sync state changes only):
   - Records `SyncOutOfDate` events when git_sync changes to DIVERGED or BEHIND_MAIN
   - Captures previous state, new state, and timestamp

Prerequisite
------------
`wt reindex` requires `wt init` to have been run first. The command will fail if:
- `.wt/` directory doesn't exist
- `.wt/state/wt.db` database doesn't exist
- Not inside a Git repository

Always run `wt init` before first use of `wt reindex`.
