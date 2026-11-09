from textual import work
from textual.app import App
from textual.binding import Binding

from roostr.application.ports import JobRepositoryPort
from roostr.application.use_cases.execute_job import ExecuteJobUseCase
from roostr.application.use_cases.manage_jobs import ManageJobsUseCase
from roostr.domain.enums import ExecutionStatus
from roostr.domain.models import Job
from roostr.i18n.catalog import SUPPORTED_LOCALES, get_messages
from roostr.infrastructure.targets.herdr import register_herdr_program
from roostr.ui.screens.dashboard import DashboardScreen
from roostr.ui.screens.form_modal import JobFormModal
from roostr.ui.screens.settings_modal import SettingsModal
from roostr.ui.themes import DEFAULT_THEME, ROOSTR_THEMES, THEME_NAMES


class RoostrApp(App):
    TITLE = "🐓 roostr"
    SUB_TITLE = "Wake up your local AI coding agents on schedule"

    ENABLE_COMMAND_PALETTE = True
    COMMAND_PALETTE_BINDING = "ctrl+k"
    COMMAND_PALETTE_DISPLAY = "^k"

    BINDINGS = [
        Binding("n", "new_job", "New Job", show=True),
        Binding("r", "run_now", "Run Now", show=True),
        Binding("o", "open_session", "Open Session", show=True),
        Binding("p", "toggle_pause", "Pause/Resume", show=True),
        Binding("d", "delete_job", "Delete", show=True),
        Binding("s", "open_settings", "Settings", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+k", "command_palette", "Actions", key_display="^k", show=False),
        Binding("t", "switch_theme", "Theme", show=False),
        Binding("l", "switch_language", "Language", show=False),
    ]

    def __init__(
        self,
        storage: JobRepositoryPort,
        locale: str = "en",
        theme: str = DEFAULT_THEME,
        execute_use_case: ExecuteJobUseCase | None = None,
        manage_use_case: ManageJobsUseCase | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.storage = storage
        self.locale = locale
        self.msg = get_messages(self.locale)

        # Register custom curated themes
        for custom_theme in ROOSTR_THEMES:
            self.register_theme(custom_theme)

        selected_theme = theme if theme in THEME_NAMES else DEFAULT_THEME
        self.theme = selected_theme

        # Register Roostr program in Herdr if Herdr is present
        try:
            register_herdr_program()
        except Exception:
            pass

        self.execute_use_case = execute_use_case or ExecuteJobUseCase(storage=storage)
        self.manage_use_case = manage_use_case or ManageJobsUseCase(storage=storage)
        self.dashboard_screen = DashboardScreen(
            storage=self.storage,
            messages=self.msg,
            theme_name=self.theme,
        )

    def get_default_screen(self) -> DashboardScreen:
        return self.dashboard_screen

    def action_new_job(self) -> None:
        def on_modal_result(job: Job | None) -> None:
            if job:
                try:
                    self.manage_use_case.create_job(job)
                    created_msg = self.msg.notify_success_created.replace("{name}", job.name)
                    self.notify(created_msg, title="Success", severity="information")
                    self.dashboard_screen.refresh_jobs(selected_job_id=job.id)
                except Exception as e:
                    self.notify(f"Error saving job: {e}", title="Error", severity="error")

        self.push_screen(JobFormModal(messages=self.msg), on_modal_result)

    def action_run_now(self) -> None:
        if not self.dashboard_screen.selected_job:
            self.notify(self.msg.notify_no_selection, severity="warning")
            return

        job = self.dashboard_screen.selected_job
        self._dispatch_run_now_async(job)

    def action_open_session(self) -> None:
        if not self.dashboard_screen.selected_job:
            self.notify(self.msg.notify_no_selection, severity="warning")
            return

        cmd = getattr(self.dashboard_screen, "latest_session_command", None)
        if cmd:
            import subprocess

            try:
                subprocess.run(["pbcopy"], input=cmd.encode("utf-8"), check=True)
                self.notify(f"Copied: {cmd}", title="Open Session")
            except Exception:
                self.notify(f"Run: {cmd}", title="Open Session")
        else:
            self.notify(
                "No recent interactive terminal session found for this job.",
                title="Open Session",
                severity="information",
            )

    @work(thread=True)
    def _dispatch_run_now_async(self, job: Job) -> None:
        self.notify(self.msg.notify_running.replace("{name}", job.name), title="Executing")
        status, msg = self.execute_use_case.execute(job.id, force=True)
        if status == ExecutionStatus.SUCCESS:
            self.notify(f"Success: {msg}", title="Completed", severity="information")
        else:
            self.notify(f"{status.value}: {msg}", title="Result", severity="warning")
        self.call_from_thread(self.dashboard_screen.refresh_jobs, job.id)

    def action_toggle_pause(self) -> None:
        if not self.dashboard_screen.selected_job:
            return

        job = self.dashboard_screen.selected_job
        new_state = self.manage_use_case.toggle_pause(job.id)
        if new_state:
            notice = self.msg.notify_paused.replace("{name}", job.name)
        else:
            notice = self.msg.notify_resumed.replace("{name}", job.name)
        self.notify(notice, title="Schedule")
        self.dashboard_screen.refresh_jobs(selected_job_id=job.id)

    def action_delete_job(self) -> None:
        if not self.dashboard_screen.selected_job:
            return

        job = self.dashboard_screen.selected_job
        self.manage_use_case.delete_job(job.id)
        deleted_msg = self.msg.notify_success_deleted.replace("{name}", job.name)
        self.notify(deleted_msg, title="Deleted", severity="information")
        self.dashboard_screen.refresh_jobs()

    def action_open_settings(self) -> None:
        def on_settings_result(result: dict | None) -> None:
            if not result:
                return
            new_theme = result.get("theme")
            new_locale = result.get("locale")

            if new_theme and new_theme != self.theme:
                self.theme = new_theme
                self.dashboard_screen.update_theme(new_theme)
                self.notify(f"Theme: {new_theme}", title="Settings")

            if new_locale and new_locale != self.locale:
                self.locale = new_locale
                self.msg = get_messages(self.locale)
                self.dashboard_screen.update_messages(self.msg)
                self.notify(f"Language: {self.locale.upper()}", title="Settings")

        self.push_screen(
            SettingsModal(
                current_theme=self.theme,
                current_locale=self.locale,
                messages=self.msg,
            ),
            on_settings_result,
        )

    def action_switch_theme(self) -> None:
        current_idx = THEME_NAMES.index(self.theme) if self.theme in THEME_NAMES else 0
        next_theme = THEME_NAMES[(current_idx + 1) % len(THEME_NAMES)]
        self.theme = next_theme
        self.dashboard_screen.update_theme(next_theme)
        self.notify(f"Theme changed to {next_theme}", title="Theme")

    def action_switch_language(self) -> None:
        current_idx = SUPPORTED_LOCALES.index(self.locale) if self.locale in SUPPORTED_LOCALES else 0
        next_locale = SUPPORTED_LOCALES[(current_idx + 1) % len(SUPPORTED_LOCALES)]
        self.locale = next_locale
        self.msg = get_messages(self.locale)
        self.dashboard_screen.update_messages(self.msg)
        self.notify(f"Language changed to {self.locale.upper()}", title="i18n")
