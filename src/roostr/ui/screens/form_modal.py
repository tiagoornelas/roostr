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
        background: #161b22;
        border: solid #58a6ff;
        padding: 1 2;
    }

    .form-title {
        text-style: bold;
        color: #58a6ff;
        margin-bottom: 1;
        text-align: center;
    }

    .field-label {
        color: #8b949e;
        margin-top: 1;
    }

    Input {
        background: #0d1117;
        border: solid #30363d;
        color: #c9d1d9;
    }

    Input:focus {
        border: solid #58a6ff;
    }

    Select {
        background: #0d1117;
        border: solid #30363d;
        color: #c9d1d9;
    }

    .button-row {
        margin-top: 2;
        align: right middle;
        height: 3;
    }

    .button-row Button {
        margin-left: 2;
    }

    #error-label {
        color: #f85149;
        margin-top: 1;
        text-align: center;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "submit", "Save"),
    ]

    def __init__(self, messages: Messages, existing_job: Job | None = None):
        super().__init__()
        self.msg = messages
        self.existing_job = existing_job

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="form-container"):
            title = self.msg.modal_title_edit if self.existing_job else self.msg.modal_title_new
            yield Label(title, classes="form-title")

            yield Label(self.msg.lbl_job_id, classes="field-label")
            initial_id = self.existing_job.id if self.existing_job else ""
            yield Input(
                placeholder="e.g. daily-report", value=initial_id, id="input-id", disabled=bool(self.existing_job)
            )

            yield Label(self.msg.lbl_job_name, classes="field-label")
            initial_name = self.existing_job.name if self.existing_job else ""
            yield Input(placeholder="e.g. Daily Standup Report", value=initial_name, id="input-name")

            yield Label(self.msg.lbl_cwd, classes="field-label")
            initial_cwd = self.existing_job.cwd if self.existing_job else str(Path.home())
            yield Input(placeholder=f"e.g. {Path.home()}/Documents/dev/my-project", value=initial_cwd, id="input-cwd")

            yield Label(self.msg.lbl_command, classes="field-label")
            initial_cmd = self.existing_job.command if self.existing_job else "claude '/daily-report'"
            yield Input(placeholder="e.g. claude '/review' or agy 'check prs'", value=initial_cmd, id="input-command")

            yield Label(self.msg.lbl_target_type, classes="field-label")
            current_target_type = self.existing_job.target.target_type.value if self.existing_job else "terminal"
            target_options = [
                ("Terminal (Default for macOS)", "terminal"),
                ("Herdr App (Spaces & Tabs)", "herdr"),
                ("Background (Headless log)", "background"),
            ]
            yield Select(options=target_options, value=current_target_type, id="select-target-type", allow_blank=False)

            # Terminal fields container
            with Vertical(id="target-fields-terminal"):
                yield Label(self.msg.lbl_terminal_app, classes="field-label")
                terminal_app_options = [
                    ("System Default (Terminal.app)", "auto"),
                    ("Ghostty", "ghostty"),
                    ("iTerm2", "iterm2"),
                    ("Kitty", "kitty"),
                ]
                initial_app = (
                    self.existing_job.target.app.value
                    if (self.existing_job and isinstance(self.existing_job.target, TerminalTargetConfig))
                    else "auto"
                )
                yield Select(
                    options=terminal_app_options, value=initial_app, id="select-terminal-app", allow_blank=False
                )

            # Herdr fields container
            with Vertical(id="target-fields-herdr", classes="hidden"):
                yield Label(self.msg.lbl_herdr_space, classes="field-label")
                initial_space = (
                    self.existing_job.target.space
                    if (self.existing_job and isinstance(self.existing_job.target, HerdrTargetConfig))
                    else "Roostr"
                )
                yield Input(
                    placeholder="e.g. Roostr or Personal Coordinator", value=initial_space, id="input-herdr-space"
                )

                yield Label(self.msg.lbl_tab_template, classes="field-label")
                initial_tab = (
                    self.existing_job.target.tab_template
                    if (self.existing_job and isinstance(self.existing_job.target, HerdrTargetConfig))
                    else "{job.name} {DD}/{MM}"
                )
                yield Input(placeholder="e.g. Daily {DD}/{MM}", value=initial_tab, id="input-tab-template")

            yield Label(self.msg.lbl_days, classes="field-label")
            if self.existing_job:
                initial_days = ",".join(str(d) for d in self.existing_job.schedule.days_of_week)
            else:
                initial_days = "0,1,2,3,4"
            yield Input(placeholder="e.g. weekdays, all, or 0,1,2,3,4", value=initial_days, id="input-days")

            yield Label(self.msg.lbl_time, classes="field-label")
            initial_time = self.existing_job.schedule.time_of_day.strftime("%H:%M") if self.existing_job else "08:00"
            yield Input(placeholder="e.g. 08:00", value=initial_time, id="input-time")

            yield Label(self.msg.lbl_tolerance_mode, classes="field-label")
            tolerance_options = [
                ("Until hour limit (e.g. until 12:00)", "until_hour"),
                ("Exact time (strict)", "exact"),
                ("Window in hours (e.g. 4h)", "window_hours"),
            ]
            current_mode = self.existing_job.schedule.tolerance_mode.value if self.existing_job else "until_hour"
            yield Select(options=tolerance_options, value=current_mode, id="select-tolerance-mode", allow_blank=False)

            yield Label(self.msg.lbl_tolerance_val, classes="field-label")
            initial_tol_val = str(self.existing_job.schedule.tolerance_value) if self.existing_job else "12"
            yield Input(placeholder="e.g. 12", value=initial_tol_val, id="input-tolerance-val")

            yield Label(self.msg.lbl_sentinel, classes="field-label")
            initial_sentinel = (
                self.existing_job.sentinel_pattern if (self.existing_job and self.existing_job.sentinel_pattern) else ""
            )
            yield Input(
                placeholder="e.g. reports/{YYYY}/{MM}/{YYYY-MM-DD}-daily.md",
                value=initial_sentinel,
                id="input-sentinel",
            )

            yield Label("", id="error-label")

            with Horizontal(classes="button-row"):
                yield Button(self.msg.btn_cancel, variant="default", id="btn-cancel")
                yield Button(self.msg.btn_save, variant="primary", id="btn-submit")

    @on(Select.Changed, "#select-target-type")
    def on_target_type_changed(self, event: Select.Changed) -> None:
        target_val = event.value
        terminal_box = self.query_one("#target-fields-terminal", Vertical)
        herdr_box = self.query_one("#target-fields-herdr", Vertical)

        if target_val == "terminal":
            terminal_box.remove_class("hidden")
            herdr_box.add_class("hidden")
        elif target_val == "herdr":
            terminal_box.add_class("hidden")
            herdr_box.remove_class("hidden")
        else:
            terminal_box.add_class("hidden")
            herdr_box.add_class("hidden")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
        elif event.button.id == "btn-submit":
            self.action_submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        job_id = self.query_one("#input-id", Input).value.strip()
        name = self.query_one("#input-name", Input).value.strip()
        cwd = self.query_one("#input-cwd", Input).value.strip()
        command = self.query_one("#input-command", Input).value.strip()
        target_type_val = self.query_one("#select-target-type", Select).value

        days_str = self.query_one("#input-days", Input).value.strip().lower()
        time_str = self.query_one("#input-time", Input).value.strip()
        tolerance_mode_val = self.query_one("#select-tolerance-mode", Select).value
        tolerance_val_str = self.query_one("#input-tolerance-val", Input).value.strip()
        sentinel = self.query_one("#input-sentinel", Input).value.strip() or None

        error_label = self.query_one("#error-label", Label)

        if not job_id or not name or not cwd or not command:
            error_label.update("Please fill all required fields (ID, Name, CWD, Command).")
            return

        try:
            h, m = map(int, time_str.split(":"))
            time_of_day = time(h, m)
        except Exception:
            error_label.update("Invalid time format. Use HH:MM (e.g. 08:00).")
            return

        if days_str in ("weekdays", "seg-sex", "seg_sex"):
            days = (0, 1, 2, 3, 4)
        elif days_str in ("all", "daily", "diario", "todos"):
            days = (0, 1, 2, 3, 4, 5, 6)
        else:
            try:
                days = tuple(int(x.strip()) for x in days_str.split(","))
            except Exception:
                error_label.update("Invalid days. Use numbers separated by commas (e.g. 0,1,2,3,4).")
                return

        try:
            tol_val = int(tolerance_val_str) if tolerance_val_str else 0
        except Exception:
            error_label.update("Tolerance limit must be an integer number.")
            return

        policy = SchedulePolicy(
            days_of_week=days,
            time_of_day=time_of_day,
            tolerance_mode=ToleranceMode(tolerance_mode_val),
            tolerance_value=tol_val,
        )

        target_cfg: TargetConfig
        if target_type_val == "terminal":
            app_val = self.query_one("#select-terminal-app", Select).value
            target_cfg = TerminalTargetConfig(app=TerminalApp(app_val), keep_open=True)
        elif target_type_val == "herdr":
            space_val = self.query_one("#input-herdr-space", Input).value.strip()
            tab_val = self.query_one("#input-tab-template", Input).value.strip() or "{job.name} {DD}/{MM}"
            if not space_val:
                error_label.update("Herdr Space Name is required when Herdr App target is selected.")
                return
            target_cfg = HerdrTargetConfig(space=space_val, tab_template=tab_val)
        else:
            target_cfg = BackgroundTargetConfig(notify_on_complete=True)

        job = Job(
            id=job_id,
            name=name,
            cwd=cwd,
            command=command,
            schedule=policy,
            target=target_cfg,
            sentinel_pattern=sentinel,
            is_paused=self.existing_job.is_paused if self.existing_job else False,
        )
        self.dismiss(job)
