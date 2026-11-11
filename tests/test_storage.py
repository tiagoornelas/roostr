from datetime import date, datetime, time

import pytest

from roostr.domain.enums import ExecutionStatus, TerminalApp, ToleranceMode, TriggerType
from roostr.domain.models import (
    BackgroundTargetConfig,
    ExecutionRecord,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
)
from roostr.infrastructure.storage import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test_roostr.db"
    return SQLiteStorage(db_path)


def test_save_and_retrieve_terminal_job(storage):
    job = Job(
        id="code-review",
        name="Morning Code Review",
        cwd="/path/to/project",
        command="claude '/review'",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            time_of_day=time(9, 0),
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=12,
        ),
        target=TerminalTargetConfig(app=TerminalApp.GHOSTTY, keep_open=True),
    )
    storage.save_job(job)

    fetched = storage.get_job("code-review")
    assert fetched is not None
    assert fetched.id == "code-review"
    assert fetched.name == "Morning Code Review"
    assert isinstance(fetched.target, TerminalTargetConfig)
    assert fetched.target.app == TerminalApp.GHOSTTY
    assert fetched.target.keep_open is True


def test_save_and_retrieve_herdr_job(storage):
    job = Job(
        id="daily-report",
        name="Daily Report",
        cwd="/path/to/voga",
        command="claude '/daily-report'",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            time_of_day=time(8, 0),
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=12,
        ),
        target=HerdrTargetConfig(space="Roostr", tab_template="Daily {DD}/{MM}"),
    )
    storage.save_job(job)

    fetched = storage.get_job("daily-report")
    assert fetched is not None
    assert isinstance(fetched.target, HerdrTargetConfig)
    assert fetched.target.space == "Roostr"
    assert fetched.target.tab_template == "Daily {DD}/{MM}"
    assert fetched.target.keep_open is True

    # Job with keep_open=False
    job_no_keep = Job(
        id="no-keep-job",
        name="No Keep Job",
        cwd="/tmp",
        command="claude '/audit'",
        schedule=job.schedule,
        target=HerdrTargetConfig(space="Roostr", tab_template="Audit", keep_open=False),
    )
    storage.save_job(job_no_keep)
    fetched_no_keep = storage.get_job("no-keep-job")
    assert fetched_no_keep is not None
    assert isinstance(fetched_no_keep.target, HerdrTargetConfig)
    assert fetched_no_keep.target.keep_open is False

    # Backward compatibility: JSON dict without keep_open defaults to True
    legacy_target = storage._dict_to_target("herdr", {"space": "OldSpace", "tab_template": "OldTab"})
    assert isinstance(legacy_target, HerdrTargetConfig)
    assert legacy_target.keep_open is True


