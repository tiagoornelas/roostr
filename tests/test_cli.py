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

    # Subcommand help
    help_cmd_res = runner.invoke(main, ["help"])
    assert help_cmd_res.exit_code == 0
    assert "job" in help_cmd_res.output

    help_topic_res = runner.invoke(main, ["help", "job"])
    assert help_topic_res.exit_code == 0
    assert "create" in help_topic_res.output


def test_cli_version():
    from roostr import __version__

    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert f"roostr {__version__}" in result.output


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


def test_cli_daemon_commands(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "darwin")
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


def test_cli_daemon_install_and_uninstall_failures(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "darwin")
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


def test_cli_daemon_commands_linux(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    runner = CliRunner()

    with patch("roostr.infrastructure.systemd.SystemdUserServiceAdapter.is_running", return_value=True):
        res = runner.invoke(main, ["daemon", "status"])
        assert res.exit_code == 0
        assert "loaded in systemd" in res.output

    with patch("roostr.infrastructure.systemd.SystemdUserServiceAdapter.install") as mock_install:
        mock_install.return_value = tmp_path / "roostr.service"
        res = runner.invoke(main, ["daemon", "install"])
        assert res.exit_code == 0
        assert "systemd" in res.output

    with patch("roostr.infrastructure.systemd.SystemdUserServiceAdapter.uninstall"):
        res = runner.invoke(main, ["daemon", "uninstall"])
        assert res.exit_code == 0
        assert "unloaded and uninstalled" in res.output

    with patch(
        "roostr.infrastructure.systemd.SystemdUserServiceAdapter.install", side_effect=RuntimeError("Permission denied")
    ):
        res = runner.invoke(main, ["daemon", "install"])
        assert res.exit_code == 1
        assert "Failed to install Roostr daemon" in res.output

    with patch(
        "roostr.infrastructure.systemd.SystemdUserServiceAdapter.uninstall",
        side_effect=RuntimeError("Permission denied"),
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


# ==============================================================================
# Job CLI Tests
# ==============================================================================


def test_cli_job_create_and_show_and_list(tmp_path):
    import json

    runner = CliRunner()
    db_file = tmp_path / "test.db"

    # Create an agent job with --json
    create_res = runner.invoke(
        main,
        [
            "--db",
            str(db_file),
            "job",
            "create",
            "--name",
            "Morning PR Review",
            "--prompt",
            "Review pull requests",
            "--harness",
            "claude",
            "--folder",
            "Work/Daily",
            "--times",
            "08:00,14:00",
            "--json",
        ],
    )
    assert create_res.exit_code == 0
    created_data = json.loads(create_res.output)
    assert created_data["name"] == "Morning PR Review"
    assert created_data["id"] == "morning-pr-review"
    assert created_data["folder"] == "Work/Daily"
    assert created_data["action"]["harness"] == "claude"

    # List jobs (standard format)
    list_res = runner.invoke(main, ["--db", str(db_file), "job", "list"])
    assert list_res.exit_code == 0
    assert "Morning PR Review" in list_res.output
    assert "morning-pr-review" in list_res.output

    # List jobs with --json
    list_json_res = runner.invoke(main, ["--db", str(db_file), "job", "list", "--json"])
    assert list_json_res.exit_code == 0
    jobs_json = json.loads(list_json_res.output)
    assert len(jobs_json) == 1
    assert jobs_json[0]["id"] == "morning-pr-review"

    # Show job with --json
    show_json_res = runner.invoke(main, ["--db", str(db_file), "job", "show", "morning-pr-review", "--json"])
    assert show_json_res.exit_code == 0
    show_data = json.loads(show_json_res.output)
    assert show_data["id"] == "morning-pr-review"
    assert show_data["action"]["prompt"] == "Review pull requests"
    assert show_data["target"]["type"] == "herdr"
    assert show_data["target"]["keep_open"] is True

    # Show job (standard visual format)
    show_res = runner.invoke(main, ["--db", str(db_file), "job", "show", "morning-pr-review"])
    assert show_res.exit_code == 0
    assert "Keep Open:  True" in show_res.output
    assert "Morning PR Review (morning-pr-review)" in show_res.output
    assert "Status:       ACTIVE" in show_res.output


def test_cli_job_create_command_action(tmp_path):
    import json

    runner = CliRunner()
    db_file = tmp_path / "test.db"

    res = runner.invoke(
        main,
        [
            "--db",
            str(db_file),
            "job",
            "create",
            "--name",
            "Build Check",
            "--command",
            "npm test",
            "--target",
            "terminal",
            "--terminal-app",
            "ghostty",
            "--json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["id"] == "build-check"
    assert data["action"]["type"] == "command"
    assert data["target"]["app"] == "ghostty"


def test_cli_job_create_missing_prompt_and_command(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    res = runner.invoke(main, ["--db", str(db_file), "job", "create", "--name", "Incomplete"])
    assert res.exit_code == 1
    assert "Either --prompt or --command is required" in res.output


def test_cli_job_pause_resume_update_delete(tmp_path):
    import json

    runner = CliRunner()
    db_file = tmp_path / "test.db"

    # Create job
    runner.invoke(
        main,
        ["--db", str(db_file), "job", "create", "-n", "Audit", "-p", "Audit code", "-t", "09:00"],
    )

    # Pause
    pause_res = runner.invoke(main, ["--db", str(db_file), "job", "pause", "audit", "--json"])
    assert pause_res.exit_code == 0
    assert json.loads(pause_res.output)["is_paused"] is True

    # Filter list by status
    list_active = runner.invoke(main, ["--db", str(db_file), "job", "list", "--status", "active", "--json"])
    assert len(json.loads(list_active.output)) == 0

    list_paused = runner.invoke(main, ["--db", str(db_file), "job", "list", "--status", "paused", "--json"])
    assert len(json.loads(list_paused.output)) == 1

    # Resume
    resume_res = runner.invoke(main, ["--db", str(db_file), "job", "resume", "audit", "--json"])
    assert resume_res.exit_code == 0
    assert json.loads(resume_res.output)["is_paused"] is False

    # Update
    update_res = runner.invoke(
        main,
        [
            "--db",
            str(db_file),
            "job",
            "update",
            "audit",
            "-n",
            "Security Audit",
            "-p",
            "Audit security",
            "--folder",
            "Security",
            "--no-keep-open",
            "--json",
        ],
    )
    assert update_res.exit_code == 0
    updated_data = json.loads(update_res.output)
    assert updated_data["name"] == "Security Audit"
    assert updated_data["folder"] == "Security"
    assert updated_data["action"]["prompt"] == "Audit security"
    assert updated_data["target"]["keep_open"] is False

    # Delete with --yes and --json
    del_res = runner.invoke(main, ["--db", str(db_file), "job", "delete", "audit", "--yes", "--json"])
    assert del_res.exit_code == 0
    assert json.loads(del_res.output)["deleted"] is True

    # Verify not found
    show_del = runner.invoke(main, ["--db", str(db_file), "job", "show", "audit"])
    assert show_del.exit_code == 1
    assert "not found" in show_del.output


def test_cli_job_run_alias(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    # Create job
    runner.invoke(main, ["--db", str(db_file), "job", "create", "-n", "Quick Job", "-c", "echo hello"])

    with patch("roostr.cli.ExecuteJobUseCase") as mock_use_case_cls:
        mock_instance = MagicMock()
        mock_instance.execute.return_value = (ExecutionStatus.SUCCESS, "Executed")
        mock_use_case_cls.return_value = mock_instance

        res = runner.invoke(main, ["--db", str(db_file), "job", "run", "quick-job", "--json"])
        assert res.exit_code == 0
        assert '"status": "success"' in res.output


def test_cli_run_due_jobs(tmp_path):
    runner = CliRunner()
    db_file = tmp_path / "test.db"

    with patch("roostr.application.use_cases.daemon.DaemonSchedulerUseCase.tick") as mock_tick:
        mock_tick.return_value = [("job-1", ExecutionStatus.SUCCESS, "Done")]
        res = runner.invoke(main, ["--db", str(db_file), "run", "--due", "--json"])
        assert res.exit_code == 0
        assert '"executed_count": 1' in res.output


# ==============================================================================
# Folder and History CLI Tests
# ==============================================================================


def test_cli_folder_lifecycle(tmp_path):
    import json

    runner = CliRunner()
    db_file = tmp_path / "test.db"

    # Create folder
    create_res = runner.invoke(main, ["--db", str(db_file), "folder", "create", "Work/Daily", "--json"])
    assert create_res.exit_code == 0
    assert json.loads(create_res.output)["folder"] == "Work/Daily"

    # List folders
    list_res = runner.invoke(main, ["--db", str(db_file), "folder", "list", "--json"])
    assert list_res.exit_code == 0
    folders = json.loads(list_res.output)
    folder_names = [f["name"] for f in folders]
    assert "Work" in folder_names
    assert "Work/Daily" in folder_names

    # Rename/edit folder with --json
    edit_res = runner.invoke(main, ["--db", str(db_file), "folder", "edit", "Work/Daily", "Work/Morning", "--json"])
    assert edit_res.exit_code == 0
    edit_data = json.loads(edit_res.output)
    assert edit_data["old_name"] == "Work/Daily"
    assert edit_data["new_name"] == "Work/Morning"
    assert edit_data["renamed"] is True

    # Rename alias in standard text mode
    rename_res = runner.invoke(main, ["--db", str(db_file), "folder", "rename", "Work/Morning", "Work/Tasks"])
    assert rename_res.exit_code == 0
    assert "Renamed folder 'Work/Morning' to 'Work/Tasks'" in rename_res.output

    # Edit error when folder not found
    err_res = runner.invoke(main, ["--db", str(db_file), "folder", "edit", "NonExistent", "NewName"])
    assert err_res.exit_code == 1
    assert "Error:" in err_res.output

    # Create job in folder to test non-empty delete
    job_create = runner.invoke(
        main,
        [
            "--db",
            str(db_file),
            "job",
            "create",
            "--name",
            "Test Job",
            "--command",
            "echo 1",
            "--folder",
            "Work/Tasks",
            "--json",
        ],
    )
    assert job_create.exit_code == 0

    # Deleting non-empty folder without flags fails
    del_fail = runner.invoke(main, ["--db", str(db_file), "folder", "delete", "Work/Tasks"])
    assert del_fail.exit_code == 1
    assert "contains 1 job" in del_fail.output

    # Force delete ungroups the job
    del_force = runner.invoke(main, ["--db", str(db_file), "folder", "delete", "Work/Tasks", "--force", "--json"])
    assert del_force.exit_code == 0
    assert json.loads(del_force.output)["deleted"] is True

    # Verify job is now ungrouped
    job_show = runner.invoke(main, ["--db", str(db_file), "job", "show", "test-job", "--json"])
    assert job_show.exit_code == 0
    assert json.loads(job_show.output)["folder"] is None

    # Move job back to Work and test --delete-jobs
    runner.invoke(main, ["--db", str(db_file), "job", "update", "test-job", "--folder", "Work"])
    del_jobs = runner.invoke(main, ["--db", str(db_file), "folder", "delete", "Work", "--delete-jobs", "--json"])
    assert del_jobs.exit_code == 0
    assert json.loads(del_jobs.output)["delete_jobs"] is True

    # Verify job was deleted
    job_show_del = runner.invoke(main, ["--db", str(db_file), "job", "show", "test-job"])
    assert job_show_del.exit_code == 1


def test_cli_history_inspection(tmp_path):
    import json
    from datetime import datetime

    from roostr.domain.enums import TriggerType
    from roostr.domain.models import ExecutionRecord
    from roostr.infrastructure.storage import SQLiteStorage

    runner = CliRunner()
    db_file = tmp_path / "test.db"
    storage = SQLiteStorage(db_file)

    # Empty history
    empty_res = runner.invoke(main, ["--db", str(db_file), "history"])
    assert empty_res.exit_code == 0
    assert "No execution history found" in empty_res.output

    # Create job first so FK constraint is satisfied
    create_job_res = runner.invoke(
        main,
        ["--db", str(db_file), "job", "create", "-n", "Test Job", "-c", "echo 1", "--id", "test-job"],
    )
    assert create_job_res.exit_code == 0

    # Add execution record
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="test-job",
            timestamp=datetime(2026, 11, 11, 8, 30),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="Executed in Herdr",
        )
    )

    # View history with --json
    hist_json = runner.invoke(main, ["--db", str(db_file), "history", "--json"])
    assert hist_json.exit_code == 0
    records = json.loads(hist_json.output)
    assert len(records) == 1
    assert records[0]["job_id"] == "test-job"
    assert records[0]["status"] == "success"

    # View history for specific job
    hist_job = runner.invoke(main, ["--db", str(db_file), "history", "test-job"])
    assert hist_job.exit_code == 0
    assert "test-job" in hist_job.output
