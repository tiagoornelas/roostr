from dataclasses import dataclass, field
from datetime import datetime, time

from roostr.domain.enums import ExecutionStatus, TargetType, TerminalApp, ToleranceMode, TriggerType


@dataclass(slots=True)
class SchedulePolicy:
    days_of_week: tuple[int, ...]  # 0=Monday ... 6=Sunday
    time_of_day: time
    tolerance_mode: ToleranceMode = ToleranceMode.EXACT
    tolerance_value: int = 0  # until_hour (e.g. 12) or window_hours (e.g. 4)

    def is_active_on_weekday(self, weekday: int) -> bool:
        return weekday in self.days_of_week

    def is_within_window(self, dt: datetime) -> bool:
        target_minutes = self.time_of_day.hour * 60 + self.time_of_day.minute
        current_minutes = dt.hour * 60 + dt.minute

        if self.tolerance_mode == ToleranceMode.EXACT:
            return abs(current_minutes - target_minutes) <= 1

        if self.tolerance_mode == ToleranceMode.UNTIL_HOUR:
            start_minutes = target_minutes
            end_minutes = self.tolerance_value * 60
            return start_minutes <= current_minutes < end_minutes

        if self.tolerance_mode == ToleranceMode.WINDOW_HOURS:
            start_minutes = target_minutes
            end_minutes = target_minutes + (self.tolerance_value * 60)
            return start_minutes <= current_minutes < end_minutes

        return False


@dataclass(slots=True)
class TerminalTargetConfig:
    app: TerminalApp = TerminalApp.AUTO
    keep_open: bool = True
    target_type: TargetType = field(default=TargetType.TERMINAL, init=False)


@dataclass(slots=True)
class HerdrTargetConfig:
    space: str
    tab_template: str = "{job.name} {DD}/{MM}"
    target_type: TargetType = field(default=TargetType.HERDR, init=False)


@dataclass(slots=True)
class BackgroundTargetConfig:
    notify_on_complete: bool = True
    target_type: TargetType = field(default=TargetType.BACKGROUND, init=False)


TargetConfig = TerminalTargetConfig | HerdrTargetConfig | BackgroundTargetConfig


@dataclass(slots=True)
class Job:
    id: str
    name: str
    cwd: str
    command: str
    schedule: SchedulePolicy
    target: TargetConfig
    is_paused: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    folder: str | None = None

    def __post_init__(self) -> None:
        if self.folder:
            parts = [p.strip() for p in self.folder.strip().strip("/").split("/") if p.strip()]
            if len(parts) > 2:
                raise ValueError(f"Folder hierarchy cannot exceed 2 levels (got '{self.folder}')")
            self.folder = "/".join(parts) if parts else None

    @property
    def root_folder(self) -> str | None:
        if not self.folder:
            return None
        parts = self.folder.split("/")
        return parts[0] if parts else None

    @property
    def subfolder(self) -> str | None:
        if not self.folder:
            return None
        parts = self.folder.split("/")
        return parts[1] if len(parts) > 1 else None

    def resolve_herdr_tab_name(self, dt: datetime) -> str:
        if not isinstance(self.target, HerdrTargetConfig):
            return self.name
        return (
            self.target.tab_template.replace("{job.name}", self.name)
            .replace("{YYYY}", dt.strftime("%Y"))
            .replace("{MM}", dt.strftime("%m"))
            .replace("{DD}", dt.strftime("%d"))
            .replace("{YYYY-MM-DD}", dt.strftime("%Y-%m-%d"))
        )


@dataclass(slots=True)
class ExecutionRecord:
    id: int | None
    job_id: str
    timestamp: datetime
    trigger_type: TriggerType
    status: ExecutionStatus
    details: str = ""