def test_save_and_retrieve_agent_action_job(storage):
    from roostr.domain.enums import ActionType, AIHarness
    from roostr.domain.models import AgentAction

    multiline_prompt = "Line 1: Search repo\nLine 2: 'quoted' instruction"
    job = Job(
        id="agent-job",
        name="Agent Job",
        cwd="/tmp",
        schedule=SchedulePolicy(
            days_of_week=(0, 1),
            time_of_day=time(9, 30),
            tolerance_mode=ToleranceMode.EXACT,
            tolerance_value=0,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
        action=AgentAction(harness=AIHarness.CLAUDE, prompt=multiline_prompt),
    )
    storage.save_job(job)

    fetched = storage.get_job("agent-job")
    assert fetched is not None
    assert fetched.action.action_type == ActionType.AGENT
    assert isinstance(fetched.action, AgentAction)
    assert fetched.action.harness == AIHarness.CLAUDE
    import shlex

    assert fetched.action.prompt == multiline_prompt
    assert f"claude {shlex.quote(multiline_prompt)}" == fetched.command


def test_record_execution_and_idempotency(storage):
    job = Job(
        id="job1",
        name="Job 1",
        cwd="/tmp",
        command="echo hi",
        schedule=SchedulePolicy((0,), time(10, 0)),
        target=BackgroundTargetConfig(),
    )
    storage.save_job(job)

    record = ExecutionRecord(
        id=None,
        job_id="job1",
        timestamp=datetime(2026, 11, 9, 10, 1),
        trigger_type=TriggerType.SCHEDULED,
        status=ExecutionStatus.SUCCESS,
        details="Done",
    )
    storage.record_execution(record)

    assert storage.count_executions("job1") == 1
    assert storage.has_succeeded_on_date("job1", date(2026, 11, 9)) is True
    assert storage.has_succeeded_on_date("job1", date(2026, 11, 10)) is False


def test_save_and_retrieve_job_with_folder(storage):
    job = Job(
        id="folder-job",
        name="Folder Job",
        cwd="/tmp",
        command="echo folder",
        schedule=SchedulePolicy((0,), time(10, 0)),
        target=BackgroundTargetConfig(),
        folder="Engineering/Backend",
    )
    storage.save_job(job)

    fetched = storage.get_job("folder-job")
    assert fetched is not None
    assert fetched.folder == "Engineering/Backend"
    assert fetched.root_folder == "Engineering"
    assert fetched.subfolder == "Backend"


def test_storage_folder_operations(storage):
    # Save folder
    storage.save_folder("Finance")
    storage.save_folder("Finance/Q4")
    folders = storage.list_folders()
    assert "Finance" in folders
    assert "Finance/Q4" in folders

    # Move job to folder
    job = Job(
        id="report-q4",
        name="Q4 Report",
        cwd="/tmp",
        command="echo q4",
        schedule=SchedulePolicy((0,), time(10, 0)),
        target=BackgroundTargetConfig(),
        folder=None,
    )
    storage.save_job(job)
    assert storage.get_job("report-q4").folder is None

    storage.move_job("report-q4", "Finance/Q4")
    assert storage.get_job("report-q4").folder == "Finance/Q4"

    # Cannot delete folder that contains jobs
    with pytest.raises(ValueError, match="contains 1 job"):
        storage.delete_folder("Finance")

    # Move job back to root
    storage.move_job("report-q4", None)
    assert storage.get_job("report-q4").folder is None

    # Now folder can be deleted
    storage.delete_folder("Finance/Q4")
    assert "Finance/Q4" not in storage.list_folders()
    storage.delete_folder("Finance")
    assert "Finance" not in storage.list_folders()


def test_storage_rename_folder(storage):
    storage.save_folder("Engineering")
    storage.save_folder("Engineering/Backend")
    storage.save_folder("Engineering/Frontend")

    job_be = Job(
        id="job-be",
        name="BE Job",
        cwd="/tmp",
        command="echo be",
        schedule=SchedulePolicy((0,), time(10, 0)),
        target=BackgroundTargetConfig(),
        folder="Engineering/Backend",
    )
    job_fe = Job(
        id="job-fe",
        name="FE Job",
        cwd="/tmp",
        command="echo fe",
        schedule=SchedulePolicy((0,), time(10, 0)),
        target=BackgroundTargetConfig(),
        folder="Engineering/Frontend",
    )
    job_root = Job(
        id="job-root",
        name="Root Job",
        cwd="/tmp",
        command="echo root",
        schedule=SchedulePolicy((0,), time(10, 0)),
        target=BackgroundTargetConfig(),
        folder="Engineering",
    )
    storage.save_job(job_be)
    storage.save_job(job_fe)
    storage.save_job(job_root)

    # 1. Rename root folder cascades to subfolders and all jobs
    storage.rename_folder("Engineering", "Tech")
    folders = storage.list_folders()
    assert "Tech" in folders
    assert "Tech/Backend" in folders
    assert "Tech/Frontend" in folders
    assert "Engineering" not in folders
    assert "Engineering/Backend" not in folders

    assert storage.get_job("job-root").folder == "Tech"
    assert storage.get_job("job-be").folder == "Tech/Backend"
    assert storage.get_job("job-fe").folder == "Tech/Frontend"

    # 2. Rename subfolder updates its jobs
    storage.rename_folder("Tech/Backend", "Tech/API")
    assert "Tech/API" in storage.list_folders()
    assert "Tech/Backend" not in storage.list_folders()
    assert storage.get_job("job-be").folder == "Tech/API"

    # 3. Rename with identical name is no-op
    assert storage.rename_folder("Tech", "Tech") == "Tech"

    # 4. Validations
    with pytest.raises(ValueError, match="Folder name cannot be empty"):
        storage.rename_folder("Tech", "   ")

    with pytest.raises(ValueError, match="cannot exceed 2 levels"):
        storage.rename_folder("Tech", "A/B/C")

    with pytest.raises(ValueError, match="not found"):
        storage.rename_folder("NonExistent", "NewName")

    with pytest.raises(ValueError, match="already exists"):
        storage.rename_folder("Tech/Frontend", "Tech/API")

    with pytest.raises(ValueError, match="Cannot move a folder with subfolders"):
        storage.rename_folder("Tech", "Parent/Tech")


def test_storage_delete_folder_force_and_cascade(storage):
    storage.save_folder("Work")
    storage.save_folder("Work/Tasks")

    job = Job(
        id="task-1",
        name="Task 1",
        cwd="/tmp",
        command="echo 1",
        schedule=SchedulePolicy((0,), time(10, 0)),
        target=BackgroundTargetConfig(),
        folder="Work/Tasks",
    )
    storage.save_job(job)

    # Force delete moves jobs to ungrouped/root (folder=None)
    storage.delete_folder("Work/Tasks", force=True, delete_jobs=False)
    assert "Work/Tasks" not in storage.list_folders()
    updated_job = storage.get_job("task-1")
    assert updated_job is not None
    assert updated_job.folder is None

    # Cascade delete deletes folder and jobs
    storage.move_job("task-1", "Work")
    assert storage.get_job("task-1").folder == "Work"

    storage.delete_folder("Work", force=True, delete_jobs=True)
    assert "Work" not in storage.list_folders()
    assert storage.get_job("task-1") is None


def test_storage_settings(storage):
    assert storage.get_setting("theme") is None
    assert storage.get_setting("theme", "night") == "night"

    storage.set_setting("theme", "tokyo-night")
    assert storage.get_setting("theme") == "tokyo-night"

    storage.set_setting("locale", "pt_br")
    assert storage.get_setting("locale") == "pt_br"

    # Update existing
    storage.set_setting("theme", "nord")
    assert storage.get_setting("theme") == "nord"


def test_storage_save_and_retrieve_interval_job(storage):
    from roostr.domain.enums import ScheduleFrequency

    job = Job(
        id="interval-test",
        name="Interval Test",
        cwd="/tmp",
        command="echo interval",
        schedule=SchedulePolicy(
            days_of_week=(0, 2, 4),
            frequency=ScheduleFrequency.INTERVAL_MINUTES,
            interval_value=45,
        ),
        target=BackgroundTargetConfig(),
    )
    storage.save_job(job)

    fetched = storage.get_job("interval-test")
    assert fetched is not None
    assert fetched.schedule.frequency == ScheduleFrequency.INTERVAL_MINUTES
    assert fetched.schedule.interval_value == 45
    assert fetched.schedule.days_of_week == (0, 2, 4)


def test_storage_save_and_retrieve_multiple_times(storage):
    job = Job(
        id="multi-times-test",
        name="Multi Times Test",
        cwd="/tmp",
        command="echo multi",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(7, 0), time(9, 30), time(14, 30), time(18, 0)),
        ),
        target=HerdrTargetConfig(space="Roostr"),
    )
    storage.save_job(job)

    fetched = storage.get_job("multi-times-test")
    assert fetched is not None
    assert fetched.schedule.times_of_day == (time(7, 0), time(9, 30), time(14, 30), time(18, 0))
    assert fetched.schedule.time_of_day == time(7, 0)


