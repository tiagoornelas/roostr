# ADR-001: Clean Architecture and Local-First Foundation

- **Status:** accepted
- **Date:** 2026-11-08

## Context

AI coding agents (Claude Code, Google Antigravity, Cursor, OpenAI Codex) operate as autonomous workers on local developer machines. Coordinating routine workflows (e.g. morning pull request audits, test runs, backlog triage) usually requires heavy remote orchestration systems or Docker containers that consume unnecessary CPU and RAM.

Standard tools like `cron` fail silently when laptops close or sleep, and manual macOS `launchd` configuration requires brittle XML plists.

Roostr needs:
1. Complete local autonomy with zero cloud dependency.
2. High resilience to macOS sleep and lid-close events.
3. Clear separation between scheduling rules, execution mechanisms, UI presentation, and storage.

## Decision

Adopt **Clean Architecture (Hexagonal / Ports & Adapters)** and a **Local-First** design:

1. **Layer Separation**:
   - `domain/`: Pure domain models (`Job`, `Schedule`, `ExecutionRecord`), value objects, and enums (`AIHarness`, `TargetType`, `ToleranceMode`, `ScheduleFrequency`). No framework dependencies.
   - `application/`: Abstract ports (`JobRepositoryPort`, `SchedulerPort`, `ExecutionTargetPort`) and use cases (`ExecuteJobUseCase`, `ManageJobsUseCase`, `DaemonSchedulerUseCase`).
   - `infrastructure/`: Concrete adapters including `SQLiteStorage` (WAL mode), `LaunchdServiceAdapter` (macOS User Agent), and execution targets (`HerdrTarget`, `TerminalTarget`, `BackgroundTarget`).
   - `ui/`: Terminal User Interface built with [Textual](https://textual.textualize.io/), consuming application use cases directly.
   - `cli.py`: Command-line entry points built with Click.

2. **Embedded Persistence**:
   - Store configuration, jobs, and run history in an embedded SQLite database (`~/.local/share/roostr/roostr.db`) with Write-Ahead Logging (WAL) enabled for concurrency safety.

3. **Resilient Scheduling**:
   - Integrate natively with macOS `launchd` for background wakeups without keeping an idle Python process running constantly.
   - Implement smart catch-up tolerance windows so jobs missed while the laptop was asleep execute cleanly upon resume.

## Consequences

**Becomes easier:**
- Adding or modifying execution targets (e.g., new terminal emulators or agent harnesses) without touching core scheduling logic.
- Testing domain logic and use cases in isolation with fast in-memory SQLite fixtures.
- Supporting multiple presentation layers (TUI, CLI, headless daemon) reusing the same application use cases.

**Becomes harder:**
- Changes across ports require updating both ports and concrete infrastructure adapters.
- SQLite schema migrations must be handled cleanly within the local database without external migration services.
