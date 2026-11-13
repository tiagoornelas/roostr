import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Label, ListItem, ListView, Static

from roostr.application.ports import DaemonServicePort, JobRepositoryPort
from roostr.application.use_cases.daemon import calculate_next_schedule_event
from roostr.domain.enums import AIHarness, ExecutionStatus, ScheduleFrequency, TriggerType
from roostr.domain.models import (
    HARNESS_INFO,
    AgentAction,
    BackgroundTargetConfig,
    ExecutionRecord,
    HerdrTargetConfig,
    Job,
    TerminalTargetConfig,
)
from roostr.i18n.schema import Messages


class JobListItem(ListItem):
    def __init__(
        self,
        job: Job,
        ran_today: bool,
        run_count: int,
        msg: Messages,
        indent: int = 0,
        last_status: ExecutionStatus | None = None,
        is_executed: bool = False,
    ):
        super().__init__()
        self.job = job
        self.ran_today = ran_today
        self.run_count = run_count
        self.msg = msg
        self.indent = indent
        self.last_status = last_status
        self.is_executed = is_executed
        if indent == 1:
            self.add_class("indent-1")
        elif indent >= 2:
            self.add_class("indent-2")

    def _get_status_markups(self) -> tuple[str, str, str]:
        if self.job.is_paused:
            status_dot = "[dim]●[/]"
            badge_markup = f"[dim]{self.msg.status_paused}[/]"
            name_markup = f"[dim]{self.job.name}[/]"
        elif self.last_status == ExecutionStatus.FAILED:
            status_dot = "[bold red]●[/]"
            badge_markup = f"[bold red]{self.msg.status_error}[/]"
            name_markup = f"[bold]{self.job.name}[/]"
        elif self.job.schedule.frequency == ScheduleFrequency.ONCE:
            if self.is_executed:
                status_dot = "[bold green]●[/]"
                badge_markup = f"[bold green]{self.msg.status_done}[/]"
                name_markup = f"[dim]{self.job.name}[/]"
            else:
                status_dot = "[bold yellow]●[/]"
                badge_markup = f"[bold yellow]{self.msg.status_waiting}[/]"
                name_markup = f"[bold]{self.job.name}[/]"
        elif self.ran_today:
            status_dot = "[bold green]●[/]"
            badge_markup = f"[bold green]{self.msg.status_running_today}[/]"
            name_markup = f"[bold]{self.job.name}[/]"
        else:
            status_dot = "[bold yellow]●[/]"
            badge_markup = f"[bold yellow]{self.msg.status_waiting}[/]"
            name_markup = f"[bold]{self.job.name}[/]"
        return status_dot, badge_markup, name_markup

    def update_status(
        self,
        ran_today: bool,
        last_status: ExecutionStatus | None,
        run_count: int,
        is_paused: bool | None = None,
        is_executed: bool | None = None,
    ) -> bool:
        if (
            self.ran_today == ran_today
            and self.last_status == last_status
            and self.run_count == run_count
            and (is_paused is None or self.job.is_paused == is_paused)
            and (is_executed is None or self.is_executed == is_executed)
        ):
            return False

        if is_paused is not None:
            self.job.is_paused = is_paused
        if is_executed is not None:
            self.is_executed = is_executed
        self.ran_today = ran_today
        self.last_status = last_status
        self.run_count = run_count

        status_dot, badge_markup, name_markup = self._get_status_markups()
        try:
            self.query_one(".job-card-name", Label).update(f"{status_dot} {name_markup}")
            self.query_one(".job-card-badge", Label).update(badge_markup)
        except Exception:
            pass
        return True

    def compose(self) -> ComposeResult:
        status_dot, badge_markup, name_markup = self._get_status_markups()

        if self.job.schedule.frequency == ScheduleFrequency.INTERVAL_HOURS:
            sched_str = self.msg.lbl_every_hours.format(val=self.job.schedule.interval_value)
            if self.job.schedule.start_time and self.job.schedule.end_time:
                sched_str += f" ({self.job.schedule.start_time.strftime('%H:%M')}–{self.job.schedule.end_time.strftime('%H:%M')})"
            elif self.job.schedule.start_time:
                sched_str += f" (>{self.job.schedule.start_time.strftime('%H:%M')})"
            elif self.job.schedule.end_time:
                sched_str += f" (<{self.job.schedule.end_time.strftime('%H:%M')})"
        elif self.job.schedule.frequency == ScheduleFrequency.INTERVAL_MINUTES:
            sched_str = self.msg.lbl_every_minutes.format(val=self.job.schedule.interval_value)
            if self.job.schedule.start_time and self.job.schedule.end_time:
                sched_str += f" ({self.job.schedule.start_time.strftime('%H:%M')}–{self.job.schedule.end_time.strftime('%H:%M')})"
            elif self.job.schedule.start_time:
                sched_str += f" (>{self.job.schedule.start_time.strftime('%H:%M')})"
            elif self.job.schedule.end_time:
                sched_str += f" (<{self.job.schedule.end_time.strftime('%H:%M')})"
        else:
            if len(self.job.schedule.times_of_day) > 1:
                times_joined = ", ".join(t.strftime("%H:%M") for t in self.job.schedule.times_of_day)
                sched_str = (
                    times_joined
                    if len(times_joined) <= 25
                    else self.msg.lbl_times_per_day.format(count=len(self.job.schedule.times_of_day))
                )
            else:
                sched_str = self.job.schedule.time_of_day.strftime("%H:%M")
        if len(self.job.schedule.days_of_week) == 5 and self.job.schedule.days_of_week == (0, 1, 2, 3, 4):
            days_str = self.msg.days_weekdays_short
        elif len(self.job.schedule.days_of_week) == 7:
            days_str = self.msg.days_everyday_short
        else:
            days_str = f"{len(self.job.schedule.days_of_week)}d"

        target_name = "Herdr"
        if isinstance(self.job.target, HerdrTargetConfig):
            target_name = f"Herdr ({self.job.target.space})" if self.job.target.space else "Herdr"
        elif isinstance(self.job.target, BackgroundTargetConfig):
            target_name = self.msg.target_opt_background_short
        elif isinstance(self.job.target, TerminalTargetConfig):
            target_name = self.msg.target_opt_terminal_short

        with Horizontal(classes="job-card-top"):
            yield Label(f"{status_dot} {name_markup}", classes="job-card-name")
            yield Label(badge_markup, classes="job-card-badge")
        if self.job.schedule.frequency == ScheduleFrequency.ONCE and self.job.schedule.run_at is not None:
            sub_text = f"{self.job.schedule.run_at.strftime('%Y-%m-%d %H:%M')} • {target_name}"
        else:
            sub_text = f"{days_str} {sched_str} • {target_name}"
        with Horizontal(classes="job-card-sub"):
            yield Label(
                f"[dim]{sub_text}[/]",
                classes="job-card-details",
            )


