from datetime import date

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from roostr.application.ports import JobRepositoryPort
from roostr.domain.enums import ExecutionStatus
from roostr.domain.models import (
    BackgroundTargetConfig,
    HerdrTargetConfig,
    Job,
    TerminalTargetConfig,
)
from roostr.i18n.schema import Messages


class JobListItem(ListItem):
    def __init__(self, job: Job, ran_today: bool, run_count: int, msg: Messages):
        super().__init__()
        self.job = job
        self.ran_today = ran_today
        self.run_count = run_count
        self.msg = msg

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

    #jobs-list > JobListItem {
        height: auto;
        padding: 0 1;
        margin: 1 1 0 1;
        background: transparent;
        border: round $panel;
        color: $foreground;
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

    #inspector-content {
        background: $background;
        color: $foreground;
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

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-content"):
            with Vertical(id="sidebar"):
                yield ListView(id="jobs-list")

            with VerticalScroll(id="inspector"):
                yield Static(id="inspector-content")

        with Horizontal(id="bottom-bar"):
            yield Label("🐓 roostr", id="footer-brand")
            yield Footer()

    def on_mount(self) -> None:
        self.refresh_jobs()

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
        target_index = 0

        today = date.today()
        for idx, job in enumerate(jobs):
            ran_today = self.storage.has_succeeded_on_date(job.id, today)
            run_count = self.storage.count_executions(job.id)
            item = JobListItem(job, ran_today, run_count, self.msg)
            jobs_list.append(item)
            if selected_job_id and job.id == selected_job_id:
                target_index = idx

        if jobs:
            jobs_list.index = target_index
            self.show_job_details(jobs[target_index])
        else:
            self.selected_job = None
            inspector_content = self.query_one("#inspector-content", Static)
            inspector_content.update(f"[dim]{self.msg.empty_state_text}[/]")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, JobListItem):
            self.show_job_details(event.item.job)

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
        is_en = self.msg.locale == "en"
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

        sentinel_info = job.sentinel_pattern or "[dim]None (standard database idempotency)[/]"

        # Execution history & session detection
        import re

        self.latest_session_command = None
        history_lines = []
        if recent_records:
            for rec in recent_records:
                ts = rec.timestamp.strftime("%d/%m %H:%M:%S")
                color = "green" if rec.status == ExecutionStatus.SUCCESS else "yellow"
                if rec.status == ExecutionStatus.FAILED:
                    color = "red"

                # Detect session ID for quick jump
                if not self.latest_session_command:
                    match = re.search(r"\b(tb[a-f0-9]{20,})\b", rec.details)
                    if match:
                        self.latest_session_command = f"hc attach {match.group(1)}"

                # Clean raw hash from details for human-readable display
                cleaned = re.sub(r"\btb[a-f0-9]{20,}\b\s*", "", rec.details)
                cleaned = re.sub(r"in tab\s+\('", "in ('", cleaned)
                history_lines.append(
                    f"[dim]{ts}[/] [{color}]{rec.status.value}[/] ([dim]{rec.trigger_type.value}[/]): {cleaned}"
                )
        else:
            history_lines.append("[dim]No executions recorded yet.[/]")

        history_rendered = "\n".join(history_lines)

        primary_color = (
            self.app.current_theme.primary
            if hasattr(self.app, "current_theme") and self.app.current_theme
            else "#ffffff"
        )

        content = f"""
[bold size=14]{job.name}[/]  {status_text}
[dim]ID: {job.id} • Created: {job.created_at.strftime("%Y-%m-%d")} • Total runs: [bold]{total_runs}[/][/]

[bold {primary_color}]{self.msg.inspector_target}[/]
[bold]{target_str}[/]

[bold {primary_color}]{self.msg.inspector_schedule}[/]
[dim]Time:[/]      [bold]{job.schedule.time_of_day.strftime("%H:%M")}[/]
[dim]Days:[/]      [bold]{days_semantic}[/]
[dim]Policy:[/]    [bold]{tol_str}[/]

[bold {primary_color}]{self.msg.inspector_execution}[/]
[dim]CWD:[/]       [bold]{job.cwd}[/]
[dim]Command:[/]   [bold green]{job.command}[/]
[dim]Sentinel:[/]  [bold]{sentinel_info}[/]

[bold {primary_color}]{self.msg.inspector_history}[/]
{history_rendered}
"""
        self.query_one("#inspector-content", Static).update(content)
