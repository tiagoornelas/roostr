import re
import shlex
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from roostr.domain.enums import (
    ActionType,
    AIHarness,
    ExecutionStatus,
    ScheduleFrequency,
    TargetType,
    TerminalApp,
    ToleranceMode,
    TriggerType,
)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "job"


def parse_time_string(s: str) -> time:
    """Parse friendly time formats: 08:00, 8:00, 7am, 7:30 am, 2:30pm, 6 pm, 12pm, 12am."""
    s = s.strip().lower()
    is_pm = "pm" in s
    is_am = "am" in s
    clean = s.replace("am", "").replace("pm", "").strip()

    if ":" in clean:
        parts = clean.split(":")
        h = int(parts[0])
        m = int(parts[1])
    else:
        h = int(clean)
        m = 0

    if is_pm and h < 12:
        h += 12
    elif is_am and h == 12:
        h = 0

    return time(h, m)


def parse_days_of_week(s: str) -> tuple[int, ...]:
    """Parse friendly days string into tuple of weekday integers (0=Monday ... 6=Sunday).

    Examples: 'all', 'weekdays', 'weekends', 'mon,tue,wed', 'seg,qua,sex', '0,1,2,3,4'
    """
    clean = s.strip().lower()
    if clean in ("all", "*", "everyday", "daily", "todos"):
        return (0, 1, 2, 3, 4, 5, 6)
    if clean in ("weekdays", "workdays", "uteis", "úteis"):
        return (0, 1, 2, 3, 4)
    if clean in ("weekends", "fimdesemana", "fds"):
        return (5, 6)

    day_map = {
        "mon": 0,
        "monday": 0,
        "seg": 0,
        "segunda": 0,
        "0": 0,
        "tue": 1,
        "tuesday": 1,
        "ter": 1,
        "terca": 1,
        "terça": 1,
        "1": 1,
        "wed": 2,
        "wednesday": 2,
        "qua": 2,
        "quarta": 2,
        "2": 2,
        "thu": 3,
        "thursday": 3,
        "qui": 3,
        "quinta": 3,
        "3": 3,
        "fri": 4,
        "friday": 4,
        "sex": 4,
        "sexta": 4,
        "4": 4,
        "sat": 5,
        "saturday": 5,
        "sab": 5,
        "sabado": 5,
        "sábado": 5,
        "5": 5,
        "sun": 6,
        "sunday": 6,
        "dom": 6,
        "domingo": 6,
        "6": 6,
    }
    days = set()
    for part in clean.split(","):
        p = part.strip()
        if not p:
            continue
        if p in day_map:
            days.add(day_map[p])
        else:
            raise ValueError(f"Unknown weekday '{p}'. Valid examples: mon,tue,wed or all, weekdays, weekends")
    if not days:
        return (0, 1, 2, 3, 4, 5, 6)
    return tuple(sorted(days))


def parse_times_list(s: str) -> tuple[time, ...]:
    """Parse comma-separated list of friendly time strings."""
    raw_parts = [p.strip() for p in s.split(",") if p.strip()]
    if not raw_parts:
        return (time(8, 0),)
    times = sorted(set(parse_time_string(p) for p in raw_parts))
    return tuple(times)


def parse_datetime_string(s: str) -> datetime:
    """Parse ISO-like datetime strings such as '2026-11-15 14:30' or '2026-11-15T14:30'."""
    clean = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(clean)


