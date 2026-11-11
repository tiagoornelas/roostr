# Architecture Rules

Roostr follows Clean Architecture (Hexagonal / Ports & Adapters) principles.

## Layer Boundaries and Dependency Direction

Dependencies point inward toward the domain. Outer layers depend on inner layers; inner layers never import or depend on outer layers.

```
ui/  (Textual TUI)  ──┐
                      ├──> application/ (Use Cases, Ports) ──> domain/ (Models, Enums)
cli/ (Click CLI)    ──┘               ▲
                                      │
infrastructure/ (SQLite, launchd) ────┘
```

1. **`domain/`**:
   - Holds pure business entities (`Job`, `Schedule`, `ExecutionRecord`), value objects, and domain enums.
   - Zero dependencies on Textual, Click, SQLite, or macOS APIs.
   - Pure Python dataclasses and standard library only.

2. **`application/`**:
   - Defines ports (interfaces) in `application/ports.py` (`JobRepositoryPort`, `SchedulerPort`, `ExecutionTargetPort`, `NotificationPort`).
   - Implements use cases in `application/use_cases/` (`ExecuteJobUseCase`, `ManageJobsUseCase`, `DaemonSchedulerUseCase`).
   - Orchestrates domain entities and delegates persistence or external execution to ports.

3. **`infrastructure/`**:
   - Implements ports defined in `application/ports.py`.
   - `storage.py`: Embedded SQLite storage with WAL journal mode.
   - `platform.py`: Platform factory resolving OS-specific adapters based on `sys.platform`.
   - `launchd.py`: macOS launchd plist generation, load, and unload commands.
   - `systemd.py`: Linux systemd user service generation, enable, start, and stop commands.
   - `notifier.py`: macOS (`osascript`) and Linux (`notify-send`) desktop notification adapters.
   - `targets/`: Execution adapters for Herdr App, macOS and Linux terminal emulators, and background execution.

4. **`ui/` and `cli.py` (Presentation)**:
   - Consumer of `application/use_cases/`.
   - Neither UI nor CLI may execute direct SQL queries or bypass application use cases.
