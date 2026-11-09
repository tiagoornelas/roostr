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
