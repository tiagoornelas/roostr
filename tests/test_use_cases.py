from datetime import datetime, time
from unittest.mock import MagicMock

import pytest

from roostr.application.use_cases.execute_job import ExecuteJobUseCase
from roostr.application.use_cases.manage_jobs import ManageJobsUseCase
from roostr.domain.enums import ExecutionStatus, TerminalApp, ToleranceMode, TriggerType
from roostr.domain.models import (
    ExecutionRecord,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
)
from roostr.infrastructure.storage import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(tmp_path / "use_case_test.db")


@pytest.fixture
def terminal_job():
    return Job(
        id="review-pr",
        name="Review PR",
        cwd="/path/to/project",
        command="claude '/review'",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),  # Mon-Fri
            time_of_day=time(9, 0),
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=12,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )


def test_execute_job_skips_on_weekend(storage, terminal_job):
    storage.save_job(terminal_job)
    dispatcher_mock = MagicMock()
    notifier_mock = MagicMock()

    use_case = ExecuteJobUseCase(storage=storage, dispatcher=dispatcher_mock, notifier=notifier_mock)

    # 2026-11-08 is Sunday (weekday=6)
    dt = datetime(2026, 11, 8, 9, 30)
    status, msg = use_case.execute("review-pr", now=dt)

    assert status == ExecutionStatus.SKIPPED_OUTSIDE_WINDOW
    assert "weekday" in msg.lower() or "active days" in msg.lower()
    assert dispatcher_mock.dispatch.call_count == 0


def test_execute_job_skips_when_already_succeeded_today(storage, terminal_job):
    storage.save_job(terminal_job)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="review-pr",
            timestamp=datetime(2026, 11, 9, 9, 1),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="Earlier run",
        )
    )

    dispatcher_mock = MagicMock()
    notifier_mock = MagicMock()
    use_case = ExecuteJobUseCase(storage=storage, dispatcher=dispatcher_mock, notifier=notifier_mock)

    dt = datetime(2026, 11, 9, 9, 30)
    status, msg = use_case.execute("review-pr", now=dt)

    assert status == ExecutionStatus.SKIPPED_ALREADY_RAN
    assert dispatcher_mock.dispatch.call_count == 0


def test_execute_job_success(storage, terminal_job):
    storage.save_job(terminal_job)
    dispatcher_mock = MagicMock()
    dispatcher_mock.dispatch.return_value = (True, "Terminal opened")
    notifier_mock = MagicMock()

    use_case = ExecuteJobUseCase(storage=storage, dispatcher=dispatcher_mock, notifier=notifier_mock)

    dt = datetime(2026, 11, 9, 9, 15)
    status, msg = use_case.execute("review-pr", now=dt)

    assert status == ExecutionStatus.SUCCESS
    assert dispatcher_mock.dispatch.call_count == 1
    assert storage.has_succeeded_on_date("review-pr", dt.date()) is True
    assert storage.count_executions("review-pr") == 1


def test_execute_job_force_run_now(storage, terminal_job):
    terminal_job.is_paused = True
    storage.save_job(terminal_job)

    dispatcher_mock = MagicMock()
    dispatcher_mock.dispatch.return_value = (True, "Terminal opened")
    notifier_mock = MagicMock()

    use_case = ExecuteJobUseCase(storage=storage, dispatcher=dispatcher_mock, notifier=notifier_mock)

    # Sunday outside window, paused, but force=True
    dt = datetime(2026, 11, 8, 23, 0)
    status, msg = use_case.execute("review-pr", now=dt, force=True)

    assert status == ExecutionStatus.SUCCESS
    last = storage.get_last_execution("review-pr")
    assert last is not None
    assert last.trigger_type == TriggerType.MANUAL


def test_manage_jobs_lifecycle(storage, terminal_job):
    scheduler_mock = MagicMock()
    use_case = ManageJobsUseCase(storage=storage, scheduler=scheduler_mock)

    use_case.create_job(terminal_job)
    assert storage.get_job("review-pr") is not None
    assert scheduler_mock.install.call_count == 1

    # Toggle pause
    use_case.toggle_pause("review-pr")
    assert storage.get_job("review-pr").is_paused is True
    assert scheduler_mock.pause.call_count == 1

    use_case.toggle_pause("review-pr")
    assert storage.get_job("review-pr").is_paused is False
    assert scheduler_mock.resume.call_count == 1

    # Delete job
    use_case.delete_job("review-pr")
    assert storage.get_job("review-pr") is None
    assert scheduler_mock.uninstall.call_count == 1
