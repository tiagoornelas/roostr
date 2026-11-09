import dataclasses

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
from roostr.ui.screens.dashboard import (
    DashboardScreen,
    FolderHeaderItem,
    SubfolderHeaderItem,
)
from roostr.ui.screens.folder_modal import NewFolderModal
from roostr.ui.screens.form_modal import JobFormModal
from roostr.ui.screens.move_modal import MoveJobModal
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
        Binding("m", "move_job", "Move to Folder", show=True),
        Binding("f", "new_folder", "New Folder", show=True),
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

        # Persist theme and locale
        if hasattr(self.storage, "set_setting"):
            self.storage.set_setting("locale", self.locale)
            self.storage.set_setting("theme", self.theme)

        self._update_bindings_language()

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
                    self.notify(created_msg, title=self.msg.title_success, severity="information")
                    self.dashboard_screen.refresh_jobs(selected_job_id=job.id)
                except Exception as e:
                    self.notify(
                        self.msg.msg_error_saving_job.format(error=e), title=self.msg.title_error, severity="error"
                    )

        self.push_screen(JobFormModal(messages=self.msg), on_modal_result)

    def action_move_job(self) -> None:
        if not self.dashboard_screen.selected_job:
            self.notify(self.msg.notify_no_selection, severity="warning")
            return

        job = self.dashboard_screen.selected_job
        folders = self.manage_use_case.list_folders()

        def on_move_result(target_folder: str | None) -> None:
            if target_folder is not None:
                dest = target_folder if target_folder else None
                try:
                    self.manage_use_case.move_job(job.id, dest)
                    dest_display = dest if dest else self.msg.lbl_no_folder_root
                    self.notify(
                        self.msg.notify_moved.format(name=job.name, dest=dest_display), title=self.msg.title_moved
                    )
                    self.dashboard_screen.refresh_jobs(selected_job_id=job.id)
                except Exception as e:
                    self.notify(
                        self.msg.msg_error_moving_job.format(error=e), title=self.msg.title_error, severity="error"
                    )

        self.push_screen(MoveJobModal(job, folders, self.msg), on_move_result)

    def action_new_folder(self) -> None:
        prefill = ""
        focused = self.dashboard_screen.get_current_focused_item()
        if isinstance(focused, FolderHeaderItem):
            prefill = f"{focused.folder_name}/"

        def on_folder_result(folder_name: str | None) -> None:
            if folder_name:
                try:
                    self.manage_use_case.create_folder(folder_name)
                    self.notify(self.msg.notify_folder_created.format(name=folder_name), title=self.msg.title_success)
                    self.dashboard_screen.refresh_jobs()
                except Exception as e:
                    self.notify(
                        self.msg.msg_error_creating_folder.format(error=e), title=self.msg.title_error, severity="error"
                    )

        self.push_screen(NewFolderModal(self.msg, prefill=prefill), on_folder_result)

    def action_run_now(self) -> None:
        if not self.dashboard_screen.selected_job:
            self.notify(self.msg.notify_no_selection, severity="warning")
            return

        job = self.dashboard_screen.selected_job
        self._dispatch_run_now_async(job)

    @work(thread=True)
    def _dispatch_run_now_async(self, job: Job) -> None:
        self.notify(self.msg.notify_running.replace("{name}", job.name), title=self.msg.title_executing)
        status, msg = self.execute_use_case.execute(job.id, force=True)
        if status == ExecutionStatus.SUCCESS:
            self.notify(f"{self.msg.title_success}: {msg}", title=self.msg.title_completed, severity="information")
        else:
            self.notify(f"{status.value}: {msg}", title=self.msg.title_schedule, severity="warning")
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
        self.notify(notice, title=self.msg.title_schedule)
        self.dashboard_screen.refresh_jobs(selected_job_id=job.id)

    def action_delete_job(self) -> None:
        focused = self.dashboard_screen.get_current_focused_item()
        if isinstance(focused, FolderHeaderItem):
            fn = focused.folder_name
            try:
                self.manage_use_case.delete_folder(fn)
                self.notify(
                    self.msg.notify_folder_deleted.format(name=fn), title=self.msg.title_deleted, severity="information"
                )
                self.dashboard_screen.refresh_jobs()
            except ValueError as e:
                self.notify(str(e), title=self.msg.title_cannot_delete, severity="warning")
            return
        elif isinstance(focused, SubfolderHeaderItem):
            sk = focused.subfolder_key
            try:
                self.manage_use_case.delete_folder(sk)
                self.notify(
                    self.msg.notify_folder_deleted.format(name=sk), title=self.msg.title_deleted, severity="information"
                )
                self.dashboard_screen.refresh_jobs()
            except ValueError as e:
                self.notify(str(e), title=self.msg.title_cannot_delete, severity="warning")
            return

        if not self.dashboard_screen.selected_job:
            return

        job = self.dashboard_screen.selected_job
        self.manage_use_case.delete_job(job.id)
        deleted_msg = self.msg.notify_success_deleted.replace("{name}", job.name)
        self.notify(deleted_msg, title=self.msg.title_deleted, severity="information")
        self.dashboard_screen.refresh_jobs()

    def _update_bindings_language(self) -> None:
        key_descriptions = {
            "n": self.msg.key_new_job,
            "r": self.msg.key_run_now,
            "m": self.msg.key_move_job,
            "f": self.msg.key_new_folder,
            "p": self.msg.key_toggle_pause,
            "d": self.msg.key_delete_job,
            "s": self.msg.key_settings,
            "q": self.msg.key_quit,
        }
        if hasattr(self, "_bindings") and hasattr(self._bindings, "key_to_bindings"):
            for key, desc in key_descriptions.items():
                if key in self._bindings.key_to_bindings:
                    bindings_list = self._bindings.key_to_bindings[key]
                    for i, b in enumerate(bindings_list):
                        bindings_list[i] = dataclasses.replace(b, description=desc)

    def set_theme(self, new_theme: str) -> None:
        self.theme = new_theme
        if hasattr(self.storage, "set_setting"):
            self.storage.set_setting("theme", new_theme)
        self.dashboard_screen.update_theme(new_theme)

    def set_locale(self, new_locale: str) -> None:
        self.locale = new_locale
        self.msg = get_messages(self.locale)
        if hasattr(self.storage, "set_setting"):
            self.storage.set_setting("locale", new_locale)

        self._update_bindings_language()

        self.dashboard_screen.update_messages(self.msg)
        try:
            from textual.widgets import Footer

            footer = self.query_one(Footer)
            footer.refresh()
        except Exception:
            pass

    def action_open_settings(self) -> None:
        def on_settings_result(result: dict | None) -> None:
            if not result:
                return
            new_theme = result.get("theme")
            new_locale = result.get("locale")

            if new_theme and new_theme != self.theme:
                self.set_theme(new_theme)
                self.notify(self.msg.msg_theme_changed.format(theme=new_theme), title=self.msg.title_settings)

            if new_locale and new_locale != self.locale:
                self.set_locale(new_locale)
                self.notify(
                    self.msg.msg_language_changed.format(lang=self.locale.upper()), title=self.msg.title_settings
                )

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
        self.set_theme(next_theme)
        self.notify(self.msg.msg_theme_changed.format(theme=next_theme), title=self.msg.title_theme)

    def action_switch_language(self) -> None:
        current_idx = SUPPORTED_LOCALES.index(self.locale) if self.locale in SUPPORTED_LOCALES else 0
        next_locale = SUPPORTED_LOCALES[(current_idx + 1) % len(SUPPORTED_LOCALES)]
        self.set_locale(next_locale)
        self.notify(self.msg.msg_language_changed.format(lang=self.locale.upper()), title=self.msg.settings_language)
