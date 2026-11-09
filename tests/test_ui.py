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
        await pilot.press("l")
        await pilot.pause()
        assert app.locale == "pt_br"
        await pilot.press("l")
        await pilot.pause()
        assert app.locale == "es"


@pytest.mark.asyncio
async def test_app_switch_theme(storage, sample_job):
    storage.save_job(sample_job)
    app = RoostrApp(storage=storage, locale="en", theme="night")

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == "night"

        # Cycle through morning -> tokyo-night -> nord -> dracula -> night
        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "morning"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "tokyo-night"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "nord"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "dracula"

        await pilot.press("t")
        await pilot.pause()
        assert app.theme == "night"


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
        assert isinstance(app.screen, DashboardScreen)


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
    monkeypatch.setattr(
        "roostr.ui.screens.dashboard.subprocess.run",
        lambda cmd, **kwargs: copied.append(kwargs.get("input", b"").decode()),
    )

    app = RoostrApp(storage=storage, locale="en")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        row = app.query_one(ExecutionRow)
        assert row.attach_cmd == "hc attach tb67c2d071c57613cb47463761c70ee3e1"
        assert "tb67c2d071c57613cb47463761c70ee3e1" not in row.cleaned_details

        await pilot.click(row)
        await pilot.pause()

        assert "hc attach tb67c2d071c57613cb47463761c70ee3e1" in copied


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
