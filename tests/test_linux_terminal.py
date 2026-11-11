from datetime import datetime
from unittest.mock import MagicMock

import pytest

from roostr.domain.enums import TerminalApp
from roostr.domain.models import Job, SchedulePolicy, TerminalTargetConfig
from roostr.infrastructure.targets.linux_terminal import LinuxTerminalTargetAdapter


@pytest.fixture
def sample_terminal_job():
    return Job(
        id="test-job",
        name="Test Linux Job",
        cwd="/home/user/project",
        command="echo 'working'",
        schedule=SchedulePolicy(days_of_week=(0, 1, 2, 3, 4)),
        target=TerminalTargetConfig(app=TerminalApp.AUTO, keep_open=True),
    )


def test_generate_runner_script(sample_terminal_job, tmp_path):
    adapter = LinuxTerminalTargetAdapter(runners_dir=tmp_path)
    script = adapter.generate_runner_script(sample_terminal_job)

    assert script.exists()
    assert script.name == "test-job.sh"
    content = script.read_text(encoding="utf-8")
    assert "cd /home/user/project" in content
    assert "echo 'working'" in content
    assert "exec" in content  # keep_open clause


def test_launch_auto_discovers_ghostty(sample_terminal_job, tmp_path):
    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0

    def mock_which(binary):
        return "/usr/bin/ghostty" if binary == "ghostty" else None

    adapter = LinuxTerminalTargetAdapter(
        runners_dir=tmp_path,
        cmd_runner=runner_mock,
        which_fn=mock_which,
    )

    success, msg = adapter.launch(sample_terminal_job, datetime.now())
    assert success is True
    assert "ghostty" in msg

    args = runner_mock.call_args[0][0]
    assert args[0] == "/usr/bin/ghostty"
    assert args[1] == "-e"
    assert "test-job.sh" in args[2]


def test_launch_specific_kitty(sample_terminal_job, tmp_path):
    sample_terminal_job.target.app = TerminalApp.KITTY
    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0

    def mock_which(binary):
        return "/usr/bin/kitty" if binary == "kitty" else None

    adapter = LinuxTerminalTargetAdapter(
        runners_dir=tmp_path,
        cmd_runner=runner_mock,
        which_fn=mock_which,
    )

    success, msg = adapter.launch(sample_terminal_job, datetime.now())
    assert success is True
    assert "kitty" in msg

    args = runner_mock.call_args[0][0]
    assert args[0] == "/usr/bin/kitty"
    assert args[1] == "--"
    assert "test-job.sh" in args[2]


def test_launch_fallback_gnome_terminal(sample_terminal_job, tmp_path):
    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0

    def mock_which(binary):
        return "/usr/bin/gnome-terminal" if binary == "gnome-terminal" else None

    adapter = LinuxTerminalTargetAdapter(
        runners_dir=tmp_path,
        cmd_runner=runner_mock,
        which_fn=mock_which,
    )

    success, msg = adapter.launch(sample_terminal_job, datetime.now())
    assert success is True
    assert "gnome-terminal" in msg

    args = runner_mock.call_args[0][0]
    assert args[0] == "/usr/bin/gnome-terminal"
    assert args[1] == "--"
    assert "test-job.sh" in args[2]


def test_launch_no_terminal_found(sample_terminal_job, tmp_path):
    adapter = LinuxTerminalTargetAdapter(
        runners_dir=tmp_path,
        which_fn=lambda _: None,
    )

    success, msg = adapter.launch(sample_terminal_job, datetime.now())
    assert success is False
    assert "No supported terminal emulator found" in msg
