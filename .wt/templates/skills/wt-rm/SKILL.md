---
name: wt-rm
description: Remove a worktree with safety checks for dirty/unpushed branches
---

When to use
-----------
Use `wt rm` when:
- You're finished with a worktree and want to clean it up
- A feature branch has been merged and the worktree is no longer needed
- You want to reclaim disk space from completed work
- An experimental worktree is no longer required
- After `wt land` or merging a branch and you're ready to remove the worktree

DO NOT use `wt rm` when:
- The worktree contains uncommitted work you want to keep (commit or stash first)
- The branch has unpushed commits that should be preserved (push first or use `--force`)
- You're still actively working in that worktree
- You want to keep the branch but remove the worktree (use `git branch -D` separately)
- The worktree is locked by another process (check `wt locks`)

Prerequisite
------------
`wt rm` requires `wt init` to have been run in the repository first.

Primary commands
----------------
```bash
# Remove a clean, up-to-date worktree
wt rm <name>

# Remove a dirty or unpushed worktree (requires --force)
wt rm <name> --force

# Remove with specific profile
wt rm <name> --force --profile <profile>
```

Required arguments:
- `<name>`: The worktree name to remove

Optional flags:
- `--force`: Override safety checks (dirty/unpushed/locked)
- `--profile <profile>`: Use a specific configuration profile from `.wt/config/profiles/`

Common workflows
----------------

Removing a clean, merged worktree
```bash
# Branch has been merged, worktree is clean and up-to-date
wt rm auth-refactor
removed worktree auth-refactor
```

Removing with unpushed commits
```bash
# Worktree has unpushed commits - refused by default
$ wt rm api-changes
refusing to remove api-changes: unpushed commits
exit code 4

# Override with --force if you're sure
$ wt rm api-changes --force
removed worktree api-changes
```

Removing a dirty worktree
```bash
# Worktree has uncommitted changes - refused by default
$ wt rm fix-login
refusing to remove fix-login: dirty worktree
exit code 4

# Commit or stash changes first, then remove
$ cd .worktrees/fix-login
$ git commit -am "WIP"
$ cd ../..
$ wt rm fix-login
removed worktree fix-login

# Or force remove if you're certain
$ wt rm fix-login --force
removed worktree fix-login
```

After successful merge and land
```bash
# Branch has been merged via PR or wt land
$ wt land feature/payment --cleanup
# This handles branch deletion, but worktree remains

# Remove the worktree
$ wt rm payment
removed worktree payment
```

Checking before removal
```bash
# Check worktree status before removing
$ wt ls
name       branch                      status  dirty  sync
api-test   feature/api-test           READY   no     ok
db-migrate feature/db-migrate         READY   yes    ok

# Only remove clean worktrees without force
$ wt rm api-test
removed worktree api-test

# db-migrate requires force (dirty)
$ wt rm db-migrate --force
removed worktree db-migrate
```

What happens when you run `wt rm`
---------------------------------
1. Reindexes worktrees to get current state
2. Checks safety configuration in `.wt/config/wt.toml`:
   - If `refuse_remove_if_dirty = true` (default): refuses dirty worktrees without `--force`
   - If `refuse_remove_if_unpushed = true` (default): refuses unpushed commits without `--force`
3. Runs `pre_remove` hooks from config before removal
4. Calls `git worktree remove` to delete the worktree
5. Records removal event in database
6. Updates worktree state to "ABSENT"

