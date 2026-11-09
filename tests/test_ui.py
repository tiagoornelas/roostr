from datetime import time
from unittest.mock import MagicMock

import pytest
from textual.widgets import Label

from roostr.domain.enums import ExecutionStatus, TerminalApp
from roostr.domain.models import Job, SchedulePolicy, TerminalTargetConfig
from roostr.infrastructure.storage import SQLiteStorage
from roostr.ui.app import RoostrApp
from roostr.ui.screens.dashboard import DashboardScreen


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(tmp_path / "test_ui.db")


@pytest.fixture
def sample_job():
    return Job(
        id="review-pr",
        name="Review PR",
        cwd="/path/to/project",
        command="claude '/review'",
        schedule=SchedulePolicy((0, 1, 2, 3, 4), time(9, 0)),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )


@pytest.mark.asyncio
async def test_app_dashboard_mounts(storage, sample_job):
    storage.save_job(sample_job)
    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test() as pilot:
        await pilot.pause()
        dashboard = app.screen
        assert isinstance(dashboard, DashboardScreen)
        assert dashboard.selected_job is not None
        assert dashboard.selected_job.id == "review-pr"
        footer_brand = dashboard.query_one("#footer-brand", Label)
        assert "🐓" in str(footer_brand.render())
        assert "roostr" in str(footer_brand.render())


@pytest.mark.asyncio
async def test_app_action_run_now(storage, sample_job):
    storage.save_job(sample_job)
    exec_mock = MagicMock()
    exec_mock.execute.return_value = (ExecutionStatus.SUCCESS, "Launched")

    app = RoostrApp(storage=storage, locale="en", execute_use_case=exec_mock)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert exec_mock.execute.call_count == 1
        assert exec_mock.execute.call_args[0][0] == "review-pr"


@pytest.mark.asyncio
async def test_app_action_toggle_pause(storage, sample_job):
    storage.save_job(sample_job)
    manage_mock = MagicMock()
    manage_mock.toggle_pause.return_value = True

    app = RoostrApp(storage=storage, locale="en", manage_use_case=manage_mock)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert manage_mock.toggle_pause.call_count == 1


@pytest.mark.asyncio
async def test_app_action_delete_job(storage, sample_job):
    storage.save_job(sample_job)
    manage_mock = MagicMock()

    app = RoostrApp(storage=storage, locale="en", manage_use_case=manage_mock)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert manage_mock.delete_job.call_count == 1


@pytest.mark.asyncio
async def test_app_switch_language(storage, sample_job):
    storage.save_job(sample_job)
    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.locale == "en"
        assert storage.get_setting("locale") == "en"

        await pilot.press("l")
        await pilot.pause()
        assert app.locale == "pt_br"
        assert storage.get_setting("locale") == "pt_br"
        assert app.dashboard_screen.msg.locale == "pt_br"

        await pilot.press("l")
        await pilot.pause()
        assert app.locale == "es"
        assert storage.get_setting("locale") == "es"
        assert app.dashboard_screen.msg.locale == "es"


@pytest.mark.asyncio
async def test_app_switch_theme(storage, sample_job):
    storage.save_job(sample_job)
    app = RoostrApp(storage=storage, locale="en", theme="night")

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == "night"
        assert storage.get_setting("theme") == "night"

        # Cycle through morning -> tokyo-night -> nord -> dracula -> night
        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "morning"
        assert storage.get_setting("theme") == "morning"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "tokyo-night"
        assert storage.get_setting("theme") == "tokyo-night"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "nord"
        assert storage.get_setting("theme") == "nord"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "dracula"
        assert storage.get_setting("theme") == "dracula"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "night"
        assert storage.get_setting("theme") == "night"


@pytest.mark.asyncio
async def test_app_open_settings(storage, sample_job):
    from roostr.ui.screens.settings_modal import SettingsModal

    storage.save_job(sample_job)
    app = RoostrApp(storage=storage, locale="en", theme="night")

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SettingsModal)
        await pilot.press("escape")
        await pilot.pause()


