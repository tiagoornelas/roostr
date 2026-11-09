import re
import subprocess
from datetime import date

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from roostr.application.ports import JobRepositoryPort
from roostr.domain.enums import ExecutionStatus
from roostr.domain.models import (
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

        sched_str = self.job.schedule.time_of_day.strftime("%H:%M")
        if len(self.job.schedule.days_of_week) == 5 and self.job.schedule.days_of_week == (0, 1, 2, 3, 4):
            days_str = "Mon–Fri" if self.msg.locale == "en" else "Seg–Sex"
        elif len(self.job.schedule.days_of_week) == 7:
            days_str = "Daily" if self.msg.locale == "en" else "Diário"
        else:
            days_str = f"{len(self.job.schedule.days_of_week)}d"

        target_name = "Herdr"
        if isinstance(self.job.target, HerdrTargetConfig):
            target_name = f"Herdr ({self.job.target.space})" if self.job.target.space else "Herdr"
        elif isinstance(self.job.target, BackgroundTargetConfig):
            target_name = "Background"
        elif isinstance(self.job.target, TerminalTargetConfig):
            target_name = "Terminal"

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
        attach_cmd: str | None,
        msg: Messages,
    ):
        super().__init__()
        self.record = record
        self.cleaned_details = cleaned_details
        self.attach_cmd = attach_cmd
        self.msg = msg

    def on_mount(self) -> None:
        ts = self.record.timestamp.strftime("%d/%m %H:%M:%S")
        color = "green" if self.record.status == ExecutionStatus.SUCCESS else "yellow"
        if self.record.status == ExecutionStatus.FAILED:
            color = "red"

        copy_hint = "  [dim cyan](click to copy session)[/]" if self.attach_cmd else ""
        self.update(
            f"[dim]{ts}[/] [{color}]{self.record.status.value}[/] ([dim]{self.record.trigger_type.value}[/]): {self.cleaned_details}{copy_hint}"
        )

    def on_click(self, event: events.Click) -> None:
        to_copy = self.attach_cmd or self.record.details
        try:
            subprocess.run(["pbcopy"], input=to_copy.encode("utf-8"), check=True)
        except Exception:
            pass
        try:
            self.app.copy_to_clipboard(to_copy)
        except Exception:
            pass

        if self.attach_cmd:
            self.app.notify(f"Copied: {self.attach_cmd}", title="Attach Command")
        else:
            self.app.notify("Copied log details to clipboard", title="Log")


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
        folder_type = "Subfolder" if is_subfolder else "Folder"
        details_markup = f"""
[bold size=14]{folder_name.upper()}[/]  [dim]({folder_type})[/]
[dim]Active Jobs:[/]  [bold]{count}[/]

[bold {primary_color}]FOLDER ACTIONS[/]
[dim]• Press [bold white]m[/] on any job to move it into this folder.[/]
[dim]• Press [bold white]f[/] to create a new folder or subfolder.[/]
[dim]• Press [bold white]d[/] to delete this folder (if empty).[/]
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

        # Format tolerance
        if job.schedule.tolerance_mode.value == "exact":
            tol_str = "Exact time" if self.msg.locale == "en" else "Horário exato"
        elif job.schedule.tolerance_mode.value == "until_hour":
            tol_str = (
                f"Until {job.schedule.tolerance_value:02d}:00"
                if self.msg.locale == "en"
                else f"Até às {job.schedule.tolerance_value:02d}:00"
            )
        else:
            tol_str = (
                f"{job.schedule.tolerance_value}h window"
                if self.msg.locale == "en"
                else f"Janela de {job.schedule.tolerance_value}h"
            )

        # Format semantic days
        days_names_en = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        days_names_pt = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
        days_names_es = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}

        if self.msg.locale == "pt_br":
            days_map = days_names_pt
            weekdays_lbl = "Dias úteis (Segunda a Sexta)"
            everyday_lbl = "Todos os dias"
            weekend_lbl = "Fim de semana (Sábado e Domingo)"
        elif self.msg.locale == "es":
            days_map = days_names_es
            weekdays_lbl = "Días laborables (Lunes a Viernes)"
            everyday_lbl = "Todos los días"
            weekend_lbl = "Fin de semana (Sábado y Domingo)"
        else:
            days_map = days_names_en
            weekdays_lbl = "Weekdays (Monday to Friday)"
            everyday_lbl = "Every day"
            weekend_lbl = "Weekends (Saturday and Sunday)"

        days = sorted(job.schedule.days_of_week)
        if len(days) == 5 and days == [0, 1, 2, 3, 4]:
            days_semantic = weekdays_lbl
        elif len(days) == 7:
            days_semantic = everyday_lbl
        elif len(days) == 2 and days == [5, 6]:
            days_semantic = weekend_lbl
        else:
            days_semantic = ", ".join(days_map.get(d, str(d)) for d in days)

        # Format target
        if isinstance(job.target, TerminalTargetConfig):
            target_str = f"Terminal Window (App: {job.target.app.value})"
        elif isinstance(job.target, HerdrTargetConfig):
            target_str = f"Herdr App (Space: '{job.target.space}', Tab: '{job.target.tab_template}')"
        else:
            target_str = "Background Process (Headless)"

        folder_info = f"[dim]Folder:[/]    [bold]{job.folder}[/]\n" if job.folder else ""

        primary_color = (
            self.app.current_theme.primary
            if hasattr(self.app, "current_theme") and self.app.current_theme
            else "#ffffff"
        )

        details_markup = f"""
[bold size=14]{job.name}[/]  {status_text}
[dim]ID: {job.id} • Created: {job.created_at.strftime("%Y-%m-%d")} • Total runs: [bold]{total_runs}[/][/]
{folder_info}
[bold {primary_color}]{self.msg.inspector_target}[/]
[bold]{target_str}[/]

[bold {primary_color}]{self.msg.inspector_schedule}[/]
[dim]Time:[/]      [bold]{job.schedule.time_of_day.strftime("%H:%M")}[/]
[dim]Days:[/]      [bold]{days_semantic}[/]
[dim]Policy:[/]    [bold]{tol_str}[/]

[bold {primary_color}]{self.msg.inspector_execution}[/]
[dim]CWD:[/]       [bold]{job.cwd}[/]
[dim]Command:[/]   [bold green]{job.command}[/]

[bold {primary_color}]{self.msg.inspector_history}[/]
"""
        self.query_one("#inspector-details", Static).update(details_markup)

        history_container = self.query_one("#inspector-history", Vertical)
        history_container.remove_children()

        if recent_records:
            for rec in recent_records:
                match = re.search(r"\b(tb[a-f0-9]{20,})\b", rec.details)
                attach_cmd = f"hc attach {match.group(1)}" if match else None

                cleaned = re.sub(r"\btb[a-f0-9]{20,}\b\s*", "", rec.details)
                cleaned = re.sub(r"in tab\s+\('", "in ('", cleaned)

                history_container.mount(ExecutionRow(rec, cleaned, attach_cmd, self.msg))
        else:
            history_container.mount(Label("[dim]No executions recorded yet.[/]"))
