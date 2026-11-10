from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from roostr.cli import main
from roostr.domain.enums import ExecutionStatus


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Wake up your local AI coding agents on schedule" in result.output
    assert "--locale" in result.output
    assert "--theme" in result.output


def test_cli_run_help():
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output


def test_cli_run_non_existent_job(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    result = runner.invoke(main, ["--db", str(db_file), "run", "fake-job"])
    assert result.exit_code == 1
    assert "[failed]" in result.output
    assert "not found" in result.output


def test_cli_run_success(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    with patch("roostr.cli.ExecuteJobUseCase") as mock_use_case_cls:
        mock_instance = MagicMock()
        mock_instance.execute.return_value = (ExecutionStatus.SUCCESS, "Executed successfully")
        mock_use_case_cls.return_value = mock_instance

        result = runner.invoke(main, ["--db", str(db_file), "run", "test-job", "--force"])
        assert result.exit_code == 0
        assert "[success] Executed successfully" in result.output
        mock_instance.execute.assert_called_once_with("test-job", force=True)


def test_cli_run_skipped_already_ran(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    with patch("roostr.cli.ExecuteJobUseCase") as mock_use_case_cls:
        mock_instance = MagicMock()
        mock_instance.execute.return_value = (ExecutionStatus.SKIPPED_ALREADY_RAN, "Already ran today")
        mock_use_case_cls.return_value = mock_instance

        result = runner.invoke(main, ["--db", str(db_file), "run", "test-job"])
        assert result.exit_code == 0
        assert "[skipped_already_ran] Already ran today" in result.output


def test_cli_run_failure(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    with patch("roostr.cli.ExecuteJobUseCase") as mock_use_case_cls:
        mock_instance = MagicMock()
        mock_instance.execute.return_value = (ExecutionStatus.FAILED, "Command crashed")
        mock_use_case_cls.return_value = mock_instance

        result = runner.invoke(main, ["run", "test-job", "--db", str(db_file)])
        assert result.exit_code == 1
        assert "[failed] Command crashed" in result.output


def test_cli_setup_herdr():
    runner = CliRunner()
    result = runner.invoke(main, ["setup-herdr"])
    assert result.exit_code == 0
    assert "Herdr App" in result.output


def test_cli_daemon_commands(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    # daemon tick
    result = runner.invoke(main, ["--db", str(db_file), "daemon", "tick"])
    assert result.exit_code == 0
    assert "Tick complete: No jobs due." in result.output

    # daemon status
    with patch("roostr.infrastructure.launchd.LaunchdServiceAdapter.is_running", return_value=True):
        res = runner.invoke(main, ["daemon", "status"])
        assert res.exit_code == 0
        assert "Roostr daemon is running" in res.output

    with patch("roostr.infrastructure.launchd.LaunchdServiceAdapter.is_running", return_value=False):
        res = runner.invoke(main, ["daemon", "status"])
        assert res.exit_code == 0
        assert "Roostr daemon is stopped" in res.output

    # daemon install and uninstall
    with patch("roostr.infrastructure.launchd.LaunchdServiceAdapter.install") as mock_install:
        mock_install.return_value = tmp_path / "daemon.plist"
        res = runner.invoke(main, ["daemon", "install"])
        assert res.exit_code == 0
        assert "installed and loaded" in res.output

    with patch("roostr.infrastructure.launchd.LaunchdServiceAdapter.uninstall"):
        res = runner.invoke(main, ["daemon", "uninstall"])
        assert res.exit_code == 0
        assert "unloaded and uninstalled" in res.output


def test_cli_main_launches_app(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    with patch("roostr.ui.app.RoostrApp.run") as mock_run:
        res = runner.invoke(main, ["--db", str(db_file), "--locale", "pt_br", "--theme", "morning"])
        assert res.exit_code == 0
        assert mock_run.call_count == 1


def test_cli_setup_herdr_registered_success():
    runner = CliRunner()
    with patch("roostr.infrastructure.targets.herdr.register_herdr_program", return_value=True):
        res = runner.invoke(main, ["setup-herdr"])
        assert res.exit_code == 0
        assert "Successfully registered Roostr" in res.output


def test_cli_daemon_run_and_interrupt(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    # Normal run
    with patch("roostr.application.use_cases.daemon.DaemonSchedulerUseCase.run_forever") as mock_rf:
        res = runner.invoke(main, ["--db", str(db_file), "daemon", "run", "--interval", "10"])
        assert res.exit_code == 0
        assert "Starting Roostr daemon (poll interval: 10s)..." in res.output
        mock_rf.assert_called_once_with(poll_interval_seconds=10)

    # KeyboardInterrupt
    with patch("roostr.application.use_cases.daemon.DaemonSchedulerUseCase.run_forever", side_effect=KeyboardInterrupt):
        res = runner.invoke(main, ["--db", str(db_file), "daemon", "run"])
        assert res.exit_code == 0
        assert "Roostr daemon stopped" in res.output


def test_cli_daemon_tick_with_executed_jobs(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"
    with patch("roostr.application.use_cases.daemon.DaemonSchedulerUseCase.tick") as mock_tick:
        mock_tick.return_value = [("job1", ExecutionStatus.SUCCESS, "Launched")]
        res = runner.invoke(main, ["--db", str(db_file), "daemon", "tick"])
        assert res.exit_code == 0
        assert "Tick complete: Executed 1 job(s):" in res.output
        assert "[job1] success: Launched" in res.output


def test_cli_daemon_install_and_uninstall_failures():
    runner = CliRunner()
    with patch(
        "roostr.infrastructure.launchd.LaunchdServiceAdapter.install", side_effect=RuntimeError("Permission denied")
    ):
        res = runner.invoke(main, ["daemon", "install"])
        assert res.exit_code == 1
        assert "Failed to install Roostr daemon" in res.output

    with patch(
        "roostr.infrastructure.launchd.LaunchdServiceAdapter.uninstall", side_effect=RuntimeError("Permission denied")
    ):
        res = runner.invoke(main, ["daemon", "uninstall"])
        assert res.exit_code == 1
        assert "Failed to uninstall Roostr daemon" in res.output


def test_main_entrypoint(monkeypatch):
    import runpy

    import pytest

    with patch("roostr.cli.main") as mock_main:
        runpy.run_module("roostr.__main__", run_name="__main__")
        assert mock_main.call_count == 1

    monkeypatch.setattr("sys.argv", ["roostr", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("roostr.cli", run_name="__main__")
    assert exc.value.code == 0


def test_cli_default_db_and_storage(tmp_path, monkeypatch):
    from roostr.cli import get_default_db_path, get_default_storage

    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = get_default_db_path()
    assert "roostr.db" in str(db_path)
    storage = get_default_storage()
    assert storage is not None


def test_cli_setup_herdr_failure():
    runner = CliRunner()
    with patch("roostr.infrastructure.targets.herdr.register_herdr_program", return_value=False):
        res = runner.invoke(main, ["setup-herdr"])
        assert res.exit_code == 0
        assert "Herdr App not found" in res.output
