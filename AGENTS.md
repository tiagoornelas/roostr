# AGENTS.md

This file provides global instructions and project context for all AI agents (Claude, Antigravity, Cursor, Codex, etc.) working on this repository.

## Project Overview

Roostr is a local-first scheduled task runner and software factory alarm for local AI coding agents on macOS. It wakes up autonomous coding routines on schedule — dispatching morning PR audits, test suites, and refactorings directly into Herdr workspaces, dedicated terminal tabs, or silent background runs.

Roostr exposes **two equal interfaces**:
1. **Interactive TUI** (`roostr`): Textual dashboard for human visual management.
2. **Autonomous CLI** (`roostr <command>`): Non-interactive Click CLI for AI coding agents and shell automation.

## Tech Stack

- **Language:** Python 3.13+
- **TUI Framework:** Textual 8.x
- **CLI Framework:** Click 8.x
- **Persistence:** Embedded SQLite 3 (WAL journal mode)
- **OS Integration:** Native macOS `launchd` User Agent (no root, no background Docker daemons)
- **Package & Environment:** `uv`, `hatchling`
- **Testing & Quality:** `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`

## Commands

```bash
uv run roostr                 # Launch the interactive Textual TUI
uv run roostr --help          # Show top-level CLI commands and options
uv run roostr job list        # List scheduled jobs (supports --json)
uv run roostr run <job_id>    # Trigger immediate execution of a job
uv run roostr daemon status   # Check status of the macOS launchd scheduler

uv run pytest                 # Run the automated test suite
uv run pytest --cov=roostr    # Run tests with coverage report
uv run ruff check .           # Run linter
uv run ruff format .          # Run code formatter
```

## Architecture

Roostr is structured under Clean Architecture (Ports & Adapters):

- `src/roostr/domain/`: Pure business models (`Job`, `Schedule`, `ExecutionRecord`) and enums (`AIHarness`, `TargetType`, `ScheduleFrequency`). Zero external framework dependencies.
- `src/roostr/application/`: Abstract ports (`ports.py`) and use cases (`ExecuteJobUseCase`, `ManageJobsUseCase`, `DaemonSchedulerUseCase`).
- `src/roostr/infrastructure/`: Concrete implementations of ports (`SQLiteStorage`, `LaunchdServiceAdapter`, and execution targets in `targets/`).
- `src/roostr/ui/`: Textual interactive TUI components, screens, modals, and reactive widgets.
- `src/roostr/cli.py`: Click CLI group and subcommands.

Dependencies point strictly inward: `ui/` and `cli.py` consume `application/use_cases/`, which consume `domain/`. Direct SQL queries or bypassing use cases in UI or CLI is forbidden.

## Key Constraints & Standing Rules

1. **Interface Parity (`docs/rules/interface-parity.md`):**
   - Every capability added to Roostr must be implemented and exposed in **both** the interactive TUI and the non-interactive CLI.
   - An AI agent driving the CLI must be able to operate the platform with the same power as a human using the visual TUI.
2. **Machine-Friendly CLI Output:**
   - Any CLI command that inspects or lists data (`roostr job list`, `roostr job show`, `roostr folder list`, `roostr history`) must support a `--json` flag returning clean, structured JSON for AI consumption.
3. **Local-First & Safety:**
   - Persistence is confined to standard XDG directories (`~/.local/share/roostr/roostr.db`, `~/.local/state/roostr/logs/`).
   - Never require root privileges or install system-wide daemons.
4. **Sleep & Lid-Close Tolerance:**
   - Scheduled tasks account for macOS sleep states using tolerance windows (`ToleranceMode.CATCH_UP` vs `ToleranceMode.STRICT_WINDOW`).

## Rules and Architecture Records

- Rules for architecture, interface parity, and coding practices live in `docs/rules/`.
- Architecture Decision Records live in `docs/adr/`.
