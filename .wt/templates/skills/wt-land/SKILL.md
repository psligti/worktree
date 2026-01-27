---
name: wt-land
description: Land a worktree branch back to main (merge and optionally remove worktree)
---

When to use
-----------
Use `wt land` when:
- Your feature work is complete and ready to merge back to main
- You've finished testing and want to integrate your changes into the base branch
- PR is approved and checks pass (if using PR workflow)
- You're ready to clean up and move on to the next task

DO NOT use `wt land` when:
- The worktree is dirty (uncommitted changes)
- You haven't tested your changes locally
- CI checks haven't passed (if applicable)
- You want to keep the worktree for further work (use `wt sync` instead)
- You need to preserve the branch separately from main

Prerequisite
------------
`wt land` requires:
- `wt init` to have been run in the repository
- Worktree to exist (created via `wt new`, `wt add`, or `wt clone`)
- Clean worktree (no uncommitted changes) if safety is enabled
- The worktree branch must be valid and not currently checked out in repo root

Primary commands
----------------
```bash
# Basic landing (merge to main, keep worktree)
wt land <name>

# Landing with pre-flight checks
wt land <name> --run-checks

# Landing with cleanup (remove worktree after successful merge)
wt land <name> --cleanup

# Landing with checks and cleanup
wt land <name> --run-checks --cleanup

# Using rebase strategy instead of merge
wt land <name> --strategy rebase --cleanup

# Using a specific profile
wt land <name> --cleanup --profile <profile>
```

Optional flags:
- `--strategy <merge|rebase>`: Merge strategy (default: "merge")
- `--run-checks`: Run `run_checks` hooks before landing (default: False)
- `--cleanup`: Remove worktree after successful landing (default: False)
- `--profile <profile>`: Use a specific configuration profile from `.wt/config/profiles/`

Common workflows
----------------

Simple workflow (keep worktree)
```bash
# Feature is complete, merge to main but keep worktree
wt land feat-x
landed feat-x into main

# Worktree still exists for reference or follow-up
wt ls
feat-x    wt/feat-x    READY    .worktrees/feat-x
```

Full cleanup workflow
```bash
# Feature complete, tested, ready to merge and clean up
wt land feat-x --run-checks --cleanup
landed feat-x into main

# Worktree is removed
wt ls
# (feat-x no longer in list)
```

Rebase instead of merge
```bash
# Use rebase strategy for cleaner history
wt land feature/new-api --strategy rebase --cleanup
landed feature/new-api into main
```

Running checks before landing
```bash
# Run configured test/lint hooks before merge
wt land auth-fix --run-checks
# Executes run_checks hooks from config
# Only proceeds if checks pass
landed auth-fix into main
```

What happens when you run `wt land`
-----------------------------------
1. Loads config and records from database
2. Finds worktree record by name
3. **Safety check**: Refuses if worktree is dirty and safety is enabled
4. If `--run-checks`: Executes `run_checks` hooks (fail if any hook fails)
5. Checks out the base branch in the main repo (e.g., `main`)
6. Merges or rebases the worktree branch into base:
   - Merge: `git merge wt/<name>` into base
   - Rebase: Rebase base onto worktree branch
7. Records `LandSucceeded` event in database
8. If `--cleanup`:
   - Runs `pre_remove` hooks
   - Removes worktree directory
   - Records lifecycle state as `ABSENT`

Safety checks
-------------
Before running `wt land`:
1. Verify worktree is clean: `wt ls` shows `dirty: no`
2. Confirm worktree is not currently checked out in repo root
3. If using PRs, ensure PR is approved and CI checks pass
4. Check you're in a clean state (no in-progress operations)
5. Verify `refuse_remove_if_dirty` safety setting in config

After running `wt land`:
1. Confirm merge/rebase succeeded in main branch
2. Verify worktree branch is integrated (check `git log`)
3. If `--cleanup` was used, verify worktree is removed from `wt ls`
4. If `--run-checks` was used, verify all checks passed
5. Test the merged changes in the main worktree if needed

Error scenarios
--------------
- **Dirty worktree**: "refusing to land <name>: dirty worktree" (exit code 4)
  - Commit or stash changes in worktree first
  - Or use `--force` flag (not available, need to clean first)
- **Merge conflict**: Git merge error (exit code 5)
  - Resolve conflicts in main branch
  - Complete merge manually, then run `wt land` again if needed
- **Hook failure**: If `--run-checks` hook fails
  - Fix the failing check
  - Try `wt land` again
- **Cleanup failure**: If `--cleanup` fails after merge
  - Worktree merge succeeded, but cleanup failed
  - Manually remove worktree: `wt rm <name>`

