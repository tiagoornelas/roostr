# 🐓 Roostr

> **The ridiculously simple scheduled task runner & software factory alarm for local AI coding agents.**  
> Wake up your autonomous workforce on a routine — dispatching morning PR audits, test suites, and refactorings straight into [Herdr](https://github.com/herdrdev/herdr) workspaces, dedicated terminal tabs, or silent background runs.

---

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.13+-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.13+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="License: MIT"></a>
  <a href="https://textual.textualize.io/"><img src="https://img.shields.io/badge/TUI-Textual-00D4AA.svg?style=flat-square" alt="Textual TUI"></a>
  <a href="https://github.com/herdrdev/herdr"><img src="https://img.shields.io/badge/Herdr-Native_Target-F43F5E.svg?style=flat-square" alt="Herdr Integration"></a>
  <a href="#-supported-ai-harnesses"><img src="https://img.shields.io/badge/AI_Harnesses-Agnostic-F97316.svg?style=flat-square" alt="AI Agnostic"></a>
</p>

---

## 🌅 Why Roostr?

Software factories are getting fancy. Cloud orchestration platforms, complex remote graphs, and heavy enterprise pipelines promise autonomy — at the cost of local simplicity, monthly bills, and Docker daemons eating your RAM.

Many of us just want to keep things **simple, local, and running straight inside the CLI harnesses we already trust** (`claude`, `agy`, `cursor`, `codex` — you name it). You do not need an industrial complex when you can run a tidy, well-organized homestead:

- **Roostr 🐓** is the rooster that crows at dawn: waking up your autonomous coding routines right on schedule.
- **Herdr 🐕** is the shepherd: herding active agents into organized workspace tabs where you can visually inspect them.

No cloud lock-in, zero Celery/Redis bloat. Just your favorite AI tools waking up on time, doing the heavy lifting while you sleep, and catching up smoothly if your laptop took a nap.

---

## ✨ Key Highlights

- **Ridiculously Simple & Local-First:**
  - Installs as a single lightweight CLI tool (`roostr`).
  - No cloud accounts, no subscriptions, zero external daemon requirements.
  - Powered by embedded SQLite (WAL mode) for rock-solid local persistence and idempotency.

- **AI-Agnostic Software Factory Runner:**
  - Preconfigured first-class support for **Claude Code** (`claude`), **Google Antigravity** (`agy`), **Cursor** (`cursor`), and **OpenAI Codex** (`codex`).
  - Supports multiline prompt authoring with markdown syntax highlighting directly in the TUI.
  - Also runs any arbitrary shell command or script (`npm test`, `pytest`, `backup.sh`).

- **Flexible Scheduling Possibilities:**
  - **Multiple Daily Runs:** Schedule specific times freely (e.g. `Monday to Friday at 7am, 9:30 am, 2:30 pm, 6 pm`).
  - **Intervals with Active Windows:** Run every `X` hours or minutes, bounded by first and last daily call limits (e.g. `every 30m between 09:00 and 18:00`).
  - **Smart Wakeup Tolerance:** Choose whether missed runs catch up after sleep/power-on (*Catch-up window*) or stay strict (*Exact time only*).

- **Multi-Target Execution:**
  - 🖥️ **Herdr App:** Default visual target. Spawns tasks in designated spaces with template-based tab names (e.g. `{job.name} {DD}/{MM}`), with 1-click tab jumping.
  - 💻 **Terminal Emulators:** Launches new windows/tabs in Terminal.app, Ghostty, iTerm2, Kitty, or Alacritty with optional interactive shell retention (`keep_open`).
  - 👻 **Background Headless:** Headless process execution with stdout/stderr redirection to log files and desktop notifications.

- **2-Level Folder Organization:**
  - Categorize jobs into collapsible folders and subfolders (e.g. `Work/Daily`, `Finance/Audit`, `OpenSource/Triage`).

- **Interactive TUI & Multilingual Support:**
  - Responsive keyboard-driven interface built on Textual.
  - Real-time inspector, execution history, and 1-click session attach command copy.
  - Switch languages on the fly (`l` key) between **English (`en`)**, **Português (`pt_br`)**, and **Español (`es`)**.
  - Curated themes: `night`, `morning`, `tokyo-night`, `nord`, and `dracula`.

---

## 🚀 Installation & Quickstart

### 1. Installation

Requires Python `>= 3.13`. Using [uv](https://github.com/astral-sh/uv) is recommended:

```bash
# Clone the repository
git clone https://github.com/tiagoornelas/roostr.git
cd roostr

# Install globally in your PATH
uv tool install --editable .
```

Verify the installation:

```bash
roostr --version
```

### 2. Launch the TUI

Simply run:

```bash
roostr
```

Or start with a specific language / theme:

```bash
roostr --locale pt_br --theme morning
```

---

## 🤖 Supported AI Harnesses

Roostr compiles prompts directly into standard CLI invocations for your favorite coding tools:

| Harness | CLI Command | Typical Software Factory Task |
| :--- | :--- | :--- |
| **Claude Code** | `claude 'prompt'` | Daily PR triage, backlog refinement, commit audits |
| **Antigravity** | `agy 'prompt'` | Autonomous subsystem redesigns, deep architecture sweeps |
| **Cursor CLI** | `cursor 'prompt'` | Rapid multi-file test-driven implementations |
| **OpenAI Codex** | `codex 'prompt'` | Boilerplate generation, schema migration reviews |
| **Custom Shell** | `/bin/zsh -c '...'` | Build verification, container health checks, database backups |

---

## 🎯 Execution Targets

### 1. Herdr App (`herdr`) — Default
Designed for developers managing multi-agent spaces in [Herdr](https://github.com/herdrdev/herdr).
- Spawns agent tasks in designated spaces.
- Dynamic tab templates with date interpolation (e.g. `{job.name} {DD}/{MM}`).
- Jump directly to the active agent tab with a single click from the Roostr inspector.

### 2. Terminal Emulators (`terminal`)
Ideal when you want dedicated windows or tabs for immediate terminal interaction.
- **Supported:** Terminal.app, Ghostty, iTerm2, Kitty, Alacritty, or auto-detect.
- **Interactive shell retention:** Keeps the terminal session open after command execution (`keep_open: true`).

### 3. Background Headless (`background`)
Silent headless runner for automated background audits, cron tasks, or headless agents.
- Redirects stdout and stderr to dedicated log files (`~/.local/state/roostr/logs/`).
- Desktop notifications on completion or failure.

---

## ⌨️ Keyboard Navigation

| Key | Action | Description |
| :---: | :--- | :--- |
| `n` | **New Job** | Opens the responsive tabbed creation modal |
| `r` | **Run Now** | Immediately triggers the selected job |
| `m` | **Move** | Moves the selected job into a folder or subfolder |
| `f` | **New Folder** | Creates a new 1st or 2nd level folder |
| `p` | **Pause / Resume** | Toggles job activation |
| `d` | **Delete** | Deletes the selected job or empty folder |
| `s` | **Settings** | Opens theme and language preferences dialog |
| `l` | **Language** | Cycles between English, Português, and Español |
| `t` | **Theme** | Cycles between curated color themes |
| `q` | **Quit** | Exits the application |

---

## 📁 Storage Layout

Roostr follows standard XDG Base Directory conventions:

| Resource | Path | Description |
| :--- | :--- | :--- |
| **Database** | `~/.local/share/roostr/roostr.db` | Embedded SQLite database (WAL journal mode) |
| **Logs** | `~/.local/state/roostr/logs/` | Standard output and error logs from background runs |
| **Runners** | `~/.local/state/roostr/runners/` | Generated executable scripts for terminal sessions |

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on code style, testing, and our pull request workflow.

> [!IMPORTANT]
> Requests for adding new AI harnesses must be submitted as an Issue first before opening a Pull Request.

---

## 📄 License

MIT © [Tiago Ornelas](https://github.com/tiagoornelas). See [LICENSE](LICENSE) for details.