def test_storage_save_and_retrieve_interval_window(storage):
    from roostr.domain.enums import ScheduleFrequency

    job = Job(
        id="window-test",
        name="Window Test",
        cwd="/tmp",
        command="echo window",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            frequency=ScheduleFrequency.INTERVAL_HOURS,
            interval_value=2,
            start_time=time(8, 30),
            end_time=time(17, 30),
        ),
        target=HerdrTargetConfig(space="Roostr"),
    )
    storage.save_job(job)

    fetched = storage.get_job("window-test")
    assert fetched is not None
    assert fetched.schedule.start_time == time(8, 30)
    assert fetched.schedule.end_time == time(17, 30)


def test_storage_folder_validations_and_errors(storage):
    # Empty folder
    with pytest.raises(ValueError, match="Folder name cannot be empty"):
        storage.save_folder("   ")

    # Exceeding 2 levels
    with pytest.raises(ValueError, match="cannot exceed 2 levels"):
        storage.save_folder("Level1/Level2/Level3")

    # Deleting folder that contains jobs
    job = Job(
        id="job-in-folder",
        name="Job in folder",
        cwd="/tmp",
        command="echo 1",
        schedule=SchedulePolicy((0,), time(9, 0)),
        folder="NotEmpty",
    )
    storage.save_job(job)
    with pytest.raises(ValueError, match="contains 1 job"):
        storage.delete_folder("NotEmpty")


def test_storage_schema_migration_from_legacy_db(tmp_path):
    import sqlite3

    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cwd TEXT NOT NULL DEFAULT '',
                command TEXT NOT NULL,
                days_of_week TEXT NOT NULL DEFAULT '[0,1,2,3,4]',
                time_of_day TEXT NOT NULL DEFAULT '08:00',
                tolerance_mode TEXT NOT NULL DEFAULT 'exact',
                tolerance_value INTEGER NOT NULL DEFAULT 0,
                target_type TEXT NOT NULL DEFAULT 'terminal',
                target_config TEXT NOT NULL DEFAULT '{}',
                is_paused INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '2026-11-09T10:00:00',
                updated_at TEXT NOT NULL DEFAULT '2026-11-09T10:00:00'
            )
            """
        )
        conn.execute("INSERT INTO jobs (id, name, command) VALUES ('old-job', 'Old Job', 'echo legacy')")

    # Initializing SQLiteStorage triggers migrations for all 8 missing columns
    repo = SQLiteStorage(db_path)
    job = repo.get_job("old-job")
    assert job is not None
    assert job.command == "echo legacy"


def test_storage_target_dict_fallback(storage):
    from unittest.mock import patch

    # Dummy object that is not Terminal, Herdr, or Background target config
    dummy = "not-a-target"
    assert storage._target_to_dict(dummy) == {}

    # Unknown target type fallback to default
    with patch("roostr.infrastructure.storage.TargetType", return_value="other"):
        fallback = storage._dict_to_target("other", {})
        assert isinstance(fallback, TerminalTargetConfig)
