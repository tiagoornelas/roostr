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


def test_generate_plist_interval(tmp_path):
    from roostr.domain.enums import ScheduleFrequency

    job = Job(
        id="interval-job",
        name="Interval Job",
        cwd="/tmp",
        command="echo interval",
        schedule=SchedulePolicy(
            days_of_week=(0, 1),
            frequency=ScheduleFrequency.INTERVAL_HOURS,
            interval_value=3,
        ),
        target=TerminalTargetConfig(),
    )
    adapter = LaunchdSchedulerAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/usr/local/bin/roostr"),
    )
    plist_xml = adapter.generate_plist_xml(job)
    data = plistlib.loads(plist_xml.encode("utf-8"))

    assert data["StartInterval"] == 3 * 3600
    assert "StartCalendarInterval" not in data


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
    assert runner_mock.call_count == 2
    unload_args = runner_mock.call_args_list[0][0][0]
    load_args = runner_mock.call_args_list[1][0][0]
    assert "launchctl" in unload_args and "unload" in unload_args
    assert "launchctl" in load_args and "load" in load_args

    runner_mock.reset_mock()
    adapter.uninstall("review-pr")
    assert not plist_path.exists()
    assert runner_mock.call_count == 1
    args = runner_mock.call_args[0][0]
    assert "launchctl" in args
    assert "unload" in args


def test_launchd_service_adapter(tmp_path):
    from roostr.infrastructure.launchd import LaunchdServiceAdapter

    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0
    adapter = LaunchdServiceAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )

    xml = adapter.generate_plist_xml()
    data = plistlib.loads(xml.encode("utf-8"))
    assert data["Label"] == "com.tiagoornelas.roostr.daemon"
    assert data["ProgramArguments"] == ["/usr/local/bin/roostr", "daemon", "run"]
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] is True
    assert "roostr-daemon.log" in data["StandardOutPath"]

    plist_path = adapter.install()
    assert plist_path.exists()
    assert runner_mock.call_count == 2

    assert adapter.is_running() is True

    adapter.start()
    assert runner_mock.call_args[0][0] == ["launchctl", "start", "com.tiagoornelas.roostr.daemon"]

    adapter.stop()
    assert runner_mock.call_args[0][0] == ["launchctl", "stop", "com.tiagoornelas.roostr.daemon"]

    adapter.uninstall()
    assert not plist_path.exists()


def test_launchd_pause_resume_and_interval_minutes(sample_job, tmp_path):
    from roostr.domain.enums import ScheduleFrequency

    runner_mock = MagicMock()
    runner_mock.return_value.returncode = 0
    adapter = LaunchdSchedulerAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )

    # 1. Pause without plist existing -> does nothing
    adapter.pause(sample_job.id)

    # Install job
    plist_path = adapter.install(sample_job)
    assert plist_path.exists()

    # 2. Pause with plist existing -> unloads
    runner_mock.reset_mock()
    adapter.pause(sample_job.id)
    assert runner_mock.call_count == 1
    assert "unload" in runner_mock.call_args[0][0]

    # 3. Resume with plist existing -> loads
    runner_mock.reset_mock()
    adapter.resume(sample_job)
    assert runner_mock.call_count == 1
    assert "load" in runner_mock.call_args[0][0]

    # 4. Resume without plist existing -> calls install
    plist_path.unlink()
    runner_mock.reset_mock()
    adapter.resume(sample_job)
    assert plist_path.exists()

    # 5. INTERVAL_MINUTES in generate_plist_xml
    sample_job.schedule.frequency = ScheduleFrequency.INTERVAL_MINUTES
    sample_job.schedule.interval_value = 15
    xml = adapter.generate_plist_xml(sample_job)
    data = plistlib.loads(xml.encode("utf-8"))
    assert data["StartInterval"] == 15 * 60


def test_launchd_service_adapter_exception_in_is_running(tmp_path):
    from roostr.infrastructure.launchd import LaunchdServiceAdapter

    runner_mock = MagicMock(side_effect=RuntimeError("launchctl exploded"))
    adapter = LaunchdServiceAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/usr/local/bin/roostr"),
        cmd_runner=runner_mock,
    )
    assert adapter.is_running() is False


def test_launchd_discover_binary_fallbacks(monkeypatch):
    import shutil
    from unittest.mock import patch

    from roostr.infrastructure.launchd import LaunchdSchedulerAdapter, LaunchdServiceAdapter

    # 1. Local bin doesn't exist, which returns a path
    with patch("pathlib.Path.exists", return_value=False):
        monkeypatch.setattr(shutil, "which", lambda cmd: "/custom/bin/roostr")
        srv_adapter = LaunchdServiceAdapter()
        assert str(srv_adapter._binary_path) == "/custom/bin/roostr"

        sched_adapter = LaunchdSchedulerAdapter()
        assert str(sched_adapter._binary_path) == "/custom/bin/roostr"

    # 2. Local bin doesn't exist, which returns None -> fallback /usr/local/bin/roostr
    with patch("pathlib.Path.exists", return_value=False):
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        srv_adapter2 = LaunchdServiceAdapter()
        assert str(srv_adapter2._binary_path) == "/usr/local/bin/roostr"

        sched_adapter2 = LaunchdSchedulerAdapter()
        assert str(sched_adapter2._binary_path) == "/usr/local/bin/roostr"

    # 3. Local bin exists
    with patch("pathlib.Path.exists", return_value=True):
        srv_adapter3 = LaunchdServiceAdapter()
        assert "roostr" in str(srv_adapter3._binary_path)
        sched_adapter3 = LaunchdSchedulerAdapter()
        assert "roostr" in str(sched_adapter3._binary_path)


def test_launchd_generate_plist_without_local_bin_in_path(sample_job, monkeypatch):
    from roostr.infrastructure.launchd import LaunchdSchedulerAdapter, LaunchdServiceAdapter

    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    srv = LaunchdServiceAdapter(binary_path=Path("/bin/roostr"))
    srv_xml = srv.generate_plist_xml()
    assert ".local/bin" in srv_xml

    sched = LaunchdSchedulerAdapter(binary_path=Path("/bin/roostr"))
    sched_xml = sched.generate_plist_xml(sample_job)
    assert ".local/bin" in sched_xml


def test_launchd_exception_swallowing_on_unload_and_load(sample_job, tmp_path):
    from roostr.infrastructure.launchd import LaunchdSchedulerAdapter, LaunchdServiceAdapter

    fail_load_flag = [False]

    def fail_runner(cmd):
        if "unload" in cmd:
            raise RuntimeError("launchctl unload error")
        if "load" in cmd and fail_load_flag[0]:
            raise RuntimeError("launchctl load error on resume")
        res = MagicMock()
        res.returncode = 0
        return res

    srv = LaunchdServiceAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/bin/roostr"),
        cmd_runner=fail_runner,
    )
    # install and uninstall should not raise
    srv.install()
    srv.uninstall()

    sched = LaunchdSchedulerAdapter(
        agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "Logs",
        binary_path=Path("/bin/roostr"),
        cmd_runner=fail_runner,
    )
    sched.install(sample_job)
    sched.pause(sample_job.id)
    fail_load_flag[0] = True
    sched.resume(sample_job)
    sched.uninstall(sample_job.id)
