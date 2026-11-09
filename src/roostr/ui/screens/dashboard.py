import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from roostr.application.ports import JobRepositoryPort
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
    def __init__(self, job: Job, ran_today: bool, run_count: int, msg: Messages, indent: int = 0):
        super().__init__()
        self.job = job
        self.ran_today = ran_today
        self.run_count = run_count
        self.msg = msg
        self.indent = indent
        if indent == 1:
            self.add_class("indent-1")
        elif indent >= 2:
            self.add_class("indent-2")

    def compose(self) -> ComposeResult:
        if self.job.is_paused:
            status_dot = "[dim]●[/]"
            badge_markup = f"[dim]{self.msg.status_paused}[/]"
            name_markup = f"[dim]{self.job.name}[/]"
        elif self.ran_today:
            status_dot = "[bold green]●[/]"
            badge_markup = f"[bold green]{self.msg.status_running_today}[/]"
            name_markup = f"[bold]{self.job.name}[/]"
        else:
            status_dot = "[bold yellow]●[/]"
            badge_markup = f"[bold yellow]{self.msg.status_waiting}[/]"
            name_markup = f"[bold]{self.job.name}[/]"

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
        with Horizontal(classes="job-card-sub"):
            yield Label(
                f"[dim]{days_str} {sched_str} • {target_name}[/]",
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

    #jobs-list > FolderHeaderItem {
        height: 1;
        padding: 0 1;
        margin: 0 1;
        background: $panel;
        color: $foreground;
        border: none;
    }

    #jobs-list > FolderHeaderItem:hover {
        background: $primary 20%;
    }

    #jobs-list > FolderHeaderItem.-highlight {
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

    #bottom-bar Footer {
        width: 1fr;
        dock: none;
        background: transparent;
    }
    """

    def __init__(self, storage: JobRepositoryPort, messages: Messages, theme_name: str = "night"):
        super().__init__()
        self.storage = storage
        self.msg = messages
        self.active_theme = theme_name
        self.selected_job: Job | None = None
        self.collapsed_folders: set[str] = set()
        self.collapsed_subfolders: set[str] = set()

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-content"):
            with Vertical(id="sidebar"):
                yield ListView(id="jobs-list")

            with VerticalScroll(id="inspector"):
                yield Static(id="inspector-details")
                yield Vertical(id="inspector-history")

        with Horizontal(id="bottom-bar"):
            yield Label("🐓 roostr", id="footer-brand")
            yield Footer()

    def on_mount(self) -> None:
        self.refresh_jobs()

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

        jobs = self.storage.list_jobs()
        today = date.today()

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

        items_to_add: list[ListItem] = []
        job_index_map: dict[str, int] = {}

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
                    item = JobListItem(job, ran_today, run_count, self.msg, indent=1)
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
                            item = JobListItem(job, ran_today, run_count, self.msg, indent=2)
                            job_index_map[job.id] = len(items_to_add)
                            items_to_add.append(item)

        # 2. Ungrouped / root jobs come LAST ("os sem pasta ficam por ultimo")
        if root_jobs:
            if folder_tree:
                items_to_add.append(UngroupedHeaderItem(self.msg.lbl_ungrouped))
            for job in root_jobs:
                ran_today = self.storage.has_succeeded_on_date(job.id, today)
                run_count = self.storage.count_executions(job.id)
                item = JobListItem(job, ran_today, run_count, self.msg, indent=0)
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
        elif isinstance(event.item, JobListItem):
            self.show_job_details(event.item.job)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, JobListItem):
            self.show_job_details(event.item.job)
        elif event.item and isinstance(event.item, FolderHeaderItem):
            self.show_folder_details(event.item.folder_name, event.item.count, is_subfolder=False)
        elif event.item and isinstance(event.item, SubfolderHeaderItem):
            self.show_folder_details(event.item.subfolder_key, event.item.count, is_subfolder=True)

    def show_folder_details(self, folder_name: str, count: int, is_subfolder: bool = False) -> None:
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

        if job.is_paused:
            status_text = f"[bold dim]{self.msg.status_paused}[/]"
        elif ran_today:
            status_text = f"[bold green]{self.msg.status_running_today}[/]"
        else:
            status_text = f"[bold yellow]{self.msg.status_waiting}[/]"

        # Format schedule and tolerance
        if job.schedule.frequency == ScheduleFrequency.INTERVAL_HOURS:
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
