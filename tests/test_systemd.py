from pathlib import Path
from unittest.mock import MagicMock

import pytest

from roostr.domain.enums import TerminalApp, ToleranceMode
from roostr.domain.models import Job, SchedulePolicy, TerminalTargetConfig
from roostr.infrastructure.systemd import SystemdUserServiceAdapter


@pytest.fixture
def sample_job():
    return Job(
        id="review-pr",
        name="Review PR",
        cwd="/path/to/project",
        command="claude '/review'",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            time_of_day=None,
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=12,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )


def test_systemd_service_unit_generation(tmp_path):
    adapter = SystemdUserServiceAdapter(
        unit_dir=tmp_path / "systemd" / "user",
        binary_path=Path("/usr/bin/roostr"),
    )
    unit_text = adapter.generate_service_unit()

    assert "[Unit]" in unit_text
    assert "Description=Roostr" in unit_text
    assert "[Service]" in unit_text
    assert "ExecStart=/usr/bin/roostr daemon run" in unit_text
    assert "Restart=always" in unit_text
    assert "[Install]" in unit_text
    assert "WantedBy=default.target" in unit_text


def test_systemd_install(tmp_path):
    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0

    adapter = SystemdUserServiceAdapter(
        unit_dir=tmp_path / "systemd" / "user",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )

    unit_path = adapter.install()
    assert unit_path.exists()
    assert unit_path.name == "roostr.service"
    assert "ExecStart=/usr/local/bin/roostr daemon run" in unit_path.read_text(encoding="utf-8")

    # Verify daemon-reload and enable --now were called
    assert runner_mock.call_count == 2
    assert runner_mock.call_args_list[0][0][0] == ["systemctl", "--user", "daemon-reload"]
    assert runner_mock.call_args_list[1][0][0] == ["systemctl", "--user", "enable", "--now", "roostr.service"]


def test_systemd_uninstall(tmp_path):
    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0

    adapter = SystemdUserServiceAdapter(
        unit_dir=tmp_path / "systemd" / "user",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )

    unit_path = adapter.install()
    assert unit_path.exists()

    runner_mock.reset_mock()
    adapter.uninstall()

    assert not unit_path.exists()
    assert runner_mock.call_count == 3
    assert runner_mock.call_args_list[0][0][0] == ["systemctl", "--user", "stop", "roostr.service"]
    assert runner_mock.call_args_list[1][0][0] == ["systemctl", "--user", "disable", "roostr.service"]
    assert runner_mock.call_args_list[2][0][0] == ["systemctl", "--user", "daemon-reload"]


def test_systemd_start_and_stop(tmp_path):
    runner_mock = MagicMock()
    adapter = SystemdUserServiceAdapter(
        unit_dir=tmp_path / "systemd" / "user",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )

    adapter.start()
    assert runner_mock.call_args[0][0] == ["systemctl", "--user", "start", "roostr.service"]

    runner_mock.reset_mock()
    adapter.stop()
    assert runner_mock.call_args[0][0] == ["systemctl", "--user", "stop", "roostr.service"]


def test_systemd_is_running(tmp_path):
    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0
    runner_mock.return_value.stdout = "active\n"

    adapter = SystemdUserServiceAdapter(
        unit_dir=tmp_path / "systemd" / "user",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )

    assert adapter.is_running() is True
    assert runner_mock.call_args[0][0] == ["systemctl", "--user", "is-active", "roostr.service"]

    # When not active
    runner_mock.return_value.returncode = 3
    runner_mock.return_value.stdout = "inactive\n"
    assert adapter.is_running() is False

    # When command raises exception
    runner_mock.side_effect = RuntimeError("systemctl failed")
    assert adapter.is_running() is False


def test_systemd_discover_binary(monkeypatch, tmp_path):
    import shutil
    from unittest.mock import patch

    with patch("pathlib.Path.exists", return_value=False):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/custom/bin/roostr")
        adapter = SystemdUserServiceAdapter(unit_dir=tmp_path)
        assert str(adapter._binary_path) == "/custom/bin/roostr"
