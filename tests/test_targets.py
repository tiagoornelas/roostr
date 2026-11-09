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


def test_make_herdr_terminal_name():
    from roostr.infrastructure.targets.herdr import make_herdr_terminal_name

    dt = datetime(2026, 11, 9, 15, 24, 21)
    # Long job id
    long_name = make_herdr_terminal_name("daily-monitor-digest", dt)
    assert len(long_name) <= 32
    assert long_name == "daily-monitor-di-20261109-152421"
    assert long_name[0].isalnum()

    # Extreme length
    extreme_name = make_herdr_terminal_name("a" * 100, dt)
    assert len(extreme_name) <= 32
    assert extreme_name == "aaaaaaaaaaaaaaaa-20261109-152421"

    # Non-alphanumeric start
    sanitized = make_herdr_terminal_name("---!@#$$$", dt)
    assert len(sanitized) <= 32
    assert sanitized[0].isalnum()


def test_herdr_adapter_creates_space_if_missing(herdr_job):
    import json

    calls = []

    def mock_runner(cmd, **kwargs):
        calls.append(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        if cmd == ["hc", "server", "status"]:
            return mock_res
        if cmd == ["herdr-app", "ls"]:
            # If space.new was called, return the newly created space
            if any("space.new" in c for c in calls):
                mock_res.stdout = json.dumps(
                    {
                        "spaces": [
                            {
                                "name": "Roostr",
                                "id": "sp_roostr",
                                "tabs": [{"terminals": [{"name": "daily-report-20261109-080000"}]}],
                            }
                        ]
                    }
                )
            else:
                mock_res.stdout = json.dumps({"spaces": []})
            return mock_res
        if "space.new" in cmd:
            mock_res.returncode = 0
            return mock_res
        if len(cmd) > 1 and cmd[0] == "hc" and cmd[1] == "run":
            mock_res.returncode = 0
            mock_res.stdout = json.dumps({"terminal": "t1"})
            return mock_res
        return mock_res

    adapter = HerdrTargetAdapter(cmd_runner=mock_runner, sleep_fn=lambda _: None)
    success, msg = adapter.launch(herdr_job, datetime(2026, 11, 9, 8, 0, 0))
    assert success is True
    assert any("space.new" in c for c in calls)


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


def test_register_herdr_program(tmp_path):
    from roostr.infrastructure.targets.herdr import register_herdr_program

    # 1. Non-existent directory returns False
    assert register_herdr_program(tmp_path / "non_existent") is False

    # 2. Existing herdr directory registers icon and programs.json
    herdr_dir = tmp_path / "herdr-app"
    herdr_dir.mkdir()

    res = register_herdr_program(herdr_dir)
    assert res is True

    icon_file = herdr_dir / "icons" / "roostr.svg"
    assert icon_file.exists()
    assert "<svg" in icon_file.read_text()

    prog_file = herdr_dir / "programs.json"
    assert prog_file.exists()
    import json

    data = json.loads(prog_file.read_text())
    assert "roostr" in data["programs"]
    assert data["programs"]["roostr"]["name"] == "Roostr"
