from datetime import datetime, time
from unittest.mock import MagicMock

import pytest

from roostr.domain.enums import TerminalApp
from roostr.domain.models import (
    BackgroundTargetConfig,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
)
from roostr.infrastructure.targets.background import BackgroundTargetAdapter
from roostr.infrastructure.targets.dispatcher import TargetDispatcher
from roostr.infrastructure.targets.herdr import HerdrTargetAdapter
from roostr.infrastructure.targets.terminal import TerminalTargetAdapter


@pytest.fixture
def terminal_job(tmp_path):
    return Job(
        id="review-pr",
        name="Review PR",
        cwd=str(tmp_path),
        command="claude '/review'",
        schedule=SchedulePolicy((0,), time(9, 0)),
        target=TerminalTargetConfig(app=TerminalApp.TERMINAL, keep_open=True),
    )


@pytest.fixture
def herdr_job(tmp_path):
    return Job(
        id="daily-report",
        name="Daily Report",
        cwd=str(tmp_path),
        command="claude '/daily-report'",
        schedule=SchedulePolicy((0,), time(8, 0)),
        target=HerdrTargetConfig(space="Roostr", tab_template="Daily {DD}/{MM}"),
    )


@pytest.fixture
def background_job(tmp_path):
    return Job(
        id="cleanup",
        name="Git Cleanup",
        cwd=str(tmp_path),
        command="git gc",
        schedule=SchedulePolicy((0,), time(2, 0)),
        target=BackgroundTargetConfig(notify_on_complete=True),
    )


def test_terminal_adapter_generates_runner_script(terminal_job, tmp_path):
    runner_dir = tmp_path / "runners"
    cmd_runner = MagicMock()
    cmd_runner.return_value.returncode = 0

    adapter = TerminalTargetAdapter(runners_dir=runner_dir, cmd_runner=cmd_runner)
    success, msg = adapter.launch(terminal_job, datetime(2026, 11, 9, 9, 0))

    assert success is True
    script_file = runner_dir / f"{terminal_job.id}.command"
    assert script_file.exists()
    content = script_file.read_text()
    assert "#!/bin/zsh -lic" in content
    assert "claude '/review'" in content

    # Assert osascript was called with script path
    assert cmd_runner.call_count == 1
    args = cmd_runner.call_args[0][0]
    assert "osascript" in args


def test_herdr_adapter_offline(herdr_job):
    cmd_runner = MagicMock()
    cmd_runner.return_value.returncode = 1  # hc server status fails
    adapter = HerdrTargetAdapter(cmd_runner=cmd_runner)

    success, msg = adapter.launch(herdr_job, datetime(2026, 11, 9, 8, 0))
    assert success is False
    assert "Herdr is not running" in msg


def test_background_adapter_spawns_process(background_job, tmp_path):
    logs_dir = tmp_path / "logs"
    popen_mock = MagicMock()

    adapter = BackgroundTargetAdapter(logs_dir=logs_dir, popen_fn=popen_mock)
    success, msg = adapter.launch(background_job, datetime(2026, 11, 9, 2, 0))

    assert success is True
    assert popen_mock.call_count == 1
    assert "Background process dispatched" in msg


def test_target_dispatcher(terminal_job, herdr_job, background_job):
    terminal_adapter = MagicMock()
    herdr_adapter = MagicMock()
    background_adapter = MagicMock()

    dispatcher = TargetDispatcher(
        terminal_adapter=terminal_adapter,
        herdr_adapter=herdr_adapter,
        background_adapter=background_adapter,
    )

    dt = datetime(2026, 11, 9, 10, 0)
    dispatcher.dispatch(terminal_job, dt)
    assert terminal_adapter.launch.call_count == 1

    dispatcher.dispatch(herdr_job, dt)
    assert herdr_adapter.launch.call_count == 1

    dispatcher.dispatch(background_job, dt)
    assert background_adapter.launch.call_count == 1