"Don't do" guardrails
--------------------
- DON'T land a dirty worktree (uncommitted changes will be lost or cause conflicts)
- DON'T land without testing locally first
- DON'T land if CI checks haven't passed (when applicable)
- DON'T use `wt land` when you need to preserve the worktree branch (use `wt sync` instead)
- DON'T land when the worktree is checked out in the main repo
- DON'T expect `--cleanup` to work if worktree is locked or has unpushed commits
- DON'T land without reviewing the diff first (know what you're merging)
- DON'T use `wt land` for rebasing conflicts (use `wt sync` instead)
- DON'T rely on `wt land` to handle complex merge conflicts automatically

Examples
--------

Basic merge (keep worktree)
```bash
$ wt land auth-refactor
landed auth-refactor into main

$ git log --oneline -5
abc1234 (HEAD -> main) Merge branch 'wt/auth-refactor' into main
def5678 (wt/auth-refactor) Add authentication service
ghi9012 Fix authentication tests

$ wt ls
auth-refactor    wt/auth-refactor    READY    .worktrees/auth-refactor
```

Full cleanup workflow
```bash
$ wt land payment-gateway --run-checks --cleanup
# Running run_checks hooks...
# ✓ pytest passed
# ✓ mypy passed
# ✓ black passed
landed payment-gateway into main

$ wt ls
# (payment-gateway no longer listed)
```

Rebase strategy
```bash
$ wt land api-v2 --strategy rebase --cleanup
landed api-v2 into main

$ git log --oneline -5
abc1234 (HEAD -> main) Add API v2 endpoints
def5678 Refactor API response models
ghi9012 Update API documentation

# Note: cleaner history, no merge commit
```

Error case: dirty worktree
```bash
$ wt land bugfix/login-error
refusing to land bugfix/login-error: dirty worktree
exit code 4

$ cd .worktrees/bugfix/login-error
$ git status
Changes not staged for commit:
    modified:   auth/login.py

$ git add auth/login.py
$ git commit -m "Fix login error handling"
[wt/bugfix/login-error 3a2b1c] Fix login error handling

$ wt land bugfix/login-error
landed bugfix/login-error into main
```

Error case: hook failure
```bash
$ wt land feature/user-profile --run-checks
# Running run_checks hooks...
# ✗ pytest failed: 2 tests failed

# Hook failure prevents landing
exit code 5

$ # Fix failing tests, then retry
$ wt land feature/user-profile --run-checks
# Running run_checks hooks...
# ✓ pytest passed
landed feature/user-profile into main
```

Error case: merge conflict
```bash
$ wt land feature/settings
Auto-merging config/settings.py
CONFLICT (content): Merge conflict in config/settings.py
Automatic merge failed; fix conflicts and then commit the result.
exit code 5

$ # Resolve conflict in main repo
$ # Edit config/settings.py, resolve conflicts
$ git add config/settings.py
$ git commit -m "Resolve merge conflict with feature/settings"

# Now the merge is complete, but worktree still exists
$ wt rm feature/settings  # Cleanup manually if needed
removed worktree feature/settings
```

Hook integration
---------------
`wt land` uses these hooks from `.wt/config/wt.toml` or profiles:

**run_checks** (triggered by `--run-checks` flag)
- Runs before merge attempt
- Typical uses: run tests, linting, type checking
- Fail the hook to prevent landing

**pre_remove** (triggered by `--cleanup` flag)
- Runs before worktree removal
- Typical uses: clean up databases, containers, or external resources
- Scripts in `.wt/config/hooks.d/pre_remove.d/` are executed

Example hook configuration:
```toml
[hooks]
run_checks = [
    "uv run pytest -q",
    "uv run mypy src/",
    "uv run black --check src/"
]
pre_remove = [
    "wt db drop ${WT_NAME} --type sqlite",
    "wt ctr rm ${WT_NAME}"
]
```

Integration with PR workflows
-----------------------------
If you use pull requests with `wt pr`:

1. Create PR: `wt pr create feat-x --title "Add feature X"`
2. Wait for review and CI checks to pass
3. When approved: `wt pr merge feat-x --strategy squash --delete-branch`
   - This merges via GitHub and deletes the remote branch
4. Then land locally: `wt land feat-x --cleanup`
   - Merges the branch into your local main
   - Removes the local worktree
   - Pushes updated main to remote

Alternative workflow (land first, then merge via PR):
1. Land locally: `wt land feat-x --run-checks`
2. Push to remote: `git push origin main`
3. Create PR for record-keeping: `wt pr create feat-x` (may auto-close as already merged)

Differences from `wt sync`
---------------------------
`wt sync`: Bring main changes INTO feature worktree
- Use to update your worktree with latest main changes
- Keeps your feature branch separate
- Branch continues to exist after sync

`wt land`: Bring feature worktree branch INTO main
- Use when your feature is complete and ready to integrate
- Merges/rebases feature into base branch
- Optionally removes worktree with `--cleanup`

Related commands
----------------
- `wt sync <name>`: Sync worktree with upstream before landing
- `wt rm <name>`: Manually remove worktree if `--cleanup` not used
- `wt ls`: Check worktree status before landing
- `wt doctor`: Diagnose issues before landing
- `wt new` / `wt add` / `wt clone`: Create worktrees
