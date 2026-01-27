# Installing wt/orch and OpenCode Skills

This guide explains how to:
1. Install `wt`/`orch` globally with `uv`
2. Install the OpenCode skills for this repository
3. Use these skills effectively with coding agents

## Global Install with `uv`

### From Local Checkout

If you have cloned this repository locally:

```bash
# Navigate to the repository root
cd /path/to/feature-agentic-skills

# Install wt and orch globally using uv
uv tool install .
```

This installs both `wt` and `orch` as globally available commands. The tools are installed from the local checkout, so any changes you make will require reinstalling.

### From Git URL

To install directly from a remote repository:

```bash
# Install from GitHub (or any git URL)
uv tool install git+https://github.com/<org>/<repo>.git

# Install from a specific branch or tag
uv tool install git+https://github.com/<org>/<repo>.git@<branch>
uv tool install git+https://github.com/<org>/<repo>.git@v1.2.0
```

Replace `<org>` and `<repo>` with the actual repository details.

### Verification

After installation, verify the tools are available:

```bash
wt --version
orch --version
```

Both commands should execute successfully and display version information.

## Installing OpenCode Skills

OpenCode skills provide AI agents with domain-specific knowledge about the `wt` CLI, helping them understand workflows, commands, and best practices.

### Local Installation (Default)

Install skills into all existing worktrees and seed templates for future worktrees:

```bash
# Run from repository root or any worktree
wt install-skills
```

This command:
- Copies skills to `.wt/templates/skills/` for seeding new worktrees
- Installs skills into all existing worktrees under `.opencode/skills/<skill>/SKILL.md`
- Skips existing skill files (idempotent, safe to re-run)

### Global Installation

Install skills to your global OpenCode skills directory:

```bash
wt install-skills --global
```

This installs skills to:
- `$XDG_CONFIG_HOME/opencode/skills` if `XDG_CONFIG_HOME` is set
- `~/.config/opencode/skills` as a fallback

Global installation makes skills available to all OpenCode sessions across all projects.

### Overwriting Existing Skills

To force overwrite of existing skill files:

```bash
# Local overwrite
wt install-skills --force

# Global overwrite
wt install-skills --global --force
```

Use `--force` when you want to update to newer versions of skills.

## Available Skills

This repository provides 9 micro-skills covering the `wt core` workflow:

| Skill | Description | When to Use |
|-------|-------------|-------------|
| `wt-init` | Initialize `.wt` configuration and database | First-time setup in a new Git repo |
| `wt-new` | Create a new worktree with a new branch | Starting new feature or fix work |
| `wt-add` | Add a worktree for an existing branch | Working on existing remote branches |
| `wt-open` | Open a worktree in tmux and launch editor | Switching to existing worktree |
| `wt-sync` | Sync a worktree with upstream | Keeping worktree up-to-date |
| `wt-land` | Merge and cleanup a completed worktree | Finishing feature work |
| `wt-rm` | Remove a worktree and its branch | Cleaning up completed worktrees |
| `wt-ls` | List all worktrees with metadata | Checking worktree status |
| `wt-doctor` | Diagnose and fix common issues | Troubleshooting problems |
| `wt-reindex` | Rebuild the worktree database cache | Repairing state inconsistencies |

### Skill Content

Each skill includes:
- **When to use**: Clear guidance on when to invoke the skill
- **Primary commands**: Essential CLI commands with flags
- **Common workflows**: Typical usage patterns and examples
- **Safety checks**: Pre-flight and post-flight verification steps
- **"Don't do" guardrails**: Common mistakes to avoid
- **Examples**: Concrete usage examples with expected output

### Skill Location

Skills are stored in the repository at:
```
src/wt/opencode_skills/<skill-name>/SKILL.md
```

They are included as package data when installing `wt` or `orch`.

## OpenCode Skill Discovery

OpenCode discovers skills in the following order (first match wins):

1. **Worktree-local skills**: `<worktree>/.opencode/skills/`
2. **Global skills**: `$XDG_CONFIG_HOME/opencode/skills/` or `~/.config/opencode/skills/`

When you install skills locally with `wt install-skills`, they become available in each worktree. When you install globally, they're available across all projects.

For more details on OpenCode skills, see: https://opencode.ai/docs/skills/

## Agent Usage Examples

Coding agents should load the appropriate skills based on the task at hand.

### Full Worktree Workflow

For agents managing the complete feature lifecycle:

