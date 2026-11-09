import plistlib
from datetime import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from roostr.domain.enums import TerminalApp, ToleranceMode
from roostr.domain.models import Job, SchedulePolicy, TerminalTargetConfig
from roostr.infrastructure.launchd import LaunchdSchedulerAdapter


@pytest.fixture
def sample_job():
    return Job(
        id="review-pr",
        name="Review PR",
        cwd="/path/to/project",
        command="claude '/review'",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            time_of_day=time(9, 0),
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=12,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )


def test_generate_plist(sample_job, tmp_path):
    adapter = LaunchdSchedulerAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/usr/local/bin/roostr"),
    )
    plist_xml = adapter.generate_plist_xml(sample_job)
    data = plistlib.loads(plist_xml.encode("utf-8"))

    assert data["Label"] == "com.tiagoornelas.roostr.review-pr"
    assert data["ProgramArguments"] == ["/usr/local/bin/roostr", "run", "review-pr"]
    assert data["RunAtLoad"] is True
    assert len(data["StartCalendarInterval"]) == 5
    assert data["StartCalendarInterval"][0] == {"Weekday": 1, "Hour": 9, "Minute": 0}
    assert "review-pr.log" in data["StandardOutPath"]


def test_install_and_uninstall(sample_job, tmp_path):
    runner_mock = MagicMock()
    adapter = LaunchdSchedulerAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )

    plist_path = adapter.install(sample_job)
    assert plist_path.exists()
    assert runner_mock.call_count == 1
    args = runner_mock.call_args[0][0]
    assert "launchctl" in args
    assert "load" in args

    runner_mock.reset_mock()
    adapter.uninstall("review-pr")
    assert not plist_path.exists()
    assert runner_mock.call_count == 1
    args = runner_mock.call_args[0][0]
    assert "launchctl" in args
    assert "unload" in args
