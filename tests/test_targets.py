from datetime import datetime, time
from unittest.mock import MagicMock, patch

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


def test_herdr_adapter_keep_open_command(herdr_job):
    import json

    calls = []

    def mock_runner(cmd, **kwargs):
        calls.append(cmd)
        mock_res = MagicMock()
        mock_res.returncode = 0
        if cmd == ["hc", "server", "status"]:
            return mock_res
        if cmd == ["herdr-app", "ls"]:
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
            return mock_res
        if len(cmd) > 1 and cmd[0] == "hc" and cmd[1] == "run":
            mock_res.stdout = json.dumps({"terminal": "t1"})
            return mock_res
        return mock_res

    adapter = HerdrTargetAdapter(cmd_runner=mock_runner, sleep_fn=lambda _: None)

    # 1. Default keep_open is True: command uses eval "$@"; exec "$0" -li pattern
    herdr_job.target.keep_open = True
    adapter.launch(herdr_job, datetime(2026, 11, 9, 8, 0, 0))
    hc_calls = [c for c in calls if len(c) > 1 and c[0] == "hc" and c[1] == "run"]
    assert len(hc_calls) == 1
    hc_cmd = hc_calls[0]
    expected_tail = ["env", "TERM=xterm-256color", "zsh", "-lic", 'eval "$@"; exec "$0" -li', "zsh", herdr_job.command]
    assert hc_cmd[-len(expected_tail) :] == expected_tail

    # 2. keep_open is False: command exits directly with job.command
    calls.clear()
    herdr_job.target.keep_open = False
    adapter.launch(herdr_job, datetime(2026, 11, 9, 8, 0, 0))
    hc_calls = [c for c in calls if len(c) > 1 and c[0] == "hc" and c[1] == "run"]
    assert len(hc_calls) == 1
    hc_cmd = hc_calls[0]
    expected_tail_no_keep = ["env", "TERM=xterm-256color", "zsh", "-lic", herdr_job.command]
    assert hc_cmd[-len(expected_tail_no_keep) :] == expected_tail_no_keep


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

    # 3. Invalid JSON in programs.json resets to valid
    prog_file.write_text("{ invalid json")
    assert register_herdr_program(herdr_dir) is True

    # 4. programs key is not a dict
    prog_file.write_text(json.dumps({"programs": "invalid"}))
    assert register_herdr_program(herdr_dir) is True

    # 5. Permission / write exception
    with patch("pathlib.Path.write_text", side_effect=OSError("Write failed")):
        assert register_herdr_program(herdr_dir) is False


def test_herdr_adapter_error_branches_and_tab_rename(herdr_job, tmp_path):
    import json
    from unittest.mock import patch

    from roostr.infrastructure.targets.herdr import HerdrTargetAdapter

    # 1. is_running exception
    err_runner = MagicMock(side_effect=RuntimeError("hc offline"))
    adapter = HerdrTargetAdapter(cmd_runner=err_runner)
    assert adapter.is_running() is False

    # 2. get_space_id empty stdout / returncode != 0 / json exception
    mock_runner = MagicMock()
    mock_runner.return_value.returncode = 1
    mock_runner.return_value.stdout = ""
    adapter2 = HerdrTargetAdapter(cmd_runner=mock_runner)
    assert adapter2.get_space_id("Roostr") is None

    mock_runner.return_value.returncode = 0
    mock_runner.return_value.stdout = "not json"
    assert adapter2.get_space_id("Roostr") is None

    # 3. get_or_create_space_id fails space.new
    mock_runner.return_value.returncode = 1
    mock_runner.return_value.stdout = json.dumps({"spaces": []})
    mock_runner.return_value.stderr = "Quota exceeded"
    sp_id, err = adapter2.get_or_create_space_id("Roostr", "/tmp")
    assert sp_id is None
    assert "Quota exceeded" in err

    # 4. get_or_create_space_id raises exception
    err_runner2 = MagicMock(side_effect=RuntimeError("Space crash"))
    adapter3 = HerdrTargetAdapter(cmd_runner=err_runner2)
    sp_id, err = adapter3.get_or_create_space_id("Roostr", "/tmp")
    assert sp_id is None
    assert "Space crash" in err

    # 5. launch with non-herdr target
    from roostr.domain.models import TerminalTargetConfig

    herdr_job.target = TerminalTargetConfig()
    ok_runner = MagicMock()
    ok_runner.return_value.returncode = 0
    adapter4 = HerdrTargetAdapter(cmd_runner=ok_runner)
    adapter4.is_running = MagicMock(return_value=True)
    assert adapter4.launch(herdr_job, datetime.now()) == (False, "Job target is not configured for Herdr")

    # 6. launch when get_or_create_space_id fails
    from roostr.domain.models import HerdrTargetConfig

    herdr_job.target = HerdrTargetConfig(space="Roostr")
    adapter4.get_or_create_space_id = MagicMock(return_value=(None, "Space creation error"))
    assert adapter4.launch(herdr_job, datetime.now()) == (False, "Space creation error")

    # 7. launch when hc run fails
    adapter4.get_or_create_space_id = MagicMock(return_value=("sp_123", None))
    fail_hc_res = MagicMock(returncode=1, stderr="hc run failed")
    adapter4._cmd_runner = MagicMock(return_value=fail_hc_res)
    assert adapter4.launch(herdr_job, datetime.now()) == (False, "Failed to execute hc run: hc run failed")

    # 8. launch when hc run raises
    adapter4._cmd_runner = MagicMock(side_effect=RuntimeError("hc crashed"))
    assert "Error spawning hc process" in adapter4.launch(herdr_job, datetime.now())[1]

    # 9. launch with tab rename exception and find_tab_id error
    def multi_runner(cmd, **kwargs):
        res = MagicMock()
        res.returncode = 0
        if cmd == ["hc", "server", "status"]:
            return res
        if "space.select" in cmd or "tab.select" in cmd:
            return res
        if "tab.rename" in cmd:
            raise RuntimeError("tab rename failed")
        if cmd == ["herdr-app", "ls"]:
            res.stdout = json.dumps(
                {
                    "spaces": [
                        {
                            "id": "sp_123",
                            "name": "Roostr",
                            "tabs": [{"id": "tab_456", "terminals": [{"name": "daily-report-20261109-080000"}]}],
                        }
                    ]
                }
            )
            return res
        return res

    adapter5 = HerdrTargetAdapter(cmd_runner=multi_runner, sleep_fn=lambda _: None)
    with patch(
        "roostr.infrastructure.targets.herdr.make_herdr_terminal_name", return_value="daily-report-20261109-080000"
    ):
        ok, msg = adapter5.launch(herdr_job, datetime(2026, 11, 9, 8, 0))
        assert ok is True
        assert "tab_456" in msg

    # 10. find_tab_id_for_terminal returns None when ls throws
    throw_runner = MagicMock(side_effect=RuntimeError("ls error"))
    adapter6 = HerdrTargetAdapter(cmd_runner=throw_runner, sleep_fn=lambda _: None)
    assert adapter6._find_tab_id_for_terminal("term1", retries=1) is None