class FolderHeaderItem(ListItem):
    def __init__(self, folder_name: str, count: int, is_collapsed: bool):
        super().__init__()
        self.folder_name = folder_name
        self.count = count
        self.is_collapsed = is_collapsed

    def compose(self) -> ComposeResult:
        arrow = "▶" if self.is_collapsed else "▼"
        with Horizontal(classes="folder-header-row"):
            yield Label(f"[bold]{arrow} {self.folder_name.upper()}[/]", classes="folder-header-title")
            yield Label(f"[dim]{self.count}[/]", classes="folder-header-badge")


class SubfolderHeaderItem(ListItem):
    def __init__(self, subfolder_key: str, subfolder_name: str, count: int, is_collapsed: bool):
        super().__init__()
        self.subfolder_key = subfolder_key
        self.subfolder_name = subfolder_name
        self.count = count
        self.is_collapsed = is_collapsed

    def compose(self) -> ComposeResult:
        arrow = "▶" if self.is_collapsed else "▼"
        with Horizontal(classes="subfolder-header-row"):
            yield Label(f"  [dim]{arrow}[/] [bold]{self.subfolder_name}[/]", classes="subfolder-header-title")
            yield Label(f"[dim]{self.count}[/]", classes="subfolder-header-badge")


class UngroupedHeaderItem(ListItem):
    def __init__(self, label: str):
        super().__init__()
        self.label = label

    def compose(self) -> ComposeResult:
        with Horizontal(classes="ungrouped-header-row"):
            yield Label(f"[dim]─── {self.label} ───[/]", classes="ungrouped-header-title")


class OneTimeSectionHeaderItem(ListItem):
    def __init__(self, section_key: str, title: str, count: int, is_collapsed: bool):
        super().__init__()
        self.section_key = section_key
        self.title = title
        self.count = count
        self.is_collapsed = is_collapsed

    def compose(self) -> ComposeResult:
        arrow = "▶" if self.is_collapsed else "▼"
        with Horizontal(classes="folder-header-row"):
            yield Label(f"[bold]{arrow} {self.title}[/]", classes="folder-header-title")
            yield Label(f"[dim]{self.count}[/]", classes="folder-header-badge")


def find_claude_session_id(cwd: str, dt: datetime) -> str | None:
    try:
        sanitized = cwd.replace("/", "-")
        pdir = Path.home() / ".claude" / "projects" / sanitized
        if not pdir.exists():
            return None

        target_ts = dt.timestamp()
        candidates: list[tuple[float, str]] = []
        for f in pdir.glob("*.jsonl"):
            if len(f.stem) < 20:
                continue
            mtime = f.stat().st_mtime
            diff = abs(mtime - target_ts)
            if diff <= 14400:  # 4 hours tolerance
                candidates.append((diff, f.stem))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
    except Exception:
        pass
    return None


def get_session_command(job: Job, dt: datetime) -> str:
    cwd = job.cwd
    if isinstance(job.action, AgentAction):
        match job.action.harness:
            case AIHarness.CLAUDE:
                sess_id = find_claude_session_id(cwd, dt)
                if sess_id:
                    return f'cd "{cwd}" && claude --resume {sess_id}'
                return f'cd "{cwd}" && claude --resume'
            case AIHarness.ANTIGRAVITY:
                return f'cd "{cwd}" && agy'
            case AIHarness.CURSOR:
                return f'cd "{cwd}" && cursor'
            case AIHarness.CODEX:
                return f'cd "{cwd}" && codex'
    return f'cd "{cwd}" && {job.command}'


