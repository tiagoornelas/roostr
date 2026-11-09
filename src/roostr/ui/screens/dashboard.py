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
            badge = f"[dim]{self.msg.status_paused}[/]"
        elif self.ran_today:
            badge = f"[bold green]{self.msg.status_running_today}[/]"
        else:
            badge = f"[bold yellow]{self.msg.status_waiting}[/]"

        sched_str = self.job.schedule.time_of_day.strftime("%H:%M")
        if len(self.job.schedule.days_of_week) == 5 and self.job.schedule.days_of_week == (0, 1, 2, 3, 4):
            days_str = "Mon–Fri" if self.msg.locale == "en" else "Seg–Sex"
        elif len(self.job.schedule.days_of_week) == 7:
            days_str = "Daily" if self.msg.locale == "en" else "Diário"
        else:
            days_str = f"{len(self.job.schedule.days_of_week)}d"

        target_icon = "💻"
        if isinstance(self.job.target, HerdrTargetConfig):
            target_icon = "🐑"
        elif isinstance(self.job.target, BackgroundTargetConfig):
            target_icon = "⚙️"

        with Vertical(classes="job-card-inner"):
            with Horizontal(classes="job-card-top"):
                yield Label(f"[bold]{target_icon} {self.job.name}[/]", classes="job-card-name")
                yield Label(badge, classes="job-card-badge")
            with Horizontal(classes="job-card-sub"):
                yield Label(
                    f"[dim]{days_str} {sched_str}[/] • [cyan]{self.run_count}[/] runs", classes="job-card-details"
                )


class DashboardScreen(Screen):
    DEFAULT_CSS = """
    DashboardScreen {
        layout: horizontal;
        background: #0f141c;
    }

    #sidebar {
        width: 42%;
        height: 100%;
        border-right: solid #2d3748;
        background: #0d121a;
    }

    #sidebar-header {
        background: #1b222d;
        color: #8b949e;
        padding: 0 1;
        height: 2;
        content-align: left middle;
        border-bottom: solid #2d3748;
        text-style: bold;
    }

    #jobs-list {
        height: 1fr;
        background: #0d121a;
        padding: 0;
    }

    JobListItem {
        padding: 1 1;
        border-bottom: solid #1e2937;
        background: #0d121a;
    }

    JobListItem:hover {
        background: #161f2c;
    }

    JobListItem.-selected {
        background: #1e2838;
        border-left: solid #58a6ff;
    }

    .job-card-top {
        height: 1;
        align: left middle;
    }

    .job-card-name {
        width: 1fr;
        color: #f0f6fc;
    }

    .job-card-badge {
        width: auto;
    }

    .job-card-sub {
        height: 1;
        margin-top: 0;
    }

    .job-card-details {
        color: #8b949e;
    }

    #inspector {
        width: 58%;
        height: 100%;
        padding: 1 2;
        background: #0f141c;
    }

    #inspector-header {
        height: 4;
        border-bottom: solid #2d3748;
        margin-bottom: 1;
    }

    .inspector-title {
        text-style: bold;
        color: #ffffff;
    }

    .inspector-meta {
        color: #8b949e;
    }

    .info-card {
        background: #141b24;
        border: solid #2d3748;
        padding: 1 1;
        margin-bottom: 1;
    }

    .info-card-title {
        color: #58a6ff;
        text-style: bold;
        margin-bottom: 0;
    }

    .prop-row {
        height: 1;
    }

    .prop-name {
        width: 16;
        color: #8b949e;
    }

    .prop-val {
        color: #f0f6fc;
    }

    #history-title {
        color: #58a6ff;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    """

    def __init__(self, storage: JobRepositoryPort, messages: Messages):
        super().__init__()
        self.storage = storage
        self.msg = messages
        self.selected_job: Job | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label(self.msg.sidebar_header, id="sidebar-header")
                yield ListView(id="jobs-list")

            with VerticalScroll(id="inspector"):
                yield Static(id="inspector-content")

        yield Footer()

    def on_mount(self) -> None:
        self.refresh_jobs()

    def update_messages(self, messages: Messages) -> None:
        self.msg = messages
        self.query_one("#sidebar-header", Label).update(self.msg.sidebar_header)
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

        # Format target
        if isinstance(job.target, TerminalTargetConfig):
            target_str = f"Terminal Window (App: {job.target.app.value})"
        elif isinstance(job.target, HerdrTargetConfig):
            target_str = f"Herdr App (Space: '{job.target.space}', Tab: '{job.target.tab_template}')"
        else:
            target_str = "Background Process (Headless)"

        sentinel_info = job.sentinel_pattern or "[dim]None (standard database idempotency)[/]"

        # Execution history
        history_lines = []
        if recent_records:
            for rec in recent_records:
                ts = rec.timestamp.strftime("%d/%m %H:%M:%S")
                color = "green" if rec.status == ExecutionStatus.SUCCESS else "yellow"
                if rec.status == ExecutionStatus.FAILED:
                    color = "red"
                history_lines.append(
                    f"[dim]{ts}[/] [{color}]{rec.status.value}[/] ([dim]{rec.trigger_type.value}[/]): {rec.details}"
                )
        else:
            history_lines.append("[dim]No executions recorded yet.[/]")

        history_rendered = "\n".join(history_lines)

        content = f"""
[bold white size=14]{job.name}[/]  {status_text}
[dim]ID: {job.id} • Created: {job.created_at.strftime("%Y-%m-%d")} • Total runs: [cyan]{total_runs}[/][/]

[bold #58a6ff]{self.msg.inspector_target}[/]
[white]{target_str}[/]

[bold #58a6ff]{self.msg.inspector_schedule}[/]
[dim]Time:[/]      [white]{job.schedule.time_of_day.strftime("%H:%M")}[/]
[dim]Days:[/]      [white]{job.schedule.days_of_week}[/]
[dim]Policy:[/]    [white]{tol_str}[/]

[bold #58a6ff]{self.msg.inspector_execution}[/]
[dim]CWD:[/]       [white]{job.cwd}[/]
[dim]Command:[/]   [bold green]{job.command}[/]
[dim]Sentinel:[/]  [white]{sentinel_info}[/]

[bold #58a6ff]{self.msg.inspector_history}[/]
{history_rendered}
"""
        self.query_one("#inspector-content", Static).update(content)
