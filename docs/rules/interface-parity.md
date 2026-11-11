# Interface Parity (TUI & CLI)

Roostr provides two first-class interfaces for managing scheduled routines:
1. **Interactive Terminal UI (TUI):** Built with Textual for human visual exploration, keyboard shortcuts, and responsive inspector cards.
2. **Command-Line Interface (CLI):** Built with Click for autonomous AI coding agents, terminal scripts, and CI automation.

## Core Principle

Every new feature or capability introduced into Roostr must be implemented and exposed across **both** interfaces:
- Visually accessible for humans via the TUI (`roostr`).
- Programmatically accessible for AI agents and scripts via the CLI (`roostr <command>`).

An AI coding agent must be able to inspect, configure, and operate the platform with the same degree of freedom and power as a human developer using the interactive visual dashboard.

## Implementation Standard

When implementing or modifying any feature:

1. **Domain & Application First**:
   - Encapsulate the behavior in the `domain` and `application/use_cases/` layers. Neither interface may hold private business logic.
   - All persistence, scheduling, and validation rules must be accessible through application use cases.

2. **CLI Parity Requirements**:
   - Provide explicit subcommands for the feature under `roostr job`, `roostr folder`, `roostr daemon`, etc.
   - Support a `--json` flag on all queries and listings to provide clean, structured data for AI agents.
   - Provide clear exit codes (`0` on success, non-zero on failure) and concise stderr error messages.

3. **TUI Parity Requirements**:
   - Provide corresponding visual screens, modals, or keyboard bindings in `roostr/ui/`.
   - Update help keys and status bars where applicable.
   - Support i18n localization keys (`en`, `pt_br`, `es`) for all user-facing strings in the TUI.

4. **Testing**:
   - Write automated unit tests for the use case.
   - Write CLI invocation tests in `tests/test_cli.py` verifying both standard formatted output and `--json` payload.
   - Write TUI async tests in `tests/test_ui.py` verifying the visual workflow.
