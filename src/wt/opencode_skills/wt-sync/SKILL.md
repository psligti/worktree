---
name: wt-sync
description: Sync a worktree with its base branch using rebase, merge, or fetch strategies
---

When to use
-----------
Use `wt sync` when:
- Bringing latest changes from main into your feature worktree
- Updating a worktree after base branch has moved forward
- Resolving merge conflicts before landing your feature
- Keeping worktrees in sync with upstream changes
- Preparing for testing against latest base branch code

DO NOT use `wt sync` when:
- Your worktree has uncommitted changes (commit or stash first)
- The worktree is in a detached HEAD state
- You want to push changes from the worktree (use `git push` instead)
- You want to merge your feature into base (use `wt land` instead)

Prerequisites
-------------
- `wt init` must have been run in the repository
- The worktree must exist (created with `wt new` or `wt add`)
- The worktree should have no uncommitted changes (or handle them first)

Primary commands
----------------
```bash
# Sync with base branch using rebase (default strategy)
wt sync <worktree-name>

# Sync using merge strategy instead of rebase
wt sync <worktree-name> --strategy merge

# Sync from a specific reference (instead of default base)
wt sync <worktree-name> --from origin/develop

# Sync with rebase (explicit)
wt sync <worktree-name> --strategy rebase
```

Strategy options (`--strategy`):
- `rebase` (default): Rebase your worktree onto the base branch. Creates linear history, requires resolving conflicts in your commits.
- `merge`: Merge base branch into your worktree. Preserves branch history, creates merge commits.

The `--from` flag:
- Defaults to `origin/<default_base>` (typically `origin/main`)
- Use `--from` to sync from a different branch or reference
- Examples: `--from origin/develop`, `--from upstream/main`, `--from my-feature`

Common workflows
----------------

Daily sync with rebase (recommended)
```bash
# Bring latest main changes into your worktree
wt sync feat-api-cleanup
# Output: synced feat-api-cleanup from origin/main
```

Sync with merge
```bash
# If you prefer merge workflow
wt sync feat-api-cleanup --strategy merge
# Output: synced feat-api-cleanup from origin/main
```

Sync from different base
```bash
# Sync from develop branch instead of main
wt sync feat-api-cleanup --from origin/develop
# Output: synced feat-api-cleanup from origin/develop
```

Workflow before landing
```bash
# 1. Commit your changes
cd .worktrees/feat-api-cleanup
git add .
git commit -m "implement api cleanup"

# 2. Sync to resolve any conflicts early
cd -
wt sync feat-api-cleanup

# 3. Run tests
cd .worktrees/feat-api-cleanup
pytest

# 4. Land your feature
cd -
wt land feat-api-cleanup --cleanup
```

Sync multiple worktrees
```bash
# Update all your active worktrees
for wt in feat-api-cleanup feat-auth feat-ui; do
    wt sync $wt
done
```

Safety checks
-------------
Before running `wt sync`:
1. Verify you have no uncommitted changes:
   ```bash
   cd .worktrees/<worktree-name>
   git status --porcelain  # Should output nothing
   ```
2. Check that the worktree is on a branch (not detached):
   ```bash
   git branch --show-current  # Should show your branch name
   ```
3. Ensure the remote reference exists:
   ```bash
   git fetch origin  # Update remote references
   ```
4. Review pending changes in base branch if needed:
   ```bash
   git log --oneline HEAD..origin/main  # See what's new
   ```

After running `wt sync`:
1. Verify the sync succeeded (no error output)
2. Check for merge conflicts:
   ```bash
   git status  # Look for "both modified" files
   ```
3. Run tests to ensure compatibility with new base changes
4. Rebuild dependencies if needed (e.g., `uv sync`)

Handling conflicts
```bash
# If rebase conflicts occur:
wt sync feat-api-cleanup
# Error: conflict detected, resolve and continue

cd .worktrees/feat-api-cleanup

# Resolve conflicts in affected files
vim conflicted-file.py

# Stage resolved files
git add conflicted-file.py

# Continue rebase
git rebase --continue

# Or abort if needed
git rebase --abort
```

