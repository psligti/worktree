# AGENTS.md

This guide is for agentic coding tools working in this repo.
Follow local conventions and keep changes minimal and focused.

## Repository overview
- Python 3.12 CLI tools: `wt` and `orch`.
- Source lives in `src/wt` and `src/orch`.
- Tests live in `tests/` and use `unittest` style.
- Config and task data: `tasks.yaml`, `.orch/config.yaml`.
- Editable install uses `uv` and `pyproject.toml`.

## Setup and build
- Python requirement: 3.12+.
- Install for local development:
  - `uv pip install -e .`
- CLI entry points (installed):
  - `wt` from `wt.cli:app`
  - `orch` from `orch.cli:app`
- No explicit build script is defined; keep packaging aligned with `pyproject.toml`.

## Tests
- Default test command (from `tasks.yaml` / `.orch/config.yaml`):
  - `uv run pytest -q`
- Run full test suite:
  - `uv run pytest`
- Run a single file:
  - `uv run pytest tests/test_status.py`
- Run a single test:
  - `uv run pytest tests/test_status.py::TestOverallStatus::test_broken_has_priority`
- Alternate `unittest` invocation (rare):
  - `python -m unittest tests/test_status.py`

## Linting and formatting
- No lint or formatter is configured in this repo.
- Keep formatting consistent with existing files.
- Avoid introducing a new formatter unless requested.

## Code style guidelines
- Use `from __future__ import annotations` at the top of new modules.
- Use 4-space indentation and align wrapped args with PEP 8 style.
- Prefer double quotes for strings.
- Keep lines reasonably short (~100 chars) when possible.
- Add type hints for public functions and complex data structures.

## Imports
- Order imports: standard library, third-party, local modules.
- Separate import groups with a blank line.
- Use relative imports inside packages (e.g., `from .config import ...`).
- Use absolute imports for external dependencies.

## Naming conventions
- Functions and variables: `snake_case`.
- Classes and exceptions: `PascalCase`.
- Constants and module-level defaults: `UPPER_SNAKE_CASE`.
- CLI commands are defined via `typer` and use short, clear names.

## Types and data models
- Domain records use `pydantic.BaseModel` (v2).
- Use `model_validate` for input validation and `model_dump` for output.
- Prefer explicit `Literal` types for state enums.
- Use `Path` for filesystem paths in models when possible.

## Error handling
- CLI boundaries convert domain errors to `typer.Exit` with exit codes.
- Preserve the underlying error message in user-facing output.
- Avoid bare `except` unless explicitly defensive (and comment if needed).
- For optional/expected failures, return structured values rather than raising.

## CLI output
- Use `rich.console.Console` via `console.print` for user output.
- Prefer tables for structured listings (see `wt.cli`).
- Avoid `print()` in CLI modules unless there is no console available.

## Testing style
- Tests use `unittest.TestCase` classes.
- Keep tests deterministic and avoid external side effects.
- Name test modules `test_*.py` and test classes `Test*`.
- Prefer explicit assertions (`self.assertEqual`, `self.assertTrue`, etc.).

## File layout hints
- `src/wt/cli.py`: main CLI commands and orchestration.
- `src/wt/config`: config loading, defaults, and Pydantic models.
- `src/wt/domain`: domain models and status derivation.
- `src/wt/git`: git adapter wrappers and error types.
- `src/wt/ops`: higher-level operations (doctor, reindex, bootstrap).
- `src/wt/persistence`: SQLite persistence and repositories.
- `src/orch`: task orchestration CLI and helpers.

## Dependency management
- Update `pyproject.toml` and `uv.lock` when adding dependencies.
- Keep optional dependencies optional; avoid adding heavy defaults.

## Cursor and Copilot rules
- No `.cursor/rules/` or `.cursorrules` files found.
- No `.github/copilot-instructions.md` file found.

## Contribution notes
- Avoid large refactors unless requested.
- Keep changes scoped to the feature or fix.
- Document new commands or flags in `README.md` or `RUNBOOK.md` if needed.