def test_mac_notifier_adapter():
    from roostr.infrastructure.notifier import MacNotifierAdapter

    cmd_runner = MagicMock()
    notifier = MacNotifierAdapter(cmd_runner=cmd_runner)
    notifier.notify('Title "Quotes"', 'Message "Quotes"')
    assert cmd_runner.call_count == 1
    args = cmd_runner.call_args[0][0]
    assert "osascript" in args
    assert '\\"Quotes\\"' in args[2]

    # Exception handling in notifier
    error_runner = MagicMock(side_effect=RuntimeError("AppleScript error"))
    notifier_err = MacNotifierAdapter(cmd_runner=error_runner)
    # Must not raise
    notifier_err.notify("T", "M")


def test_terminal_target_iterm_ghostty_and_errors(terminal_job, tmp_path):
    from roostr.domain.enums import TerminalApp

    runner_dir = tmp_path / "runners"

    # 1. iTerm2
    terminal_job.target.app = TerminalApp.ITERM2
    cmd_runner = MagicMock()
    cmd_runner.return_value.returncode = 0
    adapter = TerminalTargetAdapter(runners_dir=runner_dir, cmd_runner=cmd_runner)
    success, msg = adapter.launch(terminal_job, datetime(2026, 11, 9, 9, 0))
    assert success is True
    assert "iTerm" in cmd_runner.call_args[0][0][2]

    # 2. Ghostty
    terminal_job.target.app = TerminalApp.GHOSTTY
    cmd_runner.reset_mock()
    success, msg = adapter.launch(terminal_job, datetime(2026, 11, 9, 9, 0))
    assert success is True
    assert "Ghostty" in cmd_runner.call_args[0][0][2]

    # 3. Non-zero returncode error
    cmd_runner.return_value.returncode = 1
    cmd_runner.return_value.stderr = "Permission denied"
    success, msg = adapter.launch(terminal_job, datetime(2026, 11, 9, 9, 0))
    assert success is False
    assert "Permission denied" in msg

    # 4. Exception raised
    cmd_runner.side_effect = RuntimeError("Subprocess exploded")
    success, msg = adapter.launch(terminal_job, datetime(2026, 11, 9, 9, 0))
    assert success is False
    assert "Subprocess exploded" in msg


def test_background_target_exception_handling(background_job, tmp_path):
    error_popen = MagicMock(side_effect=OSError("Fork failed"))
    adapter = BackgroundTargetAdapter(logs_dir=tmp_path / "logs", popen_fn=error_popen)
    success, msg = adapter.launch(background_job, datetime(2026, 11, 9, 9, 0))
    assert success is False
    assert "Failed to dispatch background process" in msg


def test_targets_handle_cwd_with_spaces(tmp_path):
    spaced_cwd = tmp_path / "path with spaces and $pecials"
    job = Job(
        id="spaced-job",
        name="Spaced Job",
        cwd=str(spaced_cwd),
        command="echo hello",
        schedule=SchedulePolicy((0,), time(9, 0)),
        target=TerminalTargetConfig(app=TerminalApp.TERMINAL),
    )

    # 1. Terminal script quotes cwd
    runner_dir = tmp_path / "runners"
    cmd_runner = MagicMock()
    cmd_runner.return_value.returncode = 0
    term_adapter = TerminalTargetAdapter(runners_dir=runner_dir, cmd_runner=cmd_runner)
    script_path = term_adapter.generate_runner_script(job)
    content = script_path.read_text()
    assert "cd 'path with spaces and $pecials'" in content or f"cd '{spaced_cwd}'" in content

    # 2. Background popen quotes cwd
    popen_mock = MagicMock()
    popen_mock.return_value.pid = 9999
    bg_adapter = BackgroundTargetAdapter(logs_dir=tmp_path / "logs", popen_fn=popen_mock)
    success, msg = bg_adapter.launch(job, datetime(2026, 11, 9, 9, 0))
    assert success is True
    call_args = popen_mock.call_args[0][0]
    zsh_cmd = call_args[2]
    assert f"cd '{spaced_cwd}' && echo hello" in zsh_cmd
