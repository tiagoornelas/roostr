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