@pytest.mark.asyncio
async def test_app_folder_and_subfolder_accordion(storage):
    from roostr.ui.screens.dashboard import FolderHeaderItem, JobListItem, SubfolderHeaderItem

    j_root = Job(
        id="j-root",
        name="Root Job",
        cwd="/tmp",
        command="echo",
        schedule=SchedulePolicy((0,), time(8, 0)),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
        folder=None,
    )
    j_work = Job(
        id="j-work",
        name="Work Job",
        cwd="/tmp",
        command="echo",
        schedule=SchedulePolicy((0,), time(8, 0)),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
        folder="Work",
    )
    j_reports = Job(
        id="j-reports",
        name="Report Job",
        cwd="/tmp",
        command="echo",
        schedule=SchedulePolicy((0,), time(8, 0)),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
        folder="Work/Reports",
    )

    storage.save_job(j_root)
    storage.save_job(j_work)
    storage.save_job(j_reports)

    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test() as pilot:
        await pilot.pause()
        dashboard = app.screen
        assert isinstance(dashboard, DashboardScreen)

        # Verify initial items: Folders first, Ungrouped jobs LAST
        list_view = dashboard.query_one("#jobs-list")
        items = list(list_view.children)
        assert len(items) == 6
        assert isinstance(items[0], FolderHeaderItem)  # Work folder
        assert items[0].folder_name == "Work"
        assert items[0].count == 2
        assert isinstance(items[1], JobListItem)  # Work Job
        assert isinstance(items[2], SubfolderHeaderItem)  # Reports subfolder
        assert items[2].subfolder_name == "Reports"
        assert items[2].count == 1
        assert isinstance(items[3], JobListItem)  # Report Job
        from roostr.ui.screens.dashboard import UngroupedHeaderItem

        assert isinstance(items[4], UngroupedHeaderItem)
        assert isinstance(items[5], JobListItem)  # Root job

        # Click FolderHeaderItem to collapse Work
        await pilot.click(FolderHeaderItem)
        await pilot.pause()

        # After collapsing root folder Work: FolderHeaderItem, UngroupedHeaderItem, Root Job remain
        items_collapsed = list(list_view.children)
        assert len(items_collapsed) == 3
        assert isinstance(items_collapsed[0], FolderHeaderItem)
        assert items_collapsed[0].is_collapsed is True
        assert isinstance(items_collapsed[1], UngroupedHeaderItem)
        assert isinstance(items_collapsed[2], JobListItem)

        # Click FolderHeaderItem again to expand
        await pilot.click(FolderHeaderItem)
        await pilot.pause()
        assert len(list_view.children) == 6

        # Click SubfolderHeaderItem to collapse only Reports subfolder
        await pilot.click(SubfolderHeaderItem)
        await pilot.pause()
        items_sub_collapsed = list(list_view.children)
        # Folder WORK, Work Job, Subfolder Reports (Report Job is hidden), UngroupedHeaderItem, Root Job
        assert len(items_sub_collapsed) == 5
        assert isinstance(items_sub_collapsed[2], SubfolderHeaderItem)
        assert items_sub_collapsed[2].is_collapsed is True


@pytest.mark.asyncio
async def test_app_execution_row_click_copies_session(storage, sample_job, monkeypatch):
    from datetime import datetime

    from roostr.domain.enums import TriggerType
    from roostr.domain.models import ExecutionRecord
    from roostr.ui.screens.dashboard import ExecutionRow

    storage.save_job(sample_job)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=sample_job.id,
            timestamp=datetime(2026, 11, 9, 8, 1, 2),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="Opened terminal in tab tb67c2d071c57613cb47463761c70ee3e1 ('Daily 09/11')",
        )
    )

    copied = []
    # Mock redirect to return False (tab offline) to test copying session command
    monkeypatch.setattr(
        "roostr.ui.screens.dashboard.try_redirect_to_herdr_tab",
        lambda tab_id: (False, "offline"),
    )
    monkeypatch.setattr(
        "roostr.ui.screens.dashboard.subprocess.run",
        lambda cmd, **kwargs: copied.append(kwargs.get("input", b"").decode()),
    )

    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        row = app.query_one(ExecutionRow)
        assert row.herdr_tab_id == "tb67c2d071c57613cb47463761c70ee3e1"
        assert "tb67c2d071c57613cb47463761c70ee3e1" not in row.cleaned_details

        await pilot.click(row)
        await pilot.pause()

        expected_cmd = f'cd "{sample_job.cwd}" && {sample_job.command}'
        assert expected_cmd in copied


@pytest.mark.asyncio
async def test_app_execution_row_click_redirects_to_herdr(storage, sample_job, monkeypatch):
    from datetime import datetime

    from roostr.domain.enums import TriggerType
    from roostr.domain.models import ExecutionRecord
    from roostr.ui.screens.dashboard import ExecutionRow

    storage.save_job(sample_job)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=sample_job.id,
            timestamp=datetime(2026, 11, 9, 8, 1, 2),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="Opened terminal in tab tb67c2d071c57613cb47463761c70ee3e1 ('Daily 09/11')",
        )
    )

    redirect_calls = []
    monkeypatch.setattr(
        "roostr.ui.screens.dashboard.try_redirect_to_herdr_tab",
        lambda tab_id: (redirect_calls.append(tab_id) or True, "Daily 09/11"),
    )

    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        row = app.query_one(ExecutionRow)
        await pilot.click(row)
        await pilot.pause()

        assert "tb67c2d071c57613cb47463761c70ee3e1" in redirect_calls


