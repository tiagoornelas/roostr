import re
import shlex
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, time

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


@dataclass(slots=True)
class SchedulePolicy:
    days_of_week: tuple[int, ...]  # 0=Monday ... 6=Sunday
    time_of_day: time = time(8, 0)
    tolerance_mode: ToleranceMode = ToleranceMode.EXACT
    tolerance_value: int = 0  # until_hour (e.g. 12) or window_hours (e.g. 4)
    frequency: ScheduleFrequency = ScheduleFrequency.DAILY
    interval_value: int = 1

    def is_active_on_weekday(self, weekday: int) -> bool:
        return weekday in self.days_of_week

    def is_within_window(self, dt: datetime) -> bool:
        if self.frequency in (ScheduleFrequency.INTERVAL_HOURS, ScheduleFrequency.INTERVAL_MINUTES):
            return True

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
            raise ValueError("Job requires a TargetConfig")

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


@dataclass(slots=True)
class ExecutionRecord:
    id: int | None
    job_id: str
    timestamp: datetime
    trigger_type: TriggerType
    status: ExecutionStatus
    details: str = ""
