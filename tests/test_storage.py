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
        sentinel_pattern="reports/{YYYY}/{MM}/{YYYY-MM-DD}-daily.md",
    )
    storage.save_job(job)

    fetched = storage.get_job("daily-report")
    assert fetched is not None
    assert isinstance(fetched.target, HerdrTargetConfig)
    assert fetched.target.space == "Roostr"
    assert fetched.target.tab_template == "Daily {DD}/{MM}"
    assert fetched.sentinel_pattern == "reports/{YYYY}/{MM}/{YYYY-MM-DD}-daily.md"


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