```python
load_skills=['wt-init', 'wt-new', 'wt-add', 'wt-open', 'wt-sync', 'wt-land', 'wt-rm', 'wt-ls', 'wt-doctor']
```

This skill set provides:
- Initial repository setup (`wt-init`)
- Worktree creation and management (`wt-new`, `wt-add`, `wt-open`)
- Collaboration and synchronization (`wt-sync`, `wt-ls`)
- Completion and cleanup (`wt-land`, `wt-rm`)
- Troubleshooting (`wt-doctor`)

### Task-Specific Skill Loading

For focused tasks, load only relevant skills:

```python
# Creating new worktrees
load_skills=['wt-init', 'wt-new', 'wt-open']

# Maintaining existing worktrees
load_skills=['wt-sync', 'wt-ls', 'wt-doctor']

# Cleaning up completed work
load_skills=['wt-land', 'wt-rm']
```

### New Project Setup

For agents initializing a new repository:

```python
load_skills=['wt-init', 'wt-new']
```

The agent can:
- Initialize `.wt` configuration with `wt init`
- Create the first feature worktree with `wt new`

### Debugging and Repair

For agents diagnosing issues:

```python
load_skills=['wt-doctor', 'wt-reindex', 'wt-ls']
```

This enables:
- Running diagnostics with `wt doctor`
- Rebuilding the database with `wt reindex`
- Inspecting worktree state with `wt ls`

## Example: Complete Agent Workflow

Here's an example of how a coding agent uses these skills:

```python
# Agent initializes new project
delegate_task(
  category="writing",
  load_skills=['wt-init', 'wt-new'],
  description="Initialize wt and create first worktree"
)

# Agent runs commands based on skill guidance
# From wt-init skill:
#   wt init  # Creates .wt/config, templates, database

# From wt-new skill:
#   wt new feat-x --bootstrap --open  # Creates and opens worktree
```

The agent reads skill documentation to understand:
- What commands to run and in what order
- Required flags and options
- Expected outcomes and verification steps
- Common pitfalls to avoid

## Updating Skills

To update to the latest skills:

1. **Pull latest changes** (if installed from git):
   ```bash
   uv tool install --force git+https://github.com/<org>/<repo>.git
   ```

2. **Reinstall skills** (overwrites existing):
   ```bash
   wt install-skills --force  # Local
   wt install-skills --global --force  # Global
   ```

Skills are versioned with the `wt`/`orch` package. Reinstalling the package and running `wt install-skills --force` updates skills to the latest version.

## Uninstalling

### Remove wt/orch

```bash
uv tool uninstall wt
uv tool uninstall orch
```

### Remove Skills

```bash
# Remove local skills from a specific worktree
rm -rf .worktrees/<name>/.opencode/skills/

# Remove seeded templates
rm -rf .wt/templates/skills/

# Remove global skills
rm -rf ~/.config/opencode/skills/
# or
rm -rf $XDG_CONFIG_HOME/opencode/skills/
```

## Troubleshooting

### Skills Not Found

If an agent reports that skills are not available:

1. **Verify installation**:
   ```bash
   wt install-skills  # Local
   wt install-skills --global  # Global
   ```

2. **Check OpenCode skill directories**:
   ```bash
   ls -la .opencode/skills/
   ls -la ~/.config/opencode/skills/
   ```

3. **Verify skill files exist**:
   ```bash
   ls src/wt/opencode_skills/
   ```

### Permission Denied

If installation fails with permission errors:

```bash
# For global install, check directory ownership
ls -la ~/.config/opencode/skills/
sudo chown -R $USER:$USER ~/.config/opencode/skills/
```

### Skills Not Updating

If `wt install-skills` doesn't update skills:

```bash
# Force overwrite
wt install-skills --force

# If that fails, remove and reinstall
rm -rf .wt/templates/skills/
wt install-skills
```

## Additional Resources

- **Main repository README**: See `README.md` for an overview of `wt` and `orch`
- **Agent guidelines**: See `AGENTS.md` for working with this repository
- **OpenCode documentation**: https://opencode.ai/docs/skills/ for skill format and usage

## Quick Reference

```bash
# Install wt/orch globally
uv tool install .

# Install skills locally (all worktrees)
wt install-skills

# Install skills globally
wt install-skills --global

# Force update skills
wt install-skills --force

# Verify installation
wt --version
ls -la .wt/templates/skills/
ls -la ~/.config/opencode/skills/
```
