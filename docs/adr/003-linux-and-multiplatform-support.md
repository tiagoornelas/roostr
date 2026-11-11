# ADR-003: Linux and Multiplatform Daemon Architecture via Clean Architecture Adapters

- **Status:** accepted
- **Date:** 2026-11-11

## Context

Roostr began on macOS, using `launchd` LaunchAgents (`com.tiagoornelas.roostr.daemon.plist`), AppleScript (`osascript`) for notifications and terminal dispatch, and hardcoded `zsh` subshells. 

However, Roostr's core domain models, SQLite persistence, Click CLI, and Textual TUI are completely platform-independent. Linux developers running autonomous coding routines in local workspaces require native background task execution without requiring root privileges or external Docker daemons.

## Decision

We introduce multiplatform abstraction through the `PlatformFactory` pattern in `roostr.infrastructure.platform`, preserving Clean Architecture boundaries:

1. **Linux User Daemon (`systemd --user`)**:
   - `SystemdUserServiceAdapter` implements `DaemonServicePort`.
   - Generates and manages `~/.config/systemd/user/roostr.service` with standard `systemctl --user` commands (`enable --now`, `disable`, `is-active`, `daemon-reload`).
   - Requires zero root privileges.

2. **Cross-Platform Notifications (`notify-send`)**:
   - `LinuxNotifierAdapter` implements `NotificationPort` via `notify-send`.
   - Dispatches desktop alerts silently, handling missing notification binaries gracefully.

3. **Linux Terminal Execution Target**:
   - `LinuxTerminalTargetAdapter` implements `ExecutionTargetPort`.
   - Dispatches runner scripts (`.sh`) across supported Linux terminal emulators (`ghostty`, `kitty`, `alacritty`, `gnome-terminal`, `x-terminal-emulator`, `konsole`, `xterm`).

4. **Dynamic Shell Resolution**:
   - Replaced hardcoded `zsh` with dynamic shell discovery (`$SHELL`, `bash`, `sh`, `zsh`), preventing command execution failures on minimal Linux environments.

5. **Universal Distribution Model**:
   - Single universal wheel package on PyPI (`roostr-py3-none-any.whl`).
   - OS-specific daemon installation occurs explicitly via `roostr daemon install`.

## Consequences

### Positive
- Full functional parity on macOS and Linux.
- CLI commands (`roostr daemon install/status/uninstall`) and TUI dashboard auto-select the native background service manager (`launchd` on macOS, `systemd --user` on Linux).
- Application use cases (`ExecuteJobUseCase`) depend strictly on ports rather than platform-specific concrete classes.
- Zero heavyweight emulation needed during development: 100% of Linux adapter logic is verified through mocked runner fixtures in pytest.

### Negative / Trade-offs
- Windows is not supported (systemd and launchd are POSIX/Unix models).
- Linux headless servers without a user systemd session require `loginctl enable-linger` for background execution across user logout.