def try_redirect_to_herdr_tab(tab_id: str) -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ["herdr-app", "ls"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return False, "Herdr is offline"

        data = json.loads(res.stdout)
        for space in data.get("spaces", []):
            space_id = space.get("id")
            for tab in space.get("tabs", []):
                if tab.get("id") == tab_id:
                    tab_name = tab.get("name") or "Tab"
                    if space_id:
                        subprocess.run(
                            ["herdr-app", "do", "space.select", "--id", space_id],
                            capture_output=True,
                            timeout=2,
                            check=False,
                        )
                    subprocess.run(
                        ["herdr-app", "do", "tab.select", "--id", tab_id],
                        capture_output=True,
                        timeout=2,
                        check=False,
                    )
                    subprocess.run(
                        ["osascript", "-e", 'tell application "Herdr" to activate'],
                        capture_output=True,
                        timeout=2,
                        check=False,
                    )
                    return True, tab_name
    except Exception:
        pass
    return False, "Tab not found"


class ExecutionRow(Static):
    DEFAULT_CSS = """
    ExecutionRow {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
        background: transparent;
        border-left: solid transparent;
    }

    ExecutionRow:hover {
        background: $panel;
        border-left: solid $primary;
    }
    """

    def __init__(
        self,
        record: ExecutionRecord,
        cleaned_details: str,
        herdr_tab_id: str | None,
        job: Job,
        msg: Messages,
    ):
        super().__init__()
        self.record = record
        self.cleaned_details = cleaned_details
        self.herdr_tab_id = herdr_tab_id
        self.job = job
        self.msg = msg

    def on_mount(self) -> None:
        ts = self.record.timestamp.strftime("%d/%m %H:%M:%S")
        color = "green" if self.record.status == ExecutionStatus.SUCCESS else "yellow"
        if self.record.status == ExecutionStatus.FAILED:
            color = "red"

        status_labels = {
            ExecutionStatus.SUCCESS: self.msg.status_history_success,
            ExecutionStatus.SKIPPED_ALREADY_RAN: self.msg.status_history_already_ran,
            ExecutionStatus.SKIPPED_OUTSIDE_WINDOW: self.msg.status_history_outside_window,
            ExecutionStatus.SKIPPED_TARGET_OFFLINE: self.msg.status_history_target_offline,
            ExecutionStatus.FAILED: self.msg.status_history_failed,
        }
        trigger_labels = {
            TriggerType.SCHEDULED: self.msg.trigger_history_scheduled,
            TriggerType.MANUAL: self.msg.trigger_history_manual,
        }
        status_display = status_labels.get(self.record.status, self.record.status.value)
        trigger_display = trigger_labels.get(self.record.trigger_type, self.record.trigger_type.value)

        copy_hint = f"  [dim cyan]{self.msg.lbl_click_to_copy}[/]"
        self.update(
            f"[dim]{ts}[/] [{color}]{status_display}[/] ([dim]{trigger_display}[/]): {self.cleaned_details}{copy_hint}"
        )

    def on_click(self, event: events.Click) -> None:
        # 1. If tab is known, try redirecting directly to Herdr tab
        if self.herdr_tab_id:
            redirected, tab_name = try_redirect_to_herdr_tab(self.herdr_tab_id)
            if redirected:
                self.app.notify(
                    self.msg.notify_redirected_herdr.format(tab=tab_name),
                    title="Herdr",
                )
                return

        # 2. Otherwise copy the specific terminal session command to clipboard
        cmd = get_session_command(self.job, self.record.timestamp)
        try:
            subprocess.run(["pbcopy"], input=cmd.encode("utf-8"), check=True)
        except Exception:
            pass
        try:
            self.app.copy_to_clipboard(cmd)
        except Exception:
            pass

        self.app.notify(
            self.msg.notify_copied_attach.format(cmd=cmd),
            title="Terminal Session",
        )


class DashboardScreen(Screen):
    BINDINGS = [
        Binding("tab", "app.switch_tab", "Switch Tab", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    DashboardScreen {
        layout: vertical;
        background: $background;
        color: $foreground;
    }

    #main-content {
        height: 1fr;
        background: $background;
    }

    #view-tabs {
        height: 2;
        layout: horizontal;
        border-bottom: solid $panel;
        background: $background;
        padding: 0 1;
    }

    .view-tab-btn {
        width: auto;
        height: 2;
        padding: 0 2;
        color: $secondary;
        content-align: center middle;
    }

    .view-tab-btn:hover {
        color: $foreground;
    }

    .view-tab-btn.-active {
        color: $primary;
        text-style: bold;
        border-bottom: solid $primary;
    }

    #sidebar {
        width: 40%;
        height: 100%;
        border-right: solid $panel;
        background: $background;
    }

    #jobs-list {
        height: 1fr;
        background: $background;
        padding: 0;
        border: none;
    }

    #jobs-list:focus {
        background-tint: transparent 0%;
    }

    #jobs-list > FolderHeaderItem,
    #jobs-list > OneTimeSectionHeaderItem {
        height: 1;
        padding: 0 1;
        margin: 0 1;
        background: $panel;
        color: $foreground;
        border: none;
    }

    #jobs-list > FolderHeaderItem:hover,
    #jobs-list > OneTimeSectionHeaderItem:hover {
        background: $primary 20%;
    }

    #jobs-list > FolderHeaderItem.-highlight,
    #jobs-list > OneTimeSectionHeaderItem.-highlight {
        background: $panel;
        color: $foreground;
        border-left: thick $primary;
    }

    .folder-header-row {
        height: 1;
        align: left middle;
    }

    .folder-header-title {
        width: 1fr;
        text-style: bold;
        color: $foreground;
    }

    .folder-header-badge {
        width: auto;
        color: $secondary;
        padding: 0 1;
    }

    #jobs-list > SubfolderHeaderItem {
        height: 1;
        padding: 0 1 0 2;
        margin: 0 1;
        background: transparent;
        color: $secondary;
        border: none;
    }

    #jobs-list > SubfolderHeaderItem:hover {
        background: $panel;
    }

    #jobs-list > SubfolderHeaderItem.-highlight {
        background: $panel;
        color: $foreground;
        border-left: tall $primary;
    }

    .subfolder-header-row {
        height: 1;
        align: left middle;
    }

    .subfolder-header-title {
        width: 1fr;
        color: $secondary;
    }

    .subfolder-header-badge {
        width: auto;
        color: $secondary;
        padding: 0 1;
    }

    #jobs-list > UngroupedHeaderItem {
        height: 1;
        padding: 0 1;
        margin: 0 1;
        background: transparent;
        border: none;
    }

    #jobs-list > UngroupedHeaderItem:hover,
    #jobs-list > UngroupedHeaderItem.-highlight {
        background: transparent;
        border: none;
    }

    .ungrouped-header-row {
        height: 1;
        align: center middle;
    }

    .ungrouped-header-title {
        color: $secondary;
        text-style: bold;
        text-align: center;
        width: 100%;
    }

    #jobs-list > JobListItem {
        height: auto;
        padding: 0 1;
        margin: 0 1;
        background: transparent;
        border: round $panel;
        color: $foreground;
    }

    #jobs-list > JobListItem.indent-1 {
        margin: 0 1 0 2;
    }

    #jobs-list > JobListItem.indent-2 {
        margin: 0 1 0 4;
    }

    #jobs-list > JobListItem:hover,
    #jobs-list > JobListItem.-hovered {
        background: $panel;
    }

    #jobs-list > JobListItem.-highlight,
    #jobs-list:focus > JobListItem.-highlight,
    #jobs-list > JobListItem.-selected,
    #jobs-list > JobListItem:focus {
        background: $panel;
        color: $foreground;
        border: round $primary;
    }

    .job-card-top {
        height: 1;
        align: left middle;
    }

    .job-card-name {
        width: 1fr;
        color: $foreground;
    }

    .job-card-badge {
        width: auto;
    }

    .job-card-sub {
        height: 1;
        margin-top: 0;
    }

    .job-card-details {
        color: $secondary;
        padding-left: 2;
    }

    #inspector {
        width: 60%;
        height: 100%;
        padding: 1 2;
        background: $background;
        color: $foreground;
    }

    #inspector-details {
        background: $background;
        color: $foreground;
    }

    #inspector-history {
        margin-top: 1;
        height: auto;
    }

    #bottom-bar {
        dock: bottom;
        height: 1;
        layout: horizontal;
        background: $panel;
    }

    #footer-brand {
        width: auto;
        padding: 0 1;
        color: $foreground;
        text-style: bold;
        background: transparent;
    }

    #footer-status {
        width: auto;
        padding: 0 1;
        background: transparent;
    }

    #bottom-bar Footer {
        width: 1fr;
        dock: none;
        background: transparent;
    }
    """

    def __init__(
        self,
        storage: JobRepositoryPort,
        messages: Messages,
        theme_name: str = "night",
        daemon_service: DaemonServicePort | None = None,
    ):
        super().__init__()
        self.storage = storage
        self.msg = messages
        self.active_theme = theme_name
        self.daemon_service = daemon_service
        self.selected_job: Job | None = None
        self.active_tab: str = "recurring"
        self.collapsed_folders: set[str] = set()
        self.collapsed_subfolders: set[str] = set()
        self.collapsed_onetime_sections: set[str] = set()
        self._last_tab_job_ids: list[str] = []
        self._last_executed_ids: set[str] = set()
        self._refresh_timer: Timer | None = None

    def get_daemon_status_markup(self) -> str:
        is_active = False
        if self.daemon_service:
            try:
                is_active = self.daemon_service.is_running()
            except Exception:
                is_active = False
        if is_active:
            return f"[bold green]●[/] [green]{self.msg.status_active}[/]"
        return f"[dim]○ {self.msg.status_inactive}[/]"

    def compose(self) -> ComposeResult:
        with Horizontal(id="view-tabs"):
            yield Label(f"{self.msg.tab_view_recurring} (0)", id="tab-recurring", classes="view-tab-btn -active")
            yield Label(f"{self.msg.tab_view_onetime} (0)", id="tab-onetime", classes="view-tab-btn")

        with Horizontal(id="main-content"):
            with Vertical(id="sidebar"):
                yield ListView(id="jobs-list")

            with VerticalScroll(id="inspector"):
                yield Static(id="inspector-details")
                yield Vertical(id="inspector-history")

        with Horizontal(id="bottom-bar"):
            yield Label("🐓 roostr", id="footer-brand")
            yield Label(self.get_daemon_status_markup(), id="footer-status")
            yield Footer()

    def switch_view_tab(self, tab: str | None = None) -> None:
        new_tab = (
            tab if tab in ("recurring", "onetime") else ("onetime" if self.active_tab == "recurring" else "recurring")
        )
        if new_tab == self.active_tab:
            return
        self.active_tab = new_tab
        try:
            rec_lbl = self.query_one("#tab-recurring", Label)
            one_lbl = self.query_one("#tab-onetime", Label)
            rec_lbl.set_class(self.active_tab == "recurring", "-active")
            one_lbl.set_class(self.active_tab == "onetime", "-active")
        except Exception:
            pass
        self.selected_job = None
        self.refresh_jobs()

    def on_click(self, event: events.Click) -> None:
        widget = event.widget
        if widget and widget.id == "tab-recurring":
            self.switch_view_tab("recurring")
        elif widget and widget.id == "tab-onetime":
            self.switch_view_tab("onetime")

    def on_mount(self) -> None:
        self.refresh_jobs()

    def schedule_next_refresh(self) -> None:
        if self._refresh_timer:
            try:
                self._refresh_timer.stop()
            except Exception:
                pass
            self._refresh_timer = None

        now = datetime.now()
        jobs = self.storage.list_jobs()
        next_event = calculate_next_schedule_event(jobs, now, self.storage)
        delay = max(0.5, (next_event - now).total_seconds())
        self._refresh_timer = self.set_timer(delay, self._on_scheduled_refresh)

    def _on_scheduled_refresh(self) -> None:
        self._refresh_timer = None
        self.auto_refresh_status()
        self.schedule_next_refresh()

    def auto_refresh_status(self) -> None:
        today = date.today()
        all_jobs = self.storage.list_jobs()
        executed_ids = self.storage.get_executed_job_ids()
        tab_jobs = [
            j
            for j in all_jobs
            if (
                j.schedule.frequency == ScheduleFrequency.ONCE
                if self.active_tab == "onetime"
                else j.schedule.frequency != ScheduleFrequency.ONCE
            )
        ]
        tab_job_ids = [j.id for j in tab_jobs]
        jobs_by_id = {j.id: j for j in tab_jobs}

        current_item_jobs = list(self.query(JobListItem))

        # 1. If jobs list or one-time execution bucket changed structurally, do full reload
        if tab_job_ids != self._last_tab_job_ids or (
            self.active_tab == "onetime" and executed_ids != self._last_executed_ids
        ):
            self.refresh_jobs(selected_job_id=self.selected_job.id if self.selected_job else None)
            return

        # 2. Update status of existing items in place
        selected_updated = False
        for item in current_item_jobs:
            fresh_job = jobs_by_id.get(item.job.id)
            is_paused = fresh_job.is_paused if fresh_job else None
            ran_today = self.storage.has_succeeded_on_date(item.job.id, today)
            run_count = self.storage.count_executions(item.job.id)
            last_exec = self.storage.get_last_execution(item.job.id)
            last_status = last_exec.status if last_exec else None
            is_executed = item.job.id in executed_ids

            changed = item.update_status(
                ran_today,
                last_status,
                run_count,
                is_paused=is_paused,
                is_executed=is_executed,
            )
            if changed and self.selected_job and self.selected_job.id == item.job.id:
                selected_updated = True

        # 3. If currently selected job had a status change, update inspector details as well
        if selected_updated and self.selected_job:
            fresh_selected = jobs_by_id.get(self.selected_job.id, self.selected_job)
            self.show_job_details(fresh_selected)

        # 4. Refresh footer daemon status
        try:
            self.query_one("#footer-status", Label).update(self.get_daemon_status_markup())
        except Exception:
            pass

    def get_current_focused_item(self) -> ListItem | None:
        jobs_list = self.query_one("#jobs-list", ListView)
        if jobs_list.index is not None and 0 <= jobs_list.index < len(jobs_list.children):
            item = jobs_list.children[jobs_list.index]
            if isinstance(item, ListItem):
                return item
        return None

    def update_theme(self, theme_name: str) -> None:
        self.active_theme = theme_name
        if self.selected_job:
            self.show_job_details(self.selected_job)

    def update_messages(self, messages: Messages) -> None:
        self.msg = messages
        try:
            self.query_one("#footer-status", Label).update(self.get_daemon_status_markup())
        except Exception:
            pass
        self.refresh_jobs(selected_job_id=self.selected_job.id if self.selected_job else None)
        focused = self.get_current_focused_item()
        if isinstance(focused, FolderHeaderItem):
            self.show_folder_details(focused.folder_name, focused.count, is_subfolder=False)
        elif isinstance(focused, SubfolderHeaderItem):
            self.show_folder_details(focused.subfolder_key, focused.count, is_subfolder=True)
        elif self.selected_job:
            self.show_job_details(self.selected_job)

    def refresh_jobs(self, selected_job_id: str | None = None) -> None:
        jobs_list = self.query_one("#jobs-list", ListView)
        jobs_list.clear()

        all_jobs = self.storage.list_jobs()
        executed_ids = self.storage.get_executed_job_ids()
        recurring_jobs = [j for j in all_jobs if j.schedule.frequency != ScheduleFrequency.ONCE]
        onetime_jobs = [j for j in all_jobs if j.schedule.frequency == ScheduleFrequency.ONCE]

        if selected_job_id:
            target_job = next((j for j in all_jobs if j.id == selected_job_id), None)
            if target_job:
                desired_tab = "onetime" if target_job.schedule.frequency == ScheduleFrequency.ONCE else "recurring"
                if desired_tab != self.active_tab:
                    self.active_tab = desired_tab

        try:
            rec_lbl = self.query_one("#tab-recurring", Label)
            one_lbl = self.query_one("#tab-onetime", Label)
            rec_lbl.update(f"{self.msg.tab_view_recurring} ({len(recurring_jobs)})")
            one_lbl.update(f"{self.msg.tab_view_onetime} ({len(onetime_jobs)})")
            rec_lbl.set_class(self.active_tab == "recurring", "-active")
            one_lbl.set_class(self.active_tab == "onetime", "-active")
        except Exception:
            pass

        self._last_executed_ids = executed_ids
        today = date.today()
        items_to_add: list[ListItem] = []
        job_index_map: dict[str, int] = {}

        if self.active_tab == "onetime":
            self._last_tab_job_ids = [j.id for j in onetime_jobs]
            scheduled_ot = sorted(
                [j for j in onetime_jobs if j.id not in executed_ids],
                key=lambda j: j.schedule.run_at or j.created_at,
            )
            executed_ot = sorted(
                [j for j in onetime_jobs if j.id in executed_ids],
                key=lambda j: (
                    le.timestamp if (le := self.storage.get_last_execution(j.id)) else j.schedule.run_at or j.created_at
                ),
                reverse=True,
            )

            sched_collapsed = "scheduled" in self.collapsed_onetime_sections
            items_to_add.append(
                OneTimeSectionHeaderItem(
                    "scheduled",
                    self.msg.section_onetime_scheduled,
                    len(scheduled_ot),
                    sched_collapsed,
                )
            )
            if not sched_collapsed:
                for job in scheduled_ot:
                    run_count = self.storage.count_executions(job.id)
                    last_exec = self.storage.get_last_execution(job.id)
                    last_status = last_exec.status if last_exec else None
                    item = JobListItem(
                        job,
                        False,
                        run_count,
                        self.msg,
                        indent=1,
                        last_status=last_status,
                        is_executed=False,
                    )
                    job_index_map[job.id] = len(items_to_add)
                    items_to_add.append(item)

            exec_collapsed = "executed" in self.collapsed_onetime_sections
            items_to_add.append(
                OneTimeSectionHeaderItem(
                    "executed",
                    self.msg.section_onetime_executed,
                    len(executed_ot),
                    exec_collapsed,
                )
            )
            if not exec_collapsed:
                for job in executed_ot:
                    run_count = self.storage.count_executions(job.id)
                    last_exec = self.storage.get_last_execution(job.id)
                    last_status = last_exec.status if last_exec else None
                    item = JobListItem(
                        job,
                        False,
                        run_count,
                        self.msg,
                        indent=1,
                        last_status=last_status,
                        is_executed=True,
                    )
                    job_index_map[job.id] = len(items_to_add)
                    items_to_add.append(item)
        else:
            jobs = recurring_jobs
            self._last_tab_job_ids = [j.id for j in jobs]

            # Build folder tree with all existing folders (including empty ones)
            all_folders = self.storage.list_folders() if hasattr(self.storage, "list_folders") else []
            folder_tree: dict[str, dict] = {}
            for f in all_folders:
                parts = [p.strip() for p in f.strip("/").split("/") if p.strip()]
                if not parts:
                    continue
                rf = parts[0]
                if rf not in folder_tree:
                    folder_tree[rf] = {"direct": [], "subfolders": {}}
                if len(parts) > 1:
                    sf = parts[1]
                    if sf not in folder_tree[rf]["subfolders"]:
                        folder_tree[rf]["subfolders"][sf] = []

            root_jobs: list[Job] = []
            for job in jobs:
                if not job.folder:
                    root_jobs.append(job)
                else:
                    rf = job.root_folder or "Other"
                    sf = job.subfolder
                    if rf not in folder_tree:
                        folder_tree[rf] = {"direct": [], "subfolders": {}}
                    if sf:
                        if sf not in folder_tree[rf]["subfolders"]:
                            folder_tree[rf]["subfolders"][sf] = []
                        folder_tree[rf]["subfolders"][sf].append(job)
                    else:
                        folder_tree[rf]["direct"].append(job)

            # 1. Folders and Subfolders come FIRST
            for rf in sorted(folder_tree.keys()):
                data = folder_tree[rf]
                is_rf_collapsed = rf in self.collapsed_folders
                count_rf = len(data["direct"]) + sum(len(j) for j in data["subfolders"].values())
                items_to_add.append(FolderHeaderItem(rf, count_rf, is_rf_collapsed))

                if not is_rf_collapsed:
                    for job in data["direct"]:
                        ran_today = self.storage.has_succeeded_on_date(job.id, today)
                        run_count = self.storage.count_executions(job.id)
                        last_exec = self.storage.get_last_execution(job.id)
                        last_status = last_exec.status if last_exec else None
                        item = JobListItem(job, ran_today, run_count, self.msg, indent=1, last_status=last_status)
                        job_index_map[job.id] = len(items_to_add)
                        items_to_add.append(item)

                    for sf in sorted(data["subfolders"].keys()):
                        sf_jobs = data["subfolders"][sf]
                        sf_key = f"{rf}/{sf}"
                        is_sf_collapsed = sf_key in self.collapsed_subfolders
                        count_sf = len(sf_jobs)
                        items_to_add.append(SubfolderHeaderItem(sf_key, sf, count_sf, is_sf_collapsed))

                        if not is_sf_collapsed:
                            for job in sf_jobs:
                                ran_today = self.storage.has_succeeded_on_date(job.id, today)
                                run_count = self.storage.count_executions(job.id)
                                last_exec = self.storage.get_last_execution(job.id)
                                last_status = last_exec.status if last_exec else None
                                item = JobListItem(
                                    job, ran_today, run_count, self.msg, indent=2, last_status=last_status
                                )
                                job_index_map[job.id] = len(items_to_add)
                                items_to_add.append(item)

            # 2. Ungrouped / root jobs come LAST ("os sem pasta ficam por ultimo")
            if root_jobs:
                if folder_tree:
                    items_to_add.append(UngroupedHeaderItem(self.msg.lbl_ungrouped))
                for job in root_jobs:
                    ran_today = self.storage.has_succeeded_on_date(job.id, today)
                    run_count = self.storage.count_executions(job.id)
                    last_exec = self.storage.get_last_execution(job.id)
                    last_status = last_exec.status if last_exec else None
                    item = JobListItem(job, ran_today, run_count, self.msg, indent=0, last_status=last_status)
                    job_index_map[job.id] = len(items_to_add)
                    items_to_add.append(item)

        for item in items_to_add:
            jobs_list.append(item)

        target_idx: int | None = None
        if selected_job_id and selected_job_id in job_index_map:
            target_idx = job_index_map[selected_job_id]
        elif job_index_map:
            first_job_id = next(iter(job_index_map.keys()))
            target_idx = job_index_map[first_job_id]

        if target_idx is not None:
            jobs_list.index = target_idx
            selected_item = items_to_add[target_idx]
            if isinstance(selected_item, JobListItem):
                self.show_job_details(selected_item.job)
        else:
            self.selected_job = None
            inspector_details = self.query_one("#inspector-details", Static)
            inspector_details.update(f"[dim]{self.msg.empty_state_text}[/]")
            history_container = self.query_one("#inspector-history", Vertical)
            history_container.remove_children()

        self.schedule_next_refresh()

    @on(ListView.Selected, "#jobs-list")
    def on_item_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, FolderHeaderItem):
            rf = event.item.folder_name
            if rf in self.collapsed_folders:
                self.collapsed_folders.remove(rf)
            else:
                self.collapsed_folders.add(rf)
            self.refresh_jobs(selected_job_id=self.selected_job.id if self.selected_job else None)
        elif isinstance(event.item, SubfolderHeaderItem):
            sf_key = event.item.subfolder_key
            if sf_key in self.collapsed_subfolders:
                self.collapsed_subfolders.remove(sf_key)
            else:
                self.collapsed_subfolders.add(sf_key)
            self.refresh_jobs(selected_job_id=self.selected_job.id if self.selected_job else None)
        elif isinstance(event.item, OneTimeSectionHeaderItem):
            sec_key = event.item.section_key
            if sec_key in self.collapsed_onetime_sections:
                self.collapsed_onetime_sections.remove(sec_key)
            else:
                self.collapsed_onetime_sections.add(sec_key)
            self.refresh_jobs(selected_job_id=self.selected_job.id if self.selected_job else None)
        elif isinstance(event.item, JobListItem):
            self.show_job_details(event.item.job)
            if hasattr(self.app, "action_edit_job"):
                self.app.action_edit_job()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, JobListItem):
            today = date.today()
            ran_today = self.storage.has_succeeded_on_date(event.item.job.id, today)
            run_count = self.storage.count_executions(event.item.job.id)
            last_exec = self.storage.get_last_execution(event.item.job.id)
            last_status = last_exec.status if last_exec else None
            event.item.update_status(ran_today, last_status, run_count)
            self.show_job_details(event.item.job)
        elif event.item and isinstance(event.item, FolderHeaderItem):
            self.show_folder_details(event.item.folder_name, event.item.count, is_subfolder=False)
        elif event.item and isinstance(event.item, SubfolderHeaderItem):
            self.show_folder_details(event.item.subfolder_key, event.item.count, is_subfolder=True)

    def show_folder_details(self, folder_name: str, count: int, is_subfolder: bool = False) -> None:
        self.selected_job = None
        primary_color = (
            self.app.current_theme.primary
            if hasattr(self.app, "current_theme") and self.app.current_theme
            else "#ffffff"
        )
        folder_type = self.msg.lbl_subfolder_title if is_subfolder else self.msg.lbl_folder_title
        details_markup = f"""
