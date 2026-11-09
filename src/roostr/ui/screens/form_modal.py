from datetime import time
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

from roostr.domain.enums import TerminalApp, ToleranceMode
from roostr.domain.models import (
    BackgroundTargetConfig,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TargetConfig,
    TerminalTargetConfig,
)
from roostr.i18n.schema import Messages


class JobFormModal(ModalScreen[Job | None]):
    DEFAULT_CSS = """
    JobFormModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #form-container {
        width: 86;
        max-height: 92%;
        background: $background;
        border: solid $primary;
        padding: 1 2;
        color: $foreground;
    }

    .form-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        text-align: center;
    }

    .field-label {
        color: $secondary;
        margin-top: 1;
    }

    Input {
        background: $panel;
        border: solid $panel;
        color: $foreground;
    }

    Input:focus {
        border: solid $primary;
    }

    Select {
        background: $panel;
        border: solid $panel;
        color: $foreground;
    }

    .button-row {
        margin-top: 2;
        align: right middle;
        height: 3;
    }

    Button {
        background: $panel;
        color: $foreground;
        border: none;
        min-width: 14;
        margin-left: 2;
    }

    Button:hover {
        background: $panel;
    }

    Button.-primary {
        background: $primary;
        color: $background;
        text-style: bold;
    }

    #error-label {
        color: $error;
        text-style: bold;
        margin-top: 1;
    }

    .target-box {
        margin-top: 1;
        padding: 1;
        border: solid $panel;
        background: $background;
    }
    """

    def __init__(self, job: Job | None = None, messages: Messages | None = None):
        super().__init__()
        self.job = job
        from roostr.i18n.catalog import get_messages

        self.msg = messages or get_messages("en")

    def compose(self) -> ComposeResult:
        with Vertical(id="form-container"):
            title = self.msg.modal_title_edit if self.job else self.msg.modal_title_new
            yield Label(title, classes="form-title")

            with VerticalScroll():
                yield Label(self.msg.lbl_job_id, classes="field-label")
                yield Input(
                    placeholder="e.g. daily-sync",
                    id="inp-id",
                    value=self.job.id if self.job else "",
                    disabled=bool(self.job),
                )

                yield Label(self.msg.lbl_job_name, classes="field-label")
                yield Input(
                    placeholder="e.g. Daily Synchronization",
                    id="inp-name",
                    value=self.job.name if self.job else "",
                )

                yield Label(self.msg.lbl_cwd, classes="field-label")
                yield Input(
                    placeholder="/path/to/project",
                    id="inp-cwd",
                    value=self.job.cwd if self.job else str(Path.home()),
                )

                yield Label(self.msg.lbl_command, classes="field-label")
                yield Input(
                    placeholder="claude '/sync' or agy 'run'",
                    id="inp-command",
                    value=self.job.command if self.job else "",
                )

                yield Label(self.msg.lbl_target_type, classes="field-label")
                target_options = [
                    ("Terminal Window", "terminal"),
                    ("Herdr App Space/Tab", "herdr"),
                    ("Background Process (Daemon)", "background"),
                ]
                initial_target = "terminal"
                if self.job:
                    if isinstance(self.job.target, HerdrTargetConfig):
                        initial_target = "herdr"
                    elif isinstance(self.job.target, BackgroundTargetConfig):
                        initial_target = "background"

                yield Select(target_options, value=initial_target, id="sel-target-type")

                # Dynamic target settings containers
                with Vertical(id="target-terminal-box", classes="target-box"):
                    yield Label(self.msg.lbl_terminal_app, classes="field-label")
                    term_apps = [
                        ("Auto-detect", "auto"),
                        ("Terminal.app", "terminal"),
                        ("Ghostty", "ghostty"),
                        ("iTerm2", "iterm2"),
                        ("Kitty", "kitty"),
                    ]
                    yield Select(term_apps, value="auto", id="sel-terminal-app")

                with Vertical(id="target-herdr-box", classes="target-box"):
                    yield Label(self.msg.lbl_herdr_space, classes="field-label")
                    herdr_space = (
                        self.job.target.space if isinstance(self.job and self.job.target, HerdrTargetConfig) else ""
                    )
                    yield Input(placeholder="e.g. Roostr or Personal", id="inp-herdr-space", value=herdr_space)

                    yield Label(self.msg.lbl_tab_template, classes="field-label")
                    herdr_tab = (
                        self.job.target.tab_template
                        if isinstance(self.job and self.job.target, HerdrTargetConfig)
                        else "Daily {DD}/{MM}"
                    )
                    yield Input(placeholder="Daily {DD}/{MM}", id="inp-herdr-tab", value=herdr_tab)

                with Vertical(id="target-background-box", classes="target-box"):
                    yield Label("Log file path (optional):", classes="field-label")
                    bg_log = (
                        self.job.target.log_file
                        if isinstance(self.job and self.job.target, BackgroundTargetConfig) and self.job.target.log_file
                        else ""
                    )
                    yield Input(placeholder="~/.local/state/roostr/logs/...", id="inp-bg-log", value=bg_log)

                # Schedule settings
                yield Label(self.msg.lbl_days, classes="field-label")
                day_options = [
                    ("Monday to Friday (Mon–Fri)", "weekdays"),
                    ("Every Day (Mon–Sun)", "everyday"),
                    ("Custom (1,2,3,4,5)", "custom"),
                ]
                yield Select(day_options, value="weekdays", id="sel-days")

                yield Label(self.msg.lbl_time, classes="field-label")
                initial_time = self.job.schedule.time_of_day.strftime("%H:%M") if self.job else "08:00"
                yield Input(placeholder="08:00", id="inp-time", value=initial_time)

                yield Label(self.msg.lbl_tolerance_mode, classes="field-label")
                tol_options = [
                    ("Until specific hour (e.g. 12:00)", "until_hour"),
                    ("Hours window after schedule", "hours_window"),
                    ("Exact time only (strict)", "exact"),
                ]
                yield Select(tol_options, value="until_hour", id="sel-tolerance-mode")

                yield Label(self.msg.lbl_tolerance_val, classes="field-label")
                initial_tol_val = str(self.job.schedule.tolerance_value) if self.job else "12"
                yield Input(placeholder="12", id="inp-tolerance-val", value=initial_tol_val)

                yield Label(self.msg.lbl_sentinel, classes="field-label")
                initial_sentinel = self.job.sentinel_pattern if self.job and self.job.sentinel_pattern else ""
                yield Input(
                    placeholder="reports/{YYYY}/{MM}/{YYYY-MM-DD}-report.md",
                    id="inp-sentinel",
                    value=initial_sentinel,
                )

                yield Label("", id="error-label")

            with Horizontal(classes="button-row"):
                yield Button(self.msg.btn_cancel, variant="default", id="btn-cancel")
                yield Button(self.msg.btn_save, variant="primary", id="btn-save")

    def on_mount(self) -> None:
        self._update_target_visibility("terminal")

    @on(Select.Changed, "#sel-target-type")
    def on_target_type_changed(self, event: Select.Changed) -> None:
        self._update_target_visibility(str(event.value))

    def _update_target_visibility(self, target_type: str) -> None:
        self.query_one("#target-terminal-box").display = target_type == "terminal"
        self.query_one("#target-herdr-box").display = target_type == "herdr"
        self.query_one("#target-background-box").display = target_type == "background"

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-save")
    def on_save(self) -> None:
        job_id = self.query_one("#inp-id", Input).value.strip()
        job_name = self.query_one("#inp-name", Input).value.strip()
        cwd = self.query_one("#inp-cwd", Input).value.strip()
        command = self.query_one("#inp-command", Input).value.strip()
        time_str = self.query_one("#inp-time", Input).value.strip()
        target_type = self.query_one("#sel-target-type", Select).value

        error_label = self.query_one("#error-label", Label)

        if not job_id or not job_name or not command:
            error_label.update("Job ID, Name, and Command are required.")
            return

        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            tod = time(hour, minute)
        except Exception:
            error_label.update("Invalid time format. Please use HH:MM.")
            return

        days_val = self.query_one("#sel-days", Select).value
        if days_val == "weekdays":
            days = (0, 1, 2, 3, 4)
        elif days_val == "everyday":
            days = (0, 1, 2, 3, 4, 5, 6)
        else:
            days = (0, 1, 2, 3, 4)

        tol_mode_val = self.query_one("#sel-tolerance-mode", Select).value
        tol_mode = ToleranceMode(tol_mode_val)

        tol_val_str = self.query_one("#inp-tolerance-val", Input).value.strip()
        try:
            tol_val = int(tol_val_str) if tol_val_str else 0
        except ValueError:
            tol_val = 0

        target: TargetConfig
        if target_type == "terminal":
            app_val = self.query_one("#sel-terminal-app", Select).value
            target = TerminalTargetConfig(app=TerminalApp(app_val), keep_open=True)
        elif target_type == "herdr":
            space = self.query_one("#inp-herdr-space", Input).value.strip() or "Roostr"
            tab_template = self.query_one("#inp-herdr-tab", Input).value.strip() or "Daily {DD}/{MM}"
            target = HerdrTargetConfig(space=space, tab_template=tab_template)
        else:
            log_file = self.query_one("#inp-bg-log", Input).value.strip() or None
            target = BackgroundTargetConfig(log_file=log_file, notify_on_complete=True)

        sentinel = self.query_one("#inp-sentinel", Input).value.strip() or None
        folder_val = self.job.folder if self.job else None

        job = Job(
            id=job_id,
            name=job_name,
            cwd=cwd,
            command=command,
            schedule=SchedulePolicy(
                days_of_week=days,
                time_of_day=tod,
                tolerance_mode=tol_mode,
                tolerance_value=tol_val,
            ),
            target=target,
            sentinel_pattern=sentinel,
            is_paused=self.job.is_paused if self.job else False,
            folder=folder_val,
        )

        self.dismiss(job)
