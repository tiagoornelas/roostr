from datetime import time
from pathlib import Path

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, TextArea

from roostr.domain.enums import (
    ActionType,
    AIHarness,
    ScheduleFrequency,
    TerminalApp,
    ToleranceMode,
)
from roostr.domain.models import (
    AgentAction,
    BackgroundTargetConfig,
    CommandAction,
    HerdrTargetConfig,
    Job,
    JobAction,
    SchedulePolicy,
    TargetConfig,
    TerminalTargetConfig,
    slugify,
)
from roostr.i18n.schema import Messages


class PromptTextArea(TextArea):
    """Multiline prompt TextArea supporting line breaks via Enter, Shift+Enter, Ctrl+Enter, and Alt+Enter."""

    async def _on_key(self, event: events.Key) -> None:
        key = event.key
        if key in (
            "enter",
            "shift+enter",
            "ctrl+enter",
            "alt+enter",
            "shift+return",
            "ctrl+return",
            "alt+return",
            "return",
            "ctrl+j",
            "ctrl+m",
        ) or event.character in ("\n", "\r"):
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)
            return

        await super()._on_key(event)


class JobFormModal(ModalScreen[Job | None]):
    DEFAULT_CSS = """
    JobFormModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }

    #form-container {
        width: 92%;
        max-width: 138;
        min-width: 86;
        max-height: 94%;
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
        width: 100%;
    }

    #form-scroll {
        height: auto;
        max-height: 84%;
    }

    #form-columns {
        height: auto;
        width: 100%;
    }

    .form-column {
        width: 1fr;
        height: auto;
    }

    #form-col-left {
        border-right: solid $panel;
        padding-right: 2;
    }

    #form-col-right {
        padding-left: 2;
    }

    .section-title {
        text-style: bold;
        color: $primary;
        margin-top: 0;
        margin-bottom: 0;
        padding-bottom: 0;
    }

    .field-label {
        color: $secondary;
        margin-top: 1;
        margin-bottom: 0;
        height: 1;
    }

    .field-hint {
        color: $secondary;
        opacity: 0.75;
        margin-top: 0;
        margin-bottom: 0;
        height: auto;
    }

    Input, Select {
        background: $panel;
        border: solid $panel;
        color: $foreground;
        height: 3;
        margin-top: 0;
        margin-bottom: 0;
    }

    Input:focus, Select:focus {
        border: solid $primary;
    }

    .days-row {
        height: auto;
        layout: horizontal;
        margin-top: 0;
        margin-bottom: 0;
    }

    .day-checkbox {
        width: auto;
        margin-right: 1;
        background: transparent;
        border: none;
        height: 1;
    }

    .freq-box {
        height: auto;
        margin-top: 0;
    }

    .tol-box {
        height: auto;
        margin-top: 0;
    }

    .target-box {
        height: auto;
        margin-top: 1;
        padding: 0 1;
        border: solid $panel;
        background: $background;
    }

    .action-box {
        height: auto;
        margin-top: 0;
        padding: 0;
    }

    #inp-prompt {
        height: 14;
        background: $panel;
        border: solid $panel;
        color: $foreground;
        margin-top: 0;
    }

    #inp-prompt:focus {
        border: solid $primary;
    }

    .button-row {
        margin-top: 1;
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
        height: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        self.on_save()

    def __init__(self, job: Job | None = None, messages: Messages | None = None):
        super().__init__()
        self.job = job
        from roostr.i18n.catalog import get_messages

        self.msg = messages or get_messages("en")

    def compose(self) -> ComposeResult:
        with Vertical(id="form-container"):
            title = self.msg.modal_title_edit if self.job else self.msg.modal_title_new
            yield Label(title, classes="form-title")

            with VerticalScroll(id="form-scroll"):
                with Horizontal(id="form-columns"):
                    # LEFT COLUMN: General settings, Target & Schedule
                    with Vertical(id="form-col-left", classes="form-column"):
                        yield Label(self.msg.inspector_schedule, classes="section-title")

                        yield Label(self.msg.lbl_job_name, classes="field-label")
                        yield Input(
                            placeholder="e.g. Daily PR Review",
                            id="inp-name",
                            value=self.job.name if self.job else "",
                        )

                        yield Label(self.msg.lbl_cwd, classes="field-label")
                        yield Input(
                            placeholder="/path/to/project",
                            id="inp-cwd",
                            value=self.job.cwd if self.job else str(Path.home()),
                        )

                        yield Label(self.msg.lbl_target_type, classes="field-label")
                        target_options = [
                            (self.msg.target_opt_terminal, "terminal"),
                            (self.msg.target_opt_herdr, "herdr"),
                            (self.msg.target_opt_background, "background"),
                        ]
                        initial_target = "terminal"
                        if self.job:
                            if isinstance(self.job.target, HerdrTargetConfig):
                                initial_target = "herdr"
                            elif isinstance(self.job.target, BackgroundTargetConfig):
                                initial_target = "background"
                        yield Select(target_options, value=initial_target, id="sel-target-type")

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
                                self.job.target.space
                                if isinstance(self.job and self.job.target, HerdrTargetConfig)
                                else ""
                            )
                            yield Input(
                                placeholder="e.g. Roostr or Personal",
                                id="inp-herdr-space",
                                value=herdr_space,
                            )
                            yield Label(self.msg.lbl_herdr_space_hint, classes="field-hint")

                            yield Label(self.msg.lbl_tab_template, classes="field-label")
                            herdr_tab = (
                                self.job.target.tab_template
                                if isinstance(self.job and self.job.target, HerdrTargetConfig)
                                else "{job.name} {DD}/{MM}"
                            )
                            yield Input(placeholder="Daily {DD}/{MM}", id="inp-herdr-tab", value=herdr_tab)
                            yield Label(self.msg.lbl_tab_template_hint, classes="field-hint")

                        with Vertical(id="target-background-box", classes="target-box"):
                            yield Label(self.msg.lbl_bg_log, classes="field-label")
                            bg_log = (
                                self.job.target.log_file
                                if isinstance(self.job and self.job.target, BackgroundTargetConfig)
                                and self.job.target.log_file
                                else ""
                            )
                            yield Input(placeholder="~/.local/state/roostr/logs/...", id="inp-bg-log", value=bg_log)

                        # FREQUENCY & SCHEDULE
                        yield Label(self.msg.lbl_frequency, classes="field-label")
                        freq_options = [
                            (self.msg.freq_opt_daily, "daily"),
                            (self.msg.freq_opt_interval_hours, "interval_hours"),
                            (self.msg.freq_opt_interval_minutes, "interval_minutes"),
                        ]
                        initial_freq = self.job.schedule.frequency.value if self.job else "daily"
                        yield Select(freq_options, value=initial_freq, id="sel-frequency")

                        with Vertical(id="freq-daily-box", classes="freq-box"):
                            yield Label(self.msg.lbl_time, classes="field-label")
                            initial_time = self.job.schedule.time_of_day.strftime("%H:%M") if self.job else "08:00"
                            yield Input(placeholder="08:00", id="inp-time", value=initial_time)

                            yield Label(self.msg.lbl_tolerance_section_title, classes="field-label")
                            yield Label(self.msg.lbl_tolerance_explanation, classes="field-hint")
                            tol_options = [
                                (self.msg.tol_opt_until_hour, "until_hour"),
                                (self.msg.tol_opt_hours_window, "window_hours"),
                                (self.msg.tol_opt_exact, "exact"),
                            ]
                            initial_tol = self.job.schedule.tolerance_mode.value if self.job else "until_hour"
                            yield Select(tol_options, value=initial_tol, id="sel-tolerance-mode")

                            with Vertical(id="tol-until-hour-box", classes="tol-box"):
                                yield Label(self.msg.lbl_tol_until_hour_input, classes="field-label")
                                initial_until_val = (
                                    f"{self.job.schedule.tolerance_value:02d}:00"
                                    if (self.job and self.job.schedule.tolerance_mode == ToleranceMode.UNTIL_HOUR)
                                    else "12:00"
                                )
                                yield Input(placeholder="12:00", id="inp-tol-until-hour", value=initial_until_val)

                            with Vertical(id="tol-hours-window-box", classes="tol-box"):
                                yield Label(self.msg.lbl_tol_window_hours_input, classes="field-label")
                                initial_window_val = (
                                    str(self.job.schedule.tolerance_value)
                                    if (self.job and self.job.schedule.tolerance_mode == ToleranceMode.WINDOW_HOURS)
                                    else "3"
                                )
                                yield Input(placeholder="3", id="inp-tol-window-hours", value=initial_window_val)

                        with Vertical(id="freq-hours-box", classes="freq-box"):
                            yield Label(self.msg.lbl_interval_hours, classes="field-label")
                            initial_hours_val = (
                                str(self.job.schedule.interval_value)
                                if (self.job and self.job.schedule.frequency == ScheduleFrequency.INTERVAL_HOURS)
                                else "2"
                            )
                            yield Input(placeholder="2", id="inp-interval-hours", value=initial_hours_val)
                            yield Label(self.msg.lbl_interval_hours_hint, classes="field-hint")

                        with Vertical(id="freq-minutes-box", classes="freq-box"):
                            yield Label(self.msg.lbl_interval_minutes, classes="field-label")
                            initial_minutes_val = (
                                str(self.job.schedule.interval_value)
                                if (self.job and self.job.schedule.frequency == ScheduleFrequency.INTERVAL_MINUTES)
                                else "30"
                            )
                            yield Input(placeholder="30", id="inp-interval-minutes", value=initial_minutes_val)
                            yield Label(self.msg.lbl_interval_minutes_hint, classes="field-hint")

                        # ACTIVE DAYS CHECKBOXES
                        yield Label(self.msg.lbl_days, classes="field-label")
                        active_days_set = set(self.job.schedule.days_of_week) if self.job else {0, 1, 2, 3, 4}
                        with Horizontal(id="days-checkbox-row", classes="days-row"):
                            for day_idx in range(7):
                                abbr = (
                                    self.msg.days_names_abbr[day_idx]
                                    if day_idx < len(self.msg.days_names_abbr)
                                    else str(day_idx)
                                )
                                yield Checkbox(
                                    abbr,
                                    value=(day_idx in active_days_set),
                                    id=f"chk-day-{day_idx}",
                                    classes="day-checkbox",
                                )

                    # RIGHT COLUMN: Execution Action & Prompt
                    with Vertical(id="form-col-right", classes="form-column"):
                        yield Label(self.msg.inspector_action, classes="section-title")

                        yield Label(self.msg.lbl_action_type, classes="field-label")
                        action_options = [
                            (self.msg.lbl_action_agent, "agent"),
                            (self.msg.lbl_action_command, "command"),
                        ]
                        initial_action_type = "agent"
                        if self.job and self.job.action.action_type == ActionType.COMMAND:
                            initial_action_type = "command"
                        yield Select(action_options, value=initial_action_type, id="sel-action-type")

                        with Vertical(id="action-agent-box", classes="action-box"):
                            yield Label(self.msg.lbl_harness, classes="field-label")
                            harness_options = [
                                ("Claude Code (claude)", "claude"),
                                ("Antigravity (agy)", "antigravity"),
                                ("Cursor (cursor)", "cursor"),
                                ("Codex (codex)", "codex"),
                            ]
                            initial_harness = "claude"
                            initial_prompt = ""
                            if self.job and isinstance(self.job.action, AgentAction):
                                initial_harness = self.job.action.harness.value
                                initial_prompt = self.job.action.prompt
                            yield Select(harness_options, value=initial_harness, id="sel-harness")

                            yield Label(self.msg.lbl_prompt, classes="field-label")
                            yield PromptTextArea(
                                text=initial_prompt,
                                id="inp-prompt",
                                language="markdown",
                            )
                            yield Label(self.msg.lbl_prompt_hint, classes="field-hint")

                        with Vertical(id="action-command-box", classes="action-box"):
                            yield Label(self.msg.lbl_command, classes="field-label")
                            initial_cmd = (
                                self.job.action.command
                                if self.job and isinstance(self.job.action, CommandAction)
                                else (self.job.command if self.job else "")
                            )
                            yield Input(
                                placeholder=self.msg.lbl_command_placeholder,
                                id="inp-command",
                                value=initial_cmd,
                            )

            yield Label("", id="error-label")

            with Horizontal(classes="button-row"):
                yield Button(self.msg.btn_cancel, variant="default", id="btn-cancel")
                yield Button(self.msg.btn_save, variant="primary", id="btn-save")

    def on_mount(self) -> None:
        initial_target = "terminal"
        if self.job:
            if isinstance(self.job.target, HerdrTargetConfig):
                initial_target = "herdr"
            elif isinstance(self.job.target, BackgroundTargetConfig):
                initial_target = "background"
        self._update_target_visibility(initial_target)

        initial_action = "agent"
        if self.job and self.job.action.action_type == ActionType.COMMAND:
            initial_action = "command"
        self._update_action_visibility(initial_action)

        initial_freq = self.job.schedule.frequency.value if self.job else "daily"
        self._update_frequency_visibility(initial_freq)

        initial_tol = self.job.schedule.tolerance_mode.value if self.job else "until_hour"
        self._update_tolerance_visibility(initial_tol)

    @on(Select.Changed, "#sel-target-type")
    def on_target_type_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or not event.value:
            return
        t_val = str(event.value)
        self._update_target_visibility(t_val)
        if t_val == "herdr":
            try:
                self.query_one("#inp-herdr-space", Input).focus()
            except Exception:
                pass

    def _update_target_visibility(self, target_type: str) -> None:
        self.query_one("#target-terminal-box").display = target_type == "terminal"
        self.query_one("#target-herdr-box").display = target_type == "herdr"
        self.query_one("#target-background-box").display = target_type == "background"

    @on(Select.Changed, "#sel-frequency")
    def on_frequency_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or not event.value:
            return
        self._update_frequency_visibility(str(event.value))

    def _update_frequency_visibility(self, freq: str) -> None:
        self.query_one("#freq-daily-box").display = freq == "daily"
        self.query_one("#freq-hours-box").display = freq == "interval_hours"
        self.query_one("#freq-minutes-box").display = freq == "interval_minutes"

    @on(Select.Changed, "#sel-tolerance-mode")
    def on_tolerance_mode_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or not event.value:
            return
        self._update_tolerance_visibility(str(event.value))

    def _update_tolerance_visibility(self, tol_mode: str) -> None:
        self.query_one("#tol-until-hour-box").display = tol_mode == "until_hour"
        self.query_one("#tol-hours-window-box").display = tol_mode == "window_hours"

    @on(Select.Changed, "#sel-action-type")
    def on_action_type_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or not event.value:
            return
        self._update_action_visibility(str(event.value))

    def _update_action_visibility(self, action_type: str) -> None:
        is_agent = action_type == "agent"
        self.query_one("#action-agent-box").display = is_agent
        self.query_one("#action-command-box").display = not is_agent

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-save")
    def on_save(self) -> None:
        job_name = self.query_one("#inp-name", Input).value.strip()
        cwd = self.query_one("#inp-cwd", Input).value.strip()
        target_type = self.query_one("#sel-target-type", Select).value

        error_label = self.query_one("#error-label", Label)

        if not job_name:
            error_label.update(self.msg.err_required_fields)
            return

        job_id = self.job.id if self.job else slugify(job_name)

        action_type_val = self.query_one("#sel-action-type", Select).value
        action: JobAction
        if action_type_val == "agent":
            harness_val = str(self.query_one("#sel-harness", Select).value)
            prompt_val = self.query_one("#inp-prompt", TextArea).text.strip()
            if not prompt_val:
                error_label.update(self.msg.err_empty_prompt)
                return
            action = AgentAction(harness=AIHarness(harness_val), prompt=prompt_val)
        else:
            command_val = self.query_one("#inp-command", Input).value.strip()
            if not command_val:
                error_label.update(self.msg.err_empty_command)
                return
            action = CommandAction(command=command_val)

        # Active Days from Checkboxes
        selected_days = tuple(d for d in range(7) if self.query_one(f"#chk-day-{d}", Checkbox).value)
        if not selected_days:
            error_label.update(self.msg.err_no_days_selected)
            return

        # Frequency & Schedule
        freq_val = str(self.query_one("#sel-frequency", Select).value)
        frequency = ScheduleFrequency(freq_val)

        tod = time(8, 0)
        tol_mode = ToleranceMode.EXACT
        tol_val = 0
        interval_val = 1

        if frequency == ScheduleFrequency.DAILY:
            time_str = self.query_one("#inp-time", Input).value.strip()
            try:
                parts = time_str.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                tod = time(hour, minute)
            except Exception:
                error_label.update(self.msg.err_invalid_time)
                return

            tol_mode_val = str(self.query_one("#sel-tolerance-mode", Select).value)
            tol_mode = ToleranceMode(tol_mode_val)
            if tol_mode == ToleranceMode.UNTIL_HOUR:
                until_str = self.query_one("#inp-tol-until-hour", Input).value.strip()
                try:
                    tol_val = int(until_str.split(":")[0])
                except Exception:
                    tol_val = 12
            elif tol_mode == ToleranceMode.WINDOW_HOURS:
                win_str = self.query_one("#inp-tol-window-hours", Input).value.strip()
                try:
                    tol_val = int(win_str)
                except Exception:
                    tol_val = 3
        elif frequency == ScheduleFrequency.INTERVAL_HOURS:
            h_str = self.query_one("#inp-interval-hours", Input).value.strip()
            try:
                interval_val = max(1, int(h_str))
            except Exception:
                error_label.update(self.msg.err_invalid_interval)
                return
        elif frequency == ScheduleFrequency.INTERVAL_MINUTES:
            m_str = self.query_one("#inp-interval-minutes", Input).value.strip()
            try:
                interval_val = max(1, int(m_str))
            except Exception:
                error_label.update(self.msg.err_invalid_interval)
                return

        schedule = SchedulePolicy(
            days_of_week=selected_days,
            time_of_day=tod,
            tolerance_mode=tol_mode,
            tolerance_value=tol_val,
            frequency=frequency,
            interval_value=interval_val,
        )

        target: TargetConfig
        if target_type == "terminal":
            app_val = self.query_one("#sel-terminal-app", Select).value
            target = TerminalTargetConfig(app=TerminalApp(app_val), keep_open=True)
        elif target_type == "herdr":
            space = self.query_one("#inp-herdr-space", Input).value.strip() or "Roostr"
            tab_template = self.query_one("#inp-herdr-tab", Input).value.strip() or "{job.name} {DD}/{MM}"
            target = HerdrTargetConfig(space=space, tab_template=tab_template)
        else:
            log_file = self.query_one("#inp-bg-log", Input).value.strip() or None
            target = BackgroundTargetConfig(log_file=log_file, notify_on_complete=True)

        folder_val = self.job.folder if self.job else None

        job = Job(
            id=job_id,
            name=job_name,
            cwd=cwd,
            schedule=schedule,
            target=target,
            action=action,
            is_paused=self.job.is_paused if self.job else False,
            folder=folder_val,
        )

        self.dismiss(job)