[bold size=14]{folder_name.upper()}[/]  [dim]({folder_type})[/]
[dim]{self.msg.inspector_active_jobs}:[/]  [bold]{count}[/]

[bold {primary_color}]{self.msg.folder_actions_title}[/]
[dim]• {self.msg.folder_action_move}[/]
[dim]• {self.msg.folder_action_create}[/]
[dim]• {self.msg.folder_action_edit}[/]
[dim]• {self.msg.folder_action_delete}[/]
"""
        self.query_one("#inspector-details", Static).update(details_markup)
        history_container = self.query_one("#inspector-history", Vertical)
        history_container.remove_children()

    def show_job_details(self, job: Job) -> None:
        self.selected_job = job
        today = date.today()
        ran_today = self.storage.has_succeeded_on_date(job.id, today)
        total_runs = self.storage.count_executions(job.id)
        recent_records = self.storage.get_recent_executions(job.id, limit=5)
        last_exec = self.storage.get_last_execution(job.id)
        last_status = last_exec.status if last_exec else None

        if job.is_paused:
            status_text = f"[bold dim]{self.msg.status_paused}[/]"
        elif last_status == ExecutionStatus.FAILED:
            status_text = f"[bold red]{self.msg.status_error}[/]"
        elif job.schedule.frequency == ScheduleFrequency.ONCE:
            if self.storage.has_terminal_execution(job.id):
                status_text = f"[bold green]{self.msg.status_done}[/]"
            else:
                status_text = f"[bold yellow]{self.msg.status_waiting}[/]"
        elif ran_today:
            status_text = f"[bold green]{self.msg.status_running_today}[/]"
        else:
            status_text = f"[bold yellow]{self.msg.status_waiting}[/]"

        # Format schedule and tolerance
        if job.schedule.frequency == ScheduleFrequency.ONCE:
            time_display = job.schedule.run_at.strftime("%Y-%m-%d %H:%M") if job.schedule.run_at is not None else "-"
            if job.schedule.tolerance_mode.value == "exact":
                tol_str = self.msg.tol_exact_desc
            elif job.schedule.tolerance_mode.value == "until_hour":
                tol_str = self.msg.tol_until_hour_desc.format(hour=f"{job.schedule.tolerance_value:02d}:00")
            else:
                tol_str = self.msg.tol_hours_window_desc.format(hours=job.schedule.tolerance_value)
        elif job.schedule.frequency == ScheduleFrequency.INTERVAL_HOURS:
            time_display = self.msg.lbl_every_hours_title.format(val=job.schedule.interval_value)
            if job.schedule.start_time or job.schedule.end_time:
                w_start = job.schedule.start_time.strftime("%H:%M") if job.schedule.start_time else "00:00"
                w_end = job.schedule.end_time.strftime("%H:%M") if job.schedule.end_time else "23:59"
                time_display += f" ({w_start} – {w_end})"
            tol_str = self.msg.lbl_not_applicable_interval
        elif job.schedule.frequency == ScheduleFrequency.INTERVAL_MINUTES:
            time_display = self.msg.lbl_every_minutes_title.format(val=job.schedule.interval_value)
            if job.schedule.start_time or job.schedule.end_time:
                w_start = job.schedule.start_time.strftime("%H:%M") if job.schedule.start_time else "00:00"
                w_end = job.schedule.end_time.strftime("%H:%M") if job.schedule.end_time else "23:59"
                time_display += f" ({w_start} – {w_end})"
            tol_str = self.msg.lbl_not_applicable_interval
        else:
            if len(job.schedule.times_of_day) > 1:
                time_display = ", ".join(t.strftime("%H:%M") for t in job.schedule.times_of_day)
            else:
                time_display = job.schedule.time_of_day.strftime("%H:%M")
            if job.schedule.tolerance_mode.value == "exact":
                tol_str = self.msg.tol_exact_desc
            elif job.schedule.tolerance_mode.value == "until_hour":
                tol_str = self.msg.tol_until_hour_desc.format(hour=f"{job.schedule.tolerance_value:02d}:00")
            else:
                tol_str = self.msg.tol_hours_window_desc.format(hours=job.schedule.tolerance_value)

        # Format semantic days
        if job.schedule.frequency == ScheduleFrequency.ONCE:
            days_semantic = self.msg.lbl_onetime_type
        else:
            days = sorted(job.schedule.days_of_week)
            if len(days) == 5 and days == [0, 1, 2, 3, 4]:
                days_semantic = self.msg.days_weekdays_full
            elif len(days) == 7:
                days_semantic = self.msg.days_everyday_full
            elif len(days) == 2 and days == [5, 6]:
                days_semantic = self.msg.days_weekend_full
            else:
                abbrs = self.msg.days_names_abbr
                days_semantic = ", ".join(abbrs[d] if 0 <= d < len(abbrs) else str(d) for d in days)

        # Format target
        if isinstance(job.target, TerminalTargetConfig):
            target_str = f"{self.msg.target_opt_terminal} (App: {job.target.app.value})"
        elif isinstance(job.target, HerdrTargetConfig):
            target_str = f"{self.msg.target_opt_herdr} (Space: '{job.target.space}', Tab: '{job.target.tab_template}')"
        else:
            target_str = f"{self.msg.target_opt_background} ({self.msg.target_opt_headless})"

        folder_info = f"[dim]{self.msg.lbl_prop_folder}:[/]    [bold]{job.folder}[/]\n" if job.folder else ""

        primary_color = (
            self.app.current_theme.primary
            if hasattr(self.app, "current_theme") and self.app.current_theme
            else "#ffffff"
        )

        if isinstance(job.action, AgentAction):
            info = HARNESS_INFO.get(job.action.harness)
            harness_name = info.display_name if info else job.action.harness.value
            harness_color = info.color if info else "#ffffff"
            harness_cli = info.cli if info else job.action.harness.value
            harness_badge = f"[bold {harness_color}]{harness_name}[/] [dim]({harness_cli})[/]"
            prompt_preview = "\n".join(f"  [italic]{line}[/]" for line in job.action.prompt.splitlines())
            action_markup = f"""[dim]{self.msg.lbl_prop_mode}:[/]      [bold]{self.msg.lbl_action_agent}[/]