@pytest.mark.asyncio
async def test_app_action_move_job_and_new_folder(storage, sample_job):
    from roostr.ui.screens.folder_modal import NewFolderModal
    from roostr.ui.screens.move_modal import MoveJobModal

    storage.save_job(sample_job)
    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.dashboard_screen.selected_job.id == sample_job.id

        # 1. Press 'f' to open NewFolderModal
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, NewFolderModal)

        # Type new folder name and submit
        inp = app.screen.query_one("#inp-folder-name")
        inp.value = "Ops/Deploy"
        await pilot.press("enter")
        await pilot.pause()

        assert "Ops" in storage.list_folders()
        assert "Ops/Deploy" in storage.list_folders()

        # 2. Press 'm' to open MoveJobModal
        await pilot.press("m")
        await pilot.pause()
        assert isinstance(app.screen, MoveJobModal)

        # Select 'Ops/Deploy' in dest-list and press enter
        dest_list = app.screen.query_one("#dest-list")
        dest_list.index = 2
        await pilot.press("enter")
        await pilot.pause()

        # Job is now moved to Ops/Deploy
        updated_job = storage.get_job(sample_job.id)
        assert updated_job.folder == "Ops/Deploy"


@pytest.mark.asyncio
async def test_app_action_new_agent_job_modal(storage):
    from textual.widgets import Input, Select, TextArea

    from roostr.domain.enums import ActionType, AIHarness
    from roostr.domain.models import AgentAction
    from roostr.ui.screens.form_modal import JobFormModal

    manage_mock = MagicMock()
    app = RoostrApp(storage=storage, locale="en", manage_use_case=manage_mock)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Press 'n' to open JobFormModal
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, JobFormModal)

        modal = app.screen
        modal.query_one("#inp-name", Input).value = "Daily Claude Report"
        modal.query_one("#inp-cwd", Input).value = "/tmp"

        modal.query_one("#sel-action-type", Select).value = "agent"
        modal.query_one("#sel-harness", Select).value = "claude"
        modal.query_one("#inp-prompt", TextArea).text = "Check open PRs\nGenerate daily report"

        # Click save
        await pilot.click("#btn-save")
        await pilot.pause()

        # Verify job was created via manage_use_case with auto-inferred slug id
        assert manage_mock.create_job.call_count == 1
        created_job = manage_mock.create_job.call_args[0][0]
        assert created_job.id == "daily-claude-report"
        assert created_job.name == "Daily Claude Report"
        assert created_job.action.action_type == ActionType.AGENT
        assert isinstance(created_job.action, AgentAction)
        assert created_job.action.harness == AIHarness.CLAUDE
        assert "Check open PRs\nGenerate daily report" in created_job.action.prompt
        assert created_job.command.startswith("claude 'Check open PRs")


@pytest.mark.asyncio
async def test_prompt_text_area_shift_enter_line_break(storage):
    from textual.widgets import Input, Select

    from roostr.ui.screens.form_modal import JobFormModal, PromptTextArea

    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, JobFormModal)

        modal = app.screen
        ta = modal.query_one("#inp-prompt", PromptTextArea)
        ta.focus()
        await pilot.pause()

        # Type first line
        await pilot.press("l", "i", "n", "e", "1")
        # Press shift+enter
        await pilot.press("shift+enter")
        # Type second line
        await pilot.press("l", "i", "n", "e", "2")
        # Press enter
        await pilot.press("enter")
        # Type third line
        await pilot.press("l", "i", "n", "e", "3")
        await pilot.pause()

        assert ta.text == "line1\nline2\nline3"

        # Test Ctrl+S binding triggers save
        modal.query_one("#inp-name", Input).value = "Test Shift Enter"
        modal.query_one("#inp-cwd", Input).value = "/tmp"
        modal.query_one("#sel-action-type", Select).value = "agent"
        modal.query_one("#sel-harness", Select).value = "claude"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not isinstance(app.screen, JobFormModal)


