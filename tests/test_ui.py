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
        top_title = dashboard.query_one("#app-title", Label)
        assert "🐓" in str(top_title.render())
        assert "roostr" in str(top_title.render())


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
