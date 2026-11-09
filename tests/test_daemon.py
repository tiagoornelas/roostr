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


def test_is_job_due_daily_multiple_times(storage):
    job = Job(
        id="multi-job",
        name="Multi Job",
        cwd="/tmp",
        command="echo multi",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(7, 0), time(14, 30)),
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )
    storage.save_job(job)
    exec_mock = MagicMock()
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # Monday 07:00 -> due
    dt_morning = datetime(2026, 11, 9, 7, 0)
    assert daemon.is_job_due(job, dt_morning) is True

    # Record success for morning slot
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="multi-job",
            timestamp=dt_morning,
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="Done morning",
        )
    )

    # 07:01 -> not due (already ran in morning window)
    assert daemon.is_job_due(job, datetime(2026, 11, 9, 7, 1)) is False

    # 14:30 -> due for afternoon slot!
    dt_afternoon = datetime(2026, 11, 9, 14, 30)
    assert daemon.is_job_due(job, dt_afternoon) is True


def test_is_job_due_interval_window_bounds(storage):
    job = Job(
        id="interval-window-job",
        name="Interval Window Job",
        cwd="/tmp",
        command="echo win",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            frequency=ScheduleFrequency.INTERVAL_MINUTES,
            interval_value=30,
            start_time=time(9, 0),
            end_time=time(17, 0),
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )
    storage.save_job(job)
    exec_mock = MagicMock()
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_mock)

    # Before start_time (08:30) -> not due
    assert daemon.is_job_due(job, datetime(2026, 11, 9, 8, 30)) is False

    # At start_time (09:00) -> due
    assert daemon.is_job_due(job, datetime(2026, 11, 9, 9, 0)) is True

    # After end_time (17:05) -> not due
    assert daemon.is_job_due(job, datetime(2026, 11, 9, 17, 5)) is False
