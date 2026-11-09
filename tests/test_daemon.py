from datetime import datetime, time
from unittest.mock import MagicMock

import pytest

from roostr.application.use_cases.daemon import DaemonSchedulerUseCase
from roostr.domain.enums import (
    ExecutionStatus,
    ScheduleFrequency,
    TerminalApp,
    ToleranceMode,
    TriggerType,
)
from roostr.domain.models import (
    ExecutionRecord,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
)
from roostr.infrastructure.storage import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(tmp_path / "test_daemon.db")


@pytest.fixture
def daily_job():
    return Job(
        id="daily-job",
        name="Daily Job",
        cwd="/tmp",
        command="echo daily",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),  # Mon-Fri
            time_of_day=time(9, 0),
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=12,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )


@pytest.fixture
def interval_job():
    return Job(
        id="interval-job",
        name="Interval Job",
        cwd="/tmp",
        command="echo interval",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
            frequency=ScheduleFrequency.INTERVAL_MINUTES,
            interval_value=30,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )


def test_is_job_due_paused(storage, daily_job):
    daily_job.is_paused = True
    storage.save_job(daily_job)
    exec_mock = MagicMock()
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # Monday 09:15
    dt = datetime(2026, 11, 9, 9, 15)
    assert daemon.is_job_due(daily_job, dt) is False


def test_is_job_due_outside_weekday(storage, daily_job):
    storage.save_job(daily_job)
    exec_mock = MagicMock()
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # Sunday 09:15 (weekday 6)
    dt = datetime(2026, 11, 8, 9, 15)
    assert daemon.is_job_due(daily_job, dt) is False


def test_is_job_due_outside_tolerance_window(storage, daily_job):
    storage.save_job(daily_job)
    exec_mock = MagicMock()
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # Monday 08:30 (before 09:00)
    dt = datetime(2026, 11, 9, 8, 30)
    assert daemon.is_job_due(daily_job, dt) is False

    # Monday 12:01 (after 12:00)
    dt = datetime(2026, 11, 9, 12, 1)
    assert daemon.is_job_due(daily_job, dt) is False


def test_is_job_due_daily_already_succeeded_today(storage, daily_job):
    storage.save_job(daily_job)
    exec_mock = MagicMock()
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # Monday 09:30
    dt = datetime(2026, 11, 9, 9, 30)
    assert daemon.is_job_due(daily_job, dt) is True

    # Record success today
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="daily-job",
            timestamp=datetime(2026, 11, 9, 9, 5),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="Done",
        )
    )

    # Now should not be due
    assert daemon.is_job_due(daily_job, dt) is False


def test_is_job_due_interval(storage, interval_job):
    storage.save_job(interval_job)
    exec_mock = MagicMock()
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # No executions yet -> due
    dt = datetime(2026, 11, 9, 10, 0)
    assert daemon.is_job_due(interval_job, dt) is True

    # Record execution at 10:00
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="interval-job",
            timestamp=dt,
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="Done",
        )
    )

    # At 10:15 (only 15m passed, threshold 30m) -> not due
    assert daemon.is_job_due(interval_job, datetime(2026, 11, 9, 10, 15)) is False

    # At 10:30 (30m passed) -> due
    assert daemon.is_job_due(interval_job, datetime(2026, 11, 9, 10, 30)) is True


def test_daemon_tick_executes_due_jobs(storage, daily_job, interval_job):
    storage.save_job(daily_job)
    storage.save_job(interval_job)

    exec_mock = MagicMock()
    exec_mock.execute.return_value = (ExecutionStatus.SUCCESS, "Executed")

    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # Monday 09:15 -> both should be due
    dt = datetime(2026, 11, 9, 9, 15)
    results = daemon.tick(dt)

    assert len(results) == 2
    executed_ids = [r[0] for r in results]
    assert "daily-job" in executed_ids
    assert "interval-job" in executed_ids
    assert exec_mock.execute.call_count == 2
