# CLI Contract (v2)

This document defines the command surface, flags, output contracts, exit codes, and JSON schemas for `wt`.

## 1. Global CLI

### Usage
```
wt <command> [options]
```

### Conventions
- Errors go to stderr; human output goes to stdout.
- Git remains authoritative; the DB is a cache.
- `wt ls --json` outputs machine-readable records.

## 2. Commands

### 2.1 `wt init`
Initialize `.wt/` config/templates and SQLite schema.

### 2.2 `wt new`
Create a new worktree.
```
wt new <name> [--base <ref>] [--profile <profile>] [--open] [--bootstrap] [--purpose <text>]
```

### 2.3 `wt add`
Add a worktree from an existing branch.
```
wt add <name> --branch <branch> [--open] [--bootstrap] [--purpose <text>]
```

### 2.4 `wt open`
Open a worktree in tmux.
```
wt open <name> [--layout <layout>]
```

wt open <name> [--layout <layout>] [--editor/--no-editor]
```

### 2.5 `wt bootstrap`
Bootstrap a worktree.
```
wt bootstrap <name>
```

### 2.6 `wt ls`
List worktrees with derived status.
```
wt ls [--json]
```

### 2.7 `wt sync`
Bring main changes into the worktree branch.
```
wt sync <name> [--strategy rebase|merge] [--from <ref>]
```

### 2.8 `wt land`
Merge worktree branch back to main (local merge-first).
```
wt land <name> [--strategy merge|rebase] [--run-checks] [--cleanup]
```
- `--run-checks` runs hook commands/scripts from `.wt/config/hooks.d/run_checks.d` and `hooks.run_checks`.

### 2.9 `wt lock`
Lock a worktree to prevent cleanup.
```
wt lock <name> [--reason <text>]
```

### 2.10 `wt unlock`
Unlock a worktree.
```
wt unlock <name>
```

### 2.11 `wt run`
Run a command inside the worktree.
```
wt run <name> [--lock-on-run] [--artifacts <dir>] -- <command...>
```

### 2.12 `wt purpose`
View or set the worktree purpose metadata.
```
wt purpose <name> [purpose]
wt purpose <name> --clear
```

### 2.13 `wt runs`
List recent runs for a worktree.
```
wt runs <name> [--limit 10]
```

### 2.14 `wt locks`
List active worktree locks.
```
wt locks
```

### 2.15 `wt rm`
Remove a worktree with safety checks.
```
wt rm <name> [--force]
```

### 2.16 `wt reindex`
Rebuild DB cache from git worktree list.

### 2.17 `wt doctor`
Diagnose common issues (missing path, missing venv, missing upstream).

### 2.18 `wt api`
Launch the FastAPI server.
```
wt api [--host 127.0.0.1] [--port 8765] [--reload]
```

### 2.19 `wt tui`
Launch the Textual TUI.

## 3. Exit Codes
- `0`: Success
- `1`: General error
- `2`: Usage error
- `3`: Not found
- `4`: Conflict/guardrail
- `5`: Git failure

## 4. JSON Schemas

### 4.1 WorktreeRecord
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.local/schemas/v2/worktree-record.json",
  "title": "WorktreeRecord",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "name", "path", "lifecycle", "bootstrap", "agent", "runtime"],
  "properties": {
    "id": { "type": "string" },
    "name": { "type": "string" },
    "path": { "type": "string" },
    "branch": { "type": ["string", "null"] },
    "purpose": { "type": ["string", "null"] },
    "head_sha": { "type": ["string", "null"] },
    "base_ref": { "type": ["string", "null"] },
    "lifecycle": { "type": "string" },
    "bootstrap": { "type": "string" },
    "agent": { "type": "string" },
    "runtime": { "type": "string" },
    "git_dirty": { "type": "boolean" },
    "git_sync": { "type": ["string", "null"] },
    "upstream": { "type": ["string", "null"] },
    "ahead": { "type": "integer" },
    "behind": { "type": "integer" },
    "behind_main": { "type": "integer" },
    "created_at": { "type": "string" },
    "last_accessed_at": { "type": ["string", "null"] },
    "last_error": { "type": ["string", "null"] },
    "updated_at": { "type": "string" }
  }
}
```
