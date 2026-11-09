from enum import StrEnum


class ToleranceMode(StrEnum):
    EXACT = "exact"
    UNTIL_HOUR = "until_hour"
    WINDOW_HOURS = "window_hours"


class TriggerType(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    SKIPPED_ALREADY_RAN = "skipped_already_ran"
    SKIPPED_OUTSIDE_WINDOW = "skipped_outside_window"
    SKIPPED_TARGET_OFFLINE = "skipped_target_offline"
    FAILED = "failed"


class TargetType(StrEnum):
    TERMINAL = "terminal"
    HERDR = "herdr"
    BACKGROUND = "background"


class TerminalApp(StrEnum):
    AUTO = "auto"
    TERMINAL = "terminal"
    ITERM2 = "iterm2"
    GHOSTTY = "ghostty"
    KITTY = "kitty"