"Don't do" guardrails
--------------------
- DON'T sync with uncommitted changes (commit or stash first)
- DON'T use `--strategy rebase` on shared feature branches with collaborators
- DON'T ignore merge conflicts - resolve them before continuing
- DON'T sync from untrusted or unstable references
- DON'T sync a worktree that someone else is actively working on (check locks with `wt locks`)
- DON'T use `wt sync` to push your changes upstream (use `git push` instead)
- DON'T sync without running tests afterward (base changes may break your code)
- DON'T use merge strategy on public branches that require clean history

Examples
--------

Basic rebase sync
```bash
$ wt sync feat-api-cleanup
synced feat-api-cleanup from origin/main
```

Merge strategy sync
```bash
$ wt sync feat-api-cleanup --strategy merge
synced feat-api-cleanup from origin/main
```

Custom reference sync
```bash
$ wt sync feat-api-cleanup --from origin/develop
synced feat-api-cleanup from origin/develop
```

Sync failure (conflict)
```bash
$ wt sync feat-api-cleanup
Error: CONFLICT (content): Merge conflict in src/api.py
hint: Resolve conflicts and run "git rebase --continue"
hint: Use "git rebase --abort" to abort
hint: Disable this behavior with "git config --global rebase.autoStash false"
[Exit code 5]
```

Handling uncommitted changes
```bash
$ wt sync feat-api-cleanup
Error: worktree has uncommitted changes
hint: Commit or stash changes before syncing
[Exit code 5]

$ cd .worktrees/feat-api-cleanup
$ git stash
$ cd -
$ wt sync feat-api-cleanup
synced feat-api-cleanup from origin/main
```

Checking sync status
```bash
$ cd .worktrees/feat-api-cleanup
$ git log --oneline --graph --all --decorate
* 1a2b3c4 (HEAD -> wt/feat-api-cleanup) my latest commit
* 9f8e7d6 previous commit
| * 5c6d7e8 (origin/main) latest main commit
|/
* a1b2c3d base commit

# After sync:
$ cd -
$ wt sync feat-api-cleanup
synced feat-api-cleanup from origin/main

$ cd .worktrees/feat-api-cleanup
$ git log --oneline --graph --all --decorate
* f0e1d2c (HEAD -> wt/feat-api-cleanup) my latest commit (rebased)
* 5c6d7e8 (origin/main) latest main commit
|/
* a1b2c3d base commit
```

Rebase vs merge comparison
```bash
# Rebase: Linear history (recommended for feature branches)
$ wt sync feat-x --strategy rebase
# Result: Your commits are replayed on top of origin/main
# Good for: Clean history, easy bisect, PRs with squashed commits

# Merge: Preserves non-linear history
$ wt sync feat-x --strategy merge
# Result: A merge commit is created combining origin/main and your branch
# Good for: Long-running feature branches, multiple contributors, time-based development
```

Sync before PR update
```bash
# Working on a PR, need to update with latest main
$ cd .worktrees/feat-api-cleanup
$ git status
On branch wt/feat-api-cleanup
Your branch is up to date with 'origin/wt/feat-api-cleanup'.

$ cd -
$ wt sync feat-api-cleanup
synced feat-api-cleanup from origin/main

$ cd .worktrees/feat-api-cleanup
$ git push  # Push rebased commits to update PR
```

Integration with worktree workflow
```bash
# Typical feature branch lifecycle:
wt init                              # Initialize repo
wt new feat-api-cleanup --bootstrap  # Create worktree
cd .worktrees/feat-api-cleanup
# ... make changes ...
git commit -am "implement cleanup"

# Daily workflow:
cd -
wt sync feat-api-cleanup              # Sync with main
cd .worktrees/feat-api-cleanup
pytest                               # Run tests
# ... more work ...

# Ready to land:
cd -
wt land feat-api-cleanup --cleanup    # Merge back and clean up
```
