# Contributing to Roostr 🐓

Thank you for your interest in contributing to Roostr! We welcome bug reports, documentation improvements, feature ideas, and pull requests.

---

## ⚠️ Important: Adding New AI Harnesses

> [!IMPORTANT]
> **Requests for adding new AI harnesses must be submitted as an Issue first.**  
> Please do **not** open a Pull Request adding a new harness without prior discussion in an Issue.

Different AI CLI harnesses (Claude Code, Antigravity, Cursor, Codex, etc.) vary significantly in how they handle:
- Command-line arguments and multiline prompt passing
- Interactive versus non-interactive / headless flags
- Session resumption and workspace directories
- Shell escaping and terminal signals

Opening an Issue first allows us to align on CLI flags, expected behaviors, and integration tests before any code is authored.

---

## 🛠️ Local Development Setup

Roostr uses Python `>= 3.13` and [uv](https://github.com/astral-sh/uv) as the recommended package manager.

### 1. Clone the repository

```bash
git clone https://github.com/tiagoornelas/roostr.git
cd roostr
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Run the test suite

Roostr maintains a comprehensive test suite covering the domain, storage, use cases, daemon, targets, CLI, and Textual UI:

```bash
uv run pytest
```

### 4. Code Formatting and Linting

We enforce formatting and lint rules via [Ruff](https://docs.astral.sh/ruff/):

```bash
# Check linting
uv run ruff check .

# Check code formatting
uv run ruff format --check .

# Auto-format
uv run ruff format .
```

---

## 📋 Pull Request Guidelines

1. **Keep changes focused:** One feature or bugfix per PR.
2. **Include automated tests:** Any bugfix or new feature must include accompanying `pytest` unit/integration tests verifying observable behavior.
3. **Conventional Commits:** Follow the standard commit format:
   ```text
   <type>(<scope>): <short description>
   ```
   Examples: `feat(scheduler): support interval windows`, `fix(ui): adjust time input width`. Keep titles under 72 characters and omit trailing periods.
4. **All quality checks must pass:** Ensure `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest` pass cleanly with zero warnings or errors.

---

## 📄 License

By contributing to Roostr, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