[dim]{self.msg.lbl_prop_harness}:[/]   {harness_badge}
[dim]{self.msg.lbl_prop_prompt}:[/]
{prompt_preview}"""
        else:
            action_markup = f"""[dim]{self.msg.lbl_prop_mode}:[/]      [bold]{self.msg.lbl_action_command}[/]
[dim]{self.msg.lbl_prop_command}:[/]   [bold green]{job.command}[/]"""

        details_markup = f"""
[bold size=14]{job.name}[/]  {status_text}
[dim]ID: {job.id} • {self.msg.inspector_created}: {job.created_at.strftime("%Y-%m-%d")} • {self.msg.inspector_total_runs}: [bold]{total_runs}[/][/]
{folder_info}
[bold {primary_color}]{self.msg.inspector_target}[/]
[bold]{target_str}[/]

[bold {primary_color}]{self.msg.inspector_schedule}[/]
[dim]{self.msg.lbl_prop_time}:[/]      [bold]{time_display}[/]
[dim]{self.msg.lbl_prop_days}:[/]      [bold]{days_semantic}[/]
[dim]{self.msg.lbl_prop_policy}:[/]    [bold]{tol_str}[/]

[bold {primary_color}]{self.msg.inspector_execution}[/]
[dim]{self.msg.lbl_prop_cwd}:[/]       [bold]{job.cwd}[/]
{action_markup}

[bold {primary_color}]{self.msg.inspector_history}[/]
"""
        self.query_one("#inspector-details", Static).update(details_markup)

        history_container = self.query_one("#inspector-history", Vertical)
        history_container.remove_children()

        if recent_records:
            for rec in recent_records:
                match = re.search(r"\b(tb[a-f0-9]{20,})\b", rec.details)
                herdr_tab_id = match.group(1) if match else None

                cleaned = re.sub(r"\btb[a-f0-9]{20,}\b\s*", "", rec.details)
                cleaned = re.sub(r"in tab\s+\('", "in ('", cleaned)

                history_container.mount(ExecutionRow(rec, cleaned, herdr_tab_id, job, self.msg))
        else:
            history_container.mount(Label(f"[dim]{self.msg.empty_history_text}[/]"))