@pytest.mark.asyncio
async def test_pt_br_localization_in_form_and_inspector(storage, sample_job):
    from textual.widgets import Label, Select, Static

    from roostr.ui.screens.form_modal import JobFormModal

    storage.save_job(sample_job)
    app = RoostrApp(storage=storage, locale="pt_br")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.locale == "pt_br"

        # Check inspector static has Portuguese labels
        inspector = app.dashboard_screen.query_one("#inspector-details", Static)
        assert "DESTINO DE EXECUÇÃO" in inspector.content
        assert "AGENDAMENTO & TOLERÂNCIA" in inspector.content
        assert "COMANDO & AMBIENTE" in inspector.content

        # Open form in PT-BR
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, JobFormModal)

        modal = app.screen
        title_lbl = modal.query_one(".form-title", Label)
        assert "Criar Novo Job" in str(title_lbl.render())

        # Check select options in PT-BR
        target_select = modal.query_one("#sel-target-type", Select)
        options_text = [str(opt[0]) for opt in target_select._options]
        assert "Janela de Terminal" in options_text
        assert "Processo em Segundo Plano" in options_text

        harness_select = modal.query_one("#sel-harness", Select)
        harness_options_text = [str(opt[0]) for opt in harness_select._options]
        # Assert no emojis in harness options
        assert any("Claude Code" in opt for opt in harness_options_text)
        assert not any("🟣" in opt or "🔵" in opt for opt in harness_options_text)

        await pilot.press("escape")
        await pilot.pause()


@pytest.mark.asyncio
async def test_form_modal_frequency_tolerance_and_days(storage):
    from textual.widgets import Checkbox, Input, Select

    from roostr.domain.enums import ScheduleFrequency, ToleranceMode
    from roostr.ui.screens.form_modal import JobFormModal

    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, JobFormModal)
        modal = app.screen

        # Test Frequency toggling and conditional containers
        freq_select = modal.query_one("#sel-frequency", Select)
        daily_box = modal.query_one("#freq-daily-box")
        hours_box = modal.query_one("#freq-hours-box")
        minutes_box = modal.query_one("#freq-minutes-box")

        assert daily_box.display is True
        assert hours_box.display is False
        assert minutes_box.display is False

        # Switch to INTERVAL_HOURS
        freq_select.value = ScheduleFrequency.INTERVAL_HOURS.value
        await pilot.pause()
        assert daily_box.display is False
        assert hours_box.display is True
        assert minutes_box.display is False

        # Switch to INTERVAL_MINUTES
        freq_select.value = ScheduleFrequency.INTERVAL_MINUTES.value
        await pilot.pause()
        assert daily_box.display is False
        assert hours_box.display is False
        assert minutes_box.display is True

        # Switch back to DAILY
        freq_select.value = ScheduleFrequency.DAILY.value
        await pilot.pause()
        assert daily_box.display is True

        # Test Tolerance toggling and conditional containers
        tol_select = modal.query_one("#sel-tolerance-mode", Select)
        until_box = modal.query_one("#tol-until-hour-box")
        window_box = modal.query_one("#tol-hours-window-box")

        assert until_box.display is True
        assert window_box.display is False

        # Switch to EXACT
        tol_select.value = ToleranceMode.EXACT.value
        await pilot.pause()
        assert until_box.display is False
        assert window_box.display is False

        # Switch to WINDOW_HOURS
        tol_select.value = ToleranceMode.WINDOW_HOURS.value
        await pilot.pause()
        assert until_box.display is False
        assert window_box.display is True

        # Switch back to UNTIL_HOUR
        tol_select.value = ToleranceMode.UNTIL_HOUR.value
        await pilot.pause()
        assert until_box.display is True
        assert window_box.display is False

        # Test Days Checkboxes
        chk_mon = modal.query_one("#chk-day-0", Checkbox)
        chk_sun = modal.query_one("#chk-day-6", Checkbox)
        assert chk_mon.value is True  # Default Mon-Fri checked
        assert chk_sun.value is False

        # Uncheck all days to test validation
        for i in range(7):
            modal.query_one(f"#chk-day-{i}", Checkbox).value = False

        modal.query_one("#inp-name", Input).value = "Interval Job"
        modal.query_one("#inp-cwd", Input).value = "/tmp"
        modal.query_one("#sel-action-type", Select).value = "command"
        modal.query_one("#inp-command", Input).value = "echo 'interval'"
        freq_select.value = ScheduleFrequency.INTERVAL_HOURS.value
        modal.query_one("#inp-interval-hours", Input).value = "3"

        # Attempt to save with 0 days checked -> should remain in modal
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, JobFormModal)

        # Check Monday and Wednesday
        modal.query_one("#chk-day-0", Checkbox).value = True
        modal.query_one("#chk-day-2", Checkbox).value = True

        # Now save successfully
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not isinstance(app.screen, JobFormModal)

        # Verify job saved with slugified ID and correct interval/days
        saved = storage.get_job("interval-job")
        assert saved is not None
        assert saved.name == "Interval Job"
        assert saved.schedule.frequency == ScheduleFrequency.INTERVAL_HOURS
        assert saved.schedule.interval_value == 3
        assert saved.schedule.days_of_week == (0, 2)
