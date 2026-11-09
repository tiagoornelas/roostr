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
    key_settings: str
    key_quit: str

    # Dashboard & Inspector sections
    sidebar_header: str
    inspector_target: str
    inspector_schedule: str
    inspector_execution: str
    inspector_history: str
    inspector_action: str
    inspector_harness: str
    inspector_prompt: str
    empty_state_text: str
    lbl_ungrouped: str
    lbl_folder_title: str
    lbl_subfolder_title: str
    inspector_active_jobs: str
    inspector_created: str
    inspector_total_runs: str
    folder_actions_title: str
    folder_action_move: str
    folder_action_create: str
    folder_action_delete: str

    # Inspector Property Labels
    lbl_prop_folder: str
    lbl_prop_time: str
    lbl_prop_days: str
    lbl_prop_policy: str
    lbl_prop_cwd: str
    lbl_prop_mode: str
    lbl_prop_harness: str
    lbl_prop_prompt: str
    lbl_prop_compiled: str
    lbl_prop_command: str

    # Status badges
    status_running_today: str
    status_waiting: str
    status_paused: str
    status_skipped: str
    status_error: str

    # Schedule & Tolerance display
    days_weekdays_short: str
    days_everyday_short: str
    days_weekdays_full: str
    days_everyday_full: str
    days_weekend_full: str
    days_names_abbr: tuple[str, ...]
    tol_exact_desc: str
    tol_until_hour_desc: str
    tol_hours_window_desc: str

    # History & Execution Row
    empty_history_text: str
    lbl_click_to_copy: str
    notify_copied_attach: str
    notify_copied_log: str
    notify_redirected_herdr: str

    # Form modal
    modal_title_new: str
    modal_title_edit: str
    tab_agent_action: str
    tab_schedule: str
    tab_target_env: str
    modal_title_move: str
    modal_title_new_folder: str
    lbl_no_folder_root: str
    lbl_create_new_folder_option: str
    lbl_job_id: str
    lbl_job_name: str
    lbl_cwd: str
    lbl_action_type: str
    lbl_action_agent: str
    lbl_action_command: str
    lbl_harness: str
    lbl_prompt: str
    lbl_prompt_placeholder: str
    lbl_prompt_hint: str
    lbl_command: str
    lbl_command_placeholder: str
    err_empty_prompt: str
    err_empty_command: str
    err_required_fields: str
    err_invalid_time: str
    lbl_target_type: str
    target_opt_terminal: str
    target_opt_herdr: str
    target_opt_background: str
    target_opt_terminal_short: str
    target_opt_background_short: str
    lbl_bg_log: str
    lbl_terminal_app: str
    lbl_herdr_space: str
    lbl_herdr_space_hint: str
    lbl_tab_template: str
    lbl_tab_template_hint: str
    lbl_frequency: str
    freq_opt_daily: str
    freq_opt_interval_hours: str
    freq_opt_interval_minutes: str
    lbl_interval_hours: str
    lbl_interval_hours_hint: str
    lbl_interval_minutes: str
    lbl_interval_minutes_hint: str
    lbl_days: str
    days_opt_weekdays: str
    days_opt_everyday: str
    days_opt_custom: str
    lbl_time: str
    lbl_time_hint: str
    lbl_interval_window: str
    lbl_interval_window_hint: str
    lbl_start_time: str
    lbl_end_time: str
    lbl_tolerance_section_title: str
    lbl_tolerance_explanation: str
    lbl_tolerance_mode: str
    tol_opt_until_hour: str
    tol_opt_hours_window: str
    tol_opt_exact: str
    lbl_tol_until_hour_input: str
    lbl_tol_window_hours_input: str
    lbl_tolerance_val: str
    err_no_days_selected: str
    err_invalid_interval: str
    lbl_folder: str
    btn_save: str
    btn_cancel: str

    # Settings modal
    settings_title: str
    settings_theme: str
    settings_language: str
    btn_close: str

    # Modals common / Folder & Move
    lbl_select_target_folder: str
    lbl_folder_name_rules: str
    placeholder_folder_name: str
    err_folder_empty: str
    err_folder_hierarchy: str

    # Form Placeholders & Options
    placeholder_job_name: str
    placeholder_herdr_space: str
    placeholder_time_window_start: str
    placeholder_time_window_end: str
    target_opt_auto_detect: str
    target_opt_headless: str

    # Schedule & Interval Inspector Display
    lbl_every_hours: str
    lbl_every_minutes: str
    lbl_every_hours_title: str
    lbl_every_minutes_title: str
    lbl_times_per_day: str
    lbl_not_applicable_interval: str

    # History Row Display (Status & Trigger Labels)
    status_history_success: str
    status_history_already_ran: str
    status_history_outside_window: str
    status_history_target_offline: str
    status_history_failed: str
    trigger_history_scheduled: str
    trigger_history_manual: str

    # Notifications & Titles
    title_success: str
    title_error: str
    title_moved: str
    title_deleted: str
    title_cannot_delete: str
    title_executing: str
    title_completed: str
    title_schedule: str
    title_settings: str
    title_theme: str
    msg_error_saving_job: str
    msg_error_moving_job: str
    msg_error_creating_folder: str
    msg_theme_changed: str
    msg_language_changed: str
    notify_success_created: str
    notify_success_deleted: str
    notify_paused: str
    notify_resumed: str
    notify_running: str
    notify_no_selection: str
    notify_moved: str
    notify_folder_created: str
    notify_folder_deleted: str