@dataclass(slots=True)
class SchedulePolicy:
    days_of_week: tuple[int, ...] = ()  # 0=Monday ... 6=Sunday
    time_of_day: time = time(8, 0)
    tolerance_mode: ToleranceMode = ToleranceMode.EXACT
    tolerance_value: int = 0  # until_hour (e.g. 12) or window_hours (e.g. 4)
    frequency: ScheduleFrequency = ScheduleFrequency.DAILY
    interval_value: int = 1
    times_of_day: tuple[time, ...] = ()
    start_time: time | None = None  # First call / start of active window (optional)
    end_time: time | None = None  # Last call / end of active window (optional)
    run_at: datetime | None = None  # Target datetime for ScheduleFrequency.ONCE

    def __post_init__(self) -> None:
        if self.frequency == ScheduleFrequency.ONCE:
            if self.run_at is None:
                raise ValueError("run_at is required for one-time schedules")
            object.__setattr__(self, "time_of_day", self.run_at.time().replace(second=0, microsecond=0))
            object.__setattr__(self, "times_of_day", (self.time_of_day,))
        elif not self.times_of_day:
            object.__setattr__(self, "times_of_day", (self.time_of_day,))
        elif self.time_of_day == time(8, 0) and self.times_of_day:
            object.__setattr__(self, "time_of_day", self.times_of_day[0])

    @property
    def is_one_time(self) -> bool:
        return self.frequency == ScheduleFrequency.ONCE

    def is_active_on_weekday(self, weekday: int) -> bool:
        if self.frequency == ScheduleFrequency.ONCE:
            return True
        return weekday in self.days_of_week

    def is_within_window(self, dt: datetime) -> bool:
        if self.frequency == ScheduleFrequency.ONCE:
            return self._is_within_once_window(dt)

        if self.frequency in (ScheduleFrequency.INTERVAL_HOURS, ScheduleFrequency.INTERVAL_MINUTES):
            cur_t = dt.time()
            if self.start_time and cur_t < self.start_time:
                return False
            if self.end_time and cur_t > self.end_time:
                return False
            return True

        return self.get_active_time_slot(dt) is not None

    def _is_within_once_window(self, dt: datetime) -> bool:
        assert self.run_at is not None
        target = self.run_at.replace(second=0, microsecond=0)
        current = dt.replace(second=0, microsecond=0)

        if self.tolerance_mode == ToleranceMode.EXACT:
            return abs((current - target).total_seconds()) <= 60

        if self.tolerance_mode == ToleranceMode.UNTIL_HOUR:
            end_dt = datetime.combine(target.date(), time(0, 0)) + timedelta(hours=self.tolerance_value)
            if end_dt <= target:
                end_dt = target + timedelta(hours=1)
            return target <= dt < end_dt

        if self.tolerance_mode == ToleranceMode.WINDOW_HOURS:
            end_dt = target + timedelta(hours=self.tolerance_value)
            return target <= dt < end_dt

        return False

    def get_active_time_slot(self, dt: datetime) -> time | None:
        for tod in self.times_of_day:
            if self.is_time_within_slot_window(tod, dt):
                return tod
        return None

    def is_time_within_slot_window(self, tod: time, dt: datetime) -> bool:
        target_minutes = tod.hour * 60 + tod.minute
        current_minutes = dt.hour * 60 + dt.minute

        if self.tolerance_mode == ToleranceMode.EXACT:
            return abs(current_minutes - target_minutes) <= 1

        if self.tolerance_mode == ToleranceMode.UNTIL_HOUR:
            start_minutes = target_minutes
            end_minutes = self.tolerance_value * 60
            if end_minutes <= start_minutes:
                end_minutes = start_minutes + 60
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
    keep_open: bool = True
    target_type: TargetType = field(default=TargetType.HERDR, init=False)


@dataclass(slots=True)
class BackgroundTargetConfig:
    notify_on_complete: bool = True
    target_type: TargetType = field(default=TargetType.BACKGROUND, init=False)


TargetConfig = TerminalTargetConfig | HerdrTargetConfig | BackgroundTargetConfig


@dataclass(slots=True)
class CommandAction:
    command: str
    action_type: ActionType = field(default=ActionType.COMMAND, init=False)

    def compile(self) -> str:
        return self.command.strip()


@dataclass(slots=True)
class AgentAction:
    harness: AIHarness
    prompt: str
    action_type: ActionType = field(default=ActionType.AGENT, init=False)

    def compile(self) -> str:
        escaped_prompt = shlex.quote(self.prompt.strip())
        match self.harness:
            case AIHarness.CLAUDE:
                return f"claude {escaped_prompt}"
            case AIHarness.ANTIGRAVITY:
                return f"agy {escaped_prompt}"
            case AIHarness.CURSOR:
                return f"cursor {escaped_prompt}"
            case AIHarness.CODEX:
                return f"codex {escaped_prompt}"


JobAction = CommandAction | AgentAction


@dataclass(slots=True, frozen=True)
class HarnessInfo:
    harness: AIHarness
    display_name: str
    cli: str
    color: str
    symbol: str = ""


HARNESS_INFO: dict[AIHarness, HarnessInfo] = {
    AIHarness.CLAUDE: HarnessInfo(
        harness=AIHarness.CLAUDE,
        display_name="Claude Code",
        cli="claude",
        color="#F97316",
        symbol="",
    ),
    AIHarness.ANTIGRAVITY: HarnessInfo(
        harness=AIHarness.ANTIGRAVITY,
        display_name="Antigravity",
        cli="agy",
        color="#3B82F6",
        symbol="",
    ),
    AIHarness.CURSOR: HarnessInfo(
        harness=AIHarness.CURSOR,
        display_name="Cursor",
        cli="cursor",
        color="#94A3B8",
        symbol="",
    ),
    AIHarness.CODEX: HarnessInfo(
        harness=AIHarness.CODEX,
        display_name="Codex",
        cli="codex",
        color="#FFFFFF",
        symbol="",
    ),
}


