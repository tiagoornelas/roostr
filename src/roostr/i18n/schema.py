from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Messages:
    locale: str
    app_title: str
    app_subtitle: str

    # Keybar bindings
    key_new_job: str
    key_run_now: str
    key_move_job: str
    key_new_folder: str
    key_toggle_pause: str
    key_delete_job: str
    key_quit: str

    # Dashboard
    sidebar_header: str
    inspector_target: str
    inspector_schedule: str
    inspector_execution: str
    inspector_history: str
    empty_state_text: str
    lbl_ungrouped: str

    # Status badges
    status_running_today: str
    status_waiting: str
    status_paused: str
    status_skipped: str
    status_error: str

    # Form modal
    modal_title_new: str
    modal_title_edit: str
    modal_title_move: str
    modal_title_new_folder: str
    lbl_no_folder_root: str
    lbl_create_new_folder_option: str
    lbl_job_id: str
    lbl_job_name: str
    lbl_cwd: str
    lbl_command: str
    lbl_target_type: str
    lbl_terminal_app: str
    lbl_herdr_space: str
    lbl_tab_template: str
    lbl_days: str
    lbl_time: str
    lbl_tolerance_mode: str
    lbl_tolerance_val: str
    lbl_folder: str
    btn_save: str
    btn_cancel: str

    # Settings modal
    key_settings: str
    settings_title: str
    settings_theme: str
    settings_language: str
    btn_close: str

    # Notifications
    notify_success_created: str
    notify_success_deleted: str
    notify_paused: str
    notify_resumed: str
    notify_running: str
    notify_no_selection: str