Safety checks
-------------
Before running `wt rm`:
1. Check `wt ls` to verify the worktree exists and its status
2. Verify `git_dirty` status (dirty worktrees require `--force`)
3. Check if branch is ahead of upstream (unpushed commits require `--force`)
4. Run `wt locks` to see if worktree is locked (locks don't prevent removal but you should verify)
5. Ensure you have the correct worktree name (name matching is exact)
6. Check that no processes are using files in the worktree directory

Safety configuration
---------------------
Safety checks are controlled by `.wt/config/wt.toml`:

```toml
[safety]
refuse_remove_if_dirty = true     # Default: refuse dirty worktrees
refuse_remove_if_unpushed = true  # Default: refuse unpushed branches
```

- If `refuse_remove_if_dirty = true` (default):
  - Worktrees with uncommitted changes are refused without `--force`
  - Exit code 4: "refusing to remove {name}: dirty worktree"
- If `refuse_remove_if_unpushed = true` (default):
  - Worktrees with unpushed commits are refused without `--force`
  - Exit code 4: "refusing to remove {name}: unpushed commits"

Override safety checks by using `--force` flag (only if you understand the consequences).

After running `wt rm`:
1. Verify worktree no longer appears in `wt ls`
2. Confirm directory was removed: `.worktrees/<name>/` should be gone
3. Check that `git worktree list` no longer shows the worktree
4. Verify database recorded the removal event (check logs if needed)

Exit codes
----------
- Exit code 4: Safety check refused (dirty or unpushed, use `--force` to override)
- Exit code 5: Git error during worktree removal

"Don't do" guardrails
--------------------
- DON'T use `--force` without understanding you'll lose uncommitted work or unpushed commits
- DON'T remove a worktree while processes are using it (file locks, editors, tmux sessions)
- DON'T assume `wt rm` deletes the branch (it only removes the worktree, branch remains)
- DON'T use `wt rm` to switch between worktrees (use `wt open` instead)
- DON'T remove a worktree you're currently in (navigate away first)
- DON'T rely on `--force` as a shortcut for proper cleanup (commit, push, or stash intentionally)
- DON'T remove worktrees with important uncommitted work without verification
- DON'T use `wt rm` if you want to keep the branch (use `git worktree remove` + `git branch -D` separately)

Examples
--------

Basic removal (clean worktree)
```bash
$ wt ls
name       branch                  status  dirty  sync
feat-x     wt/feat-x               READY   no     ok

$ wt rm feat-x
removed worktree feat-x

$ wt ls
# feat-x no longer appears
```

Refused: dirty worktree
```bash
$ wt ls
name       branch                  status  dirty  sync
feat-y     wt/feat-y               READY   yes    ok

$ wt rm feat-y
refusing to remove feat-y: dirty worktree
exit code 4

# Fix: commit or stash changes first
$ cd .worktrees/feat-y
$ git stash
$ cd ../..
$ wt rm feat-y
removed worktree feat-y
```

Refused: unpushed commits
```bash
$ wt ls
name       branch                  status  dirty  sync
feat-z     wt/feat-z               READY   no     2 ahead

$ wt rm feat-z
refusing to remove feat-z: unpushed commits
exit code 4

# Fix: push commits first or use --force if you're certain
$ cd .worktrees/feat-z
$ git push origin feat-z
$ cd ../..
$ wt rm feat-z
removed worktree feat-z
```

Force remove (dangerous)
```bash
$ wt ls
name       branch                  status  dirty  sync
exp-wt     experimental            READY   yes    1 ahead

# Force remove loses uncommitted changes and unpushed commits
$ wt rm exp-wt --force
removed worktree exp-wt
# WARNING: Uncommitted work and unpushed commits are gone forever
```

Error: worktree not found
```bash
$ wt rm nonexistent
error: worktree not found: nonexistent
exit code 2
```

Using pre_remove hooks
```bash
# In .wt/config/wt.toml:
[hooks]
pre_remove = [
    "echo 'About to remove worktree {name}'",
    "wt db snapshot {name} --name pre-remove-backup",
]

# When removing, hooks run before git worktree remove
$ wt rm old-feature
About to remove worktree old-feature
created snapshot: .wt/state/snapshots/old-feature-pre-remove-backup.sqlite
removed worktree old-feature
```

Safety configuration override
```bash
# In .wt/config/wt.toml, disable specific safety checks:
[safety]
refuse_remove_if_dirty = false
refuse_remove_if_unpushed = true

# Now dirty worktrees can be removed without --force
$ wt ls
name       branch                  status  dirty  sync
quick-fix  wt/quick-fix           READY   yes    ok

$ wt rm quick-fix
removed worktree quick-fix
# No --force needed because refuse_remove_if_dirty = false

# But unpushed commits still require --force
$ wt rm another-branch
refusing to remove another-branch: unpushed commits
exit code 4
```

Difference between `wt rm` and branch deletion
----------------------------------------------
`wt rm`: Removes the worktree directory only
- Does NOT delete the Git branch
- Worktree directory at `.worktrees/<name>/` is removed
- Branch remains in `git branch` list
- Use after merging work or when you want to keep the branch

To remove both worktree AND branch:
```bash
# Remove worktree first
wt rm feat-x

# Delete the branch separately
git branch -D wt/feat-x

# Or use wt land --cleanup (handles both for merged branches)
wt land feat-x --cleanup
```

Integration with other commands
--------------------------------
Before removing a worktree, you typically:
- `wt ls`: Verify worktree status and safety conditions
- `wt status <name>`: Check detailed status before removal
- `wt db snapshot <name>`: Create database snapshot before removal (if needed)
- `git status`: Check for uncommitted work in the worktree

After removing a worktree:
- `wt ls`: Verify worktree is gone
- `git branch -D <branch>`: Delete the branch if no longer needed
- `wt gc`: Clean up other old worktrees
- `wt reindex`: Rebuild database if needed

Recovery after accidental removal
--------------------------------
If you accidentally removed a worktree with `--force`:
1. Worktree directory is gone (Git worktree remove is destructive)
2. Branch may still exist (check `git branch -a`)
3. Recover from remote if unpushed work was lost:
   ```bash
   git checkout -b recovered-branch origin/branch-name
   wt add recovered-work --branch recovered-branch
   ```
4. If branch was also deleted and not pushed, data may be unrecoverable
