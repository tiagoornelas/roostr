# ADR-002: AI-Accessible CLI Interface for Autonomous Manipulation

- **Status:** accepted
- **Date:** 2026-11-11

## Context

Roostr was initially built around an interactive terminal user interface (TUI) powered by Textual. While the TUI provides an intuitive visual dashboard for human developers, it is not usable by autonomous AI coding harnesses (such as Claude Code, Google Antigravity, Cursor, or OpenAI Codex) executing shell commands inside autonomous agent loops.

Developers want to instruct AI agents to manage routines on their behalf (e.g. "create a job that runs pytest every morning at 8am and sends output to a Herdr tab", "show me failed jobs from today", or "run the PR review job now").

Without a comprehensive, non-interactive CLI surface, AI agents cannot inspect or alter Roostr jobs without directly mutating the SQLite database.

## Decision

Provide a comprehensive, non-interactive CLI interface covering all core domain capabilities, built on the existing `ManageJobsUseCase` and `ExecuteJobUseCase`:

1. **Job Management Subcommands (`roostr job ...`)**:
   - `list`: List all configured jobs, filterable by folder or status, with optional `--json` output.
   - `show <job_id>`: Display complete job details, schedule, target config, and prompt, with optional `--json` output.
   - `create`: Create a new job with flags for name, schedule, target, harness, prompt, and folder.
   - `update <job_id>`: Modify existing job properties.
   - `pause <job_id>` / `resume <job_id>`: Toggle or set paused state.
   - `delete <job_id>`: Remove a job and uninstall its schedule.
   - `run <job_id>`: Trigger immediate execution of a job (also aliased at top-level as `roostr run <job_id>`).

2. **Immediate Execution**:
   - Support triggering individual jobs on demand (`roostr run <job_id>` or `roostr job run <job_id>`), as well as executing all currently due jobs (`roostr run-due` or `roostr daemon tick`).

3. **Folder Management Subcommands (`roostr folder ...`)**:
   - `list`: List existing 1st and 2nd level folders.
   - `create <name>`: Create a folder.
   - `edit <old_name> <new_name>` (alias `rename`): Rename an existing folder, cascading to subfolders and jobs.
   - `delete <name>`: Delete a folder (supports `--force` to ungroup jobs or `--delete-jobs` to delete contents).

4. **History Subcommand (`roostr history [job_id]`)**:
   - List recent execution records, statuses, and durations with optional `--json` output.

5. **Machine-Friendly Output**:
   - Every inspection and listing command must support a `--json` flag to return structured data for programmatic AI consumption.
   - Standard output without `--json` provides clean, formatted tables for human terminal use.

## Consequences

**Becomes easier:**
- AI agents can discover, configure, inspect, and trigger scheduled jobs via standard terminal commands.
- Scripting and shell automation can integrate with Roostr without opening the TUI.
- Debugging and headless CI testing become straightforward.

**Becomes harder:**
- CLI argument parsing must handle complex nested options (e.g., target parameters, multi-time schedules).
- Any domain change must maintain parity across both the Textual TUI and the Click CLI.