@dataclass(slots=True, init=False)
class Job:
    id: str
    name: str
    cwd: str
    schedule: SchedulePolicy
    target: TargetConfig
    action: JobAction
    is_paused: bool
    created_at: datetime
    folder: str | None

    def __init__(
        self,
        id: str,
        name: str,
        cwd: str,
        arg4: SchedulePolicy | str | None = None,
        arg5: TargetConfig | SchedulePolicy | None = None,
        arg6: TargetConfig | JobAction | None = None,
        action: JobAction | None = None,
        command: str | None = None,
        schedule: SchedulePolicy | None = None,
        target: TargetConfig | None = None,
        is_paused: bool = False,
        created_at: datetime | None = None,
        folder: str | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.cwd = cwd

        resolved_schedule: SchedulePolicy | None = schedule
        resolved_target: TargetConfig | None = target
        resolved_command: str | None = command
        resolved_action: JobAction | None = action

        if isinstance(arg4, str):
            resolved_command = arg4
            if isinstance(arg5, SchedulePolicy):
                resolved_schedule = arg5
            if isinstance(arg6, (TerminalTargetConfig, HerdrTargetConfig, BackgroundTargetConfig)):
                resolved_target = arg6
        elif isinstance(arg4, SchedulePolicy):
            resolved_schedule = arg4
            if isinstance(arg5, (TerminalTargetConfig, HerdrTargetConfig, BackgroundTargetConfig)):
                resolved_target = arg5
            if isinstance(arg6, (CommandAction, AgentAction)):
                resolved_action = arg6

        if resolved_schedule is None:
            raise ValueError("Job requires a SchedulePolicy")
        if resolved_target is None:
            resolved_target = HerdrTargetConfig(space="Roostr")

        self.schedule = resolved_schedule
        self.target = resolved_target

        if resolved_action is not None:
            self.action = resolved_action
        elif resolved_command is not None:
            self.action = CommandAction(command=resolved_command)
        else:
            raise ValueError("Job requires either an action or a command")

        self.is_paused = is_paused
        self.created_at = created_at or datetime.now()

        parsed_folder = None
        if folder:
            parts = [p.strip() for p in folder.strip().strip("/").split("/") if p.strip()]
            if len(parts) > 2:
                raise ValueError(f"Folder hierarchy cannot exceed 2 levels (got '{folder}')")
            parsed_folder = "/".join(parts) if parts else None
        self.folder = parsed_folder

    @property
    def command(self) -> str:
        return self.action.compile()

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
        tpl = self.target.tab_template or "{job.name} {DD}/{MM}"
        return (
            tpl.replace("{job.name}", self.name)
            .replace("{YYYY}", dt.strftime("%Y"))
            .replace("{MM}", dt.strftime("%m"))
            .replace("{DD}", dt.strftime("%d"))
            .replace("{HH}", dt.strftime("%H"))
            .replace("{mm}", dt.strftime("%M"))
            .replace("{YYYY-MM-DD}", dt.strftime("%Y-%m-%d"))
        )

    def to_dict(self) -> dict:
        target_info: dict = {
            "type": self.target.target_type.value,
        }
        if isinstance(self.target, TerminalTargetConfig):
            target_info["app"] = self.target.app.value
            target_info["keep_open"] = self.target.keep_open
        elif isinstance(self.target, HerdrTargetConfig):
            target_info["space"] = self.target.space
            target_info["tab_template"] = self.target.tab_template
            target_info["keep_open"] = self.target.keep_open
        elif isinstance(self.target, BackgroundTargetConfig):
            target_info["notify_on_complete"] = self.target.notify_on_complete

        action_info: dict = {
            "type": self.action.action_type.value,
            "command": self.command,
        }
        if isinstance(self.action, AgentAction):
            action_info["harness"] = self.action.harness.value
            action_info["prompt"] = self.action.prompt

        return {
            "id": self.id,
            "name": self.name,
            "cwd": self.cwd,
            "folder": self.folder,
            "is_paused": self.is_paused,
            "created_at": self.created_at.isoformat(),
            "action": action_info,
            "target": target_info,
            "schedule": {
                "frequency": self.schedule.frequency.value,
                "interval_value": self.schedule.interval_value,
                "days_of_week": list(self.schedule.days_of_week),
                "times_of_day": [t.strftime("%H:%M") for t in self.schedule.times_of_day],
                "start_time": self.schedule.start_time.strftime("%H:%M") if self.schedule.start_time else None,
                "end_time": self.schedule.end_time.strftime("%H:%M") if self.schedule.end_time else None,
                "run_at": self.schedule.run_at.isoformat() if self.schedule.run_at else None,
                "tolerance_mode": self.schedule.tolerance_mode.value,
                "tolerance_value": self.schedule.tolerance_value,
            },
        }


@dataclass(slots=True)
class ExecutionRecord:
    id: int | None
    job_id: str
    timestamp: datetime
    trigger_type: TriggerType
    status: ExecutionStatus
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "timestamp": self.timestamp.isoformat(),
            "trigger_type": self.trigger_type.value,
            "status": self.status.value,
            "details": self.details,
        }
