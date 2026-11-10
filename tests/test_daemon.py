import asyncio
from datetime import datetime, time
from unittest.mock import MagicMock, patch

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


def test_calculate_next_job_run_daily_future_today(storage, daily_job):
    from roostr.application.use_cases.daemon import calculate_next_job_run

    storage.save_job(daily_job)
    # Monday 08:00 (daily_job is at 09:00)
    now = datetime(2026, 11, 9, 8, 0, 0)  # 2026-11-09 is Monday
    next_run = calculate_next_job_run(daily_job, now, storage)
    assert next_run == datetime(2026, 11, 9, 9, 0, 2)


def test_calculate_next_job_run_daily_already_ran_today(storage, daily_job):
    from roostr.application.use_cases.daemon import calculate_next_job_run

    storage.save_job(daily_job)
    now = datetime(2026, 11, 9, 10, 0, 0)
    # Record success today
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=daily_job.id,
            timestamp=datetime(2026, 11, 9, 9, 0, 1),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
        )
    )
    next_run = calculate_next_job_run(daily_job, now, storage)
    # Tomorrow Tuesday 09:00:02
    assert next_run == datetime(2026, 11, 10, 9, 0, 2)


def test_calculate_next_job_run_daily_failed_in_tolerance(storage, daily_job):
    from roostr.application.use_cases.daemon import calculate_next_job_run

    storage.save_job(daily_job)
    now = datetime(2026, 11, 9, 9, 15, 30)
    # Record failed attempt earlier
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=daily_job.id,
            timestamp=datetime(2026, 11, 9, 9, 0, 1),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.FAILED,
        )
    )
    next_run = calculate_next_job_run(daily_job, now, storage)
    # Next minute boundary: 09:16:02
    assert next_run == datetime(2026, 11, 9, 9, 16, 2)


def test_calculate_next_job_run_weekend_jump(storage, daily_job):
    from roostr.application.use_cases.daemon import calculate_next_job_run

    storage.save_job(daily_job)
    # Friday evening 20:00 (2026-11-13 is Friday)
    now = datetime(2026, 11, 13, 20, 0, 0)
    next_run = calculate_next_job_run(daily_job, now, storage)
    # Next Monday 2026-11-16 09:00:02
    assert next_run == datetime(2026, 11, 16, 9, 0, 2)


def test_calculate_next_job_run_paused(storage, daily_job):
    from roostr.application.use_cases.daemon import calculate_next_job_run

    daily_job.is_paused = True
    storage.save_job(daily_job)
    now = datetime(2026, 11, 9, 8, 0, 0)
    next_run = calculate_next_job_run(daily_job, now, storage)
    assert next_run is None


def test_calculate_next_schedule_event(storage, daily_job):
    from roostr.application.use_cases.daemon import calculate_next_schedule_event

    storage.save_job(daily_job)
    now = datetime(2026, 11, 9, 8, 0, 0)
    next_event = calculate_next_schedule_event([daily_job], now, storage)
    assert next_event == datetime(2026, 11, 9, 9, 0, 2)

    # Empty list falls back to midnight rollover
    next_empty = calculate_next_schedule_event([], now, storage)
    assert next_empty == datetime(2026, 11, 10, 0, 0, 2)


@pytest.mark.asyncio
async def test_daemon_run_forever_async(storage):
    from unittest.mock import patch

    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=MagicMock())

    async def fake_sleep(seconds):
        daemon._running = False

    with patch("asyncio.sleep", side_effect=fake_sleep):
        await daemon.run_forever_async(poll_interval_seconds=1)

    assert daemon._running is False


def test_daemon_run_forever_sync(storage):
    from unittest.mock import AsyncMock, patch

    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=MagicMock())
    with patch.object(daemon, "run_forever_async", new_callable=AsyncMock) as mock_async:
        daemon.run_forever(poll_interval_seconds=1)
        assert mock_async.call_count == 1


def test_is_job_due_interval_hours(storage):
    job = Job(
        id="interval-hours-job",
        name="Interval Hours Job",
        cwd="/tmp",
        command="echo hours",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            frequency=ScheduleFrequency.INTERVAL_HOURS,
            interval_value=2,
        ),
        target=TerminalTargetConfig(),
    )
    storage.save_job(job)
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=MagicMock())

    # No executions yet -> due
    now = datetime(2026, 11, 9, 10, 0)
    assert daemon.is_job_due(job, now) is True

    # Succeeded 30 min ago -> not due
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=job.id,
            timestamp=datetime(2026, 11, 9, 9, 30),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
        )
    )
    assert daemon.is_job_due(job, now) is False

    # Check 2 hours later (11:35) -> due (elapsed > 2h - 30s)
    later = datetime(2026, 11, 9, 11, 35)
    assert daemon.is_job_due(job, later) is True


def test_calculate_next_job_run_interval_and_multi_slot(storage):
    from roostr.application.use_cases.daemon import calculate_next_job_run

    # 1. Interval with start_time & end_time
    job_interval = Job(
        id="job-int-win",
        name="Job Interval Window",
        cwd="/tmp",
        command="echo int",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            frequency=ScheduleFrequency.INTERVAL_HOURS,
            interval_value=2,
            start_time=time(9, 0),
            end_time=time(17, 0),
        ),
        target=TerminalTargetConfig(),
    )
    storage.save_job(job_interval)

    # Before start_time (08:00) -> next run is at start_time 09:00:02
    now_early = datetime(2026, 11, 9, 8, 0)
    nr = calculate_next_job_run(job_interval, now_early, storage)
    assert nr == datetime(2026, 11, 9, 9, 0, 2)

    # After end_time (18:00) -> next run is next day at start_time 09:00:02
    now_late = datetime(2026, 11, 9, 18, 0)
    nr = calculate_next_job_run(job_interval, now_late, storage)
    assert nr == datetime(2026, 11, 10, 9, 0, 2)

    # 2. Multi-slot daily already ran morning slot
    job_multi = Job(
        id="job-multi",
        name="Job Multi Slot",
        cwd="/tmp",
        command="echo multi",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(8, 0), time(14, 0)),
        ),
        target=TerminalTargetConfig(),
    )
    storage.save_job(job_multi)
    # Ran morning slot at 08:00
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=job_multi.id,
            timestamp=datetime(2026, 11, 9, 8, 0, 1),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
        )
    )
    now_midday = datetime(2026, 11, 9, 10, 0)
    nr_multi = calculate_next_job_run(job_multi, now_midday, storage)
    assert nr_multi == datetime(2026, 11, 9, 14, 0, 2)


def test_is_job_due_daily_multi_slot_outside_slots(storage):
    job = Job(
        id="job-multi-outside",
        name="Job Multi Outside",
        cwd="/tmp",
        command="echo 1",
        schedule=SchedulePolicy(
            days_of_week=(0,),
            times_of_day=(time(8, 0), time(14, 0)),
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=TerminalTargetConfig(),
    )
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=MagicMock())
    # Monday at 10:00 -> not in any slot window -> returns False
    assert daemon.is_job_due(job, datetime(2026, 11, 9, 10, 0)) is False


@pytest.mark.asyncio
async def test_daemon_run_forever_async_error_and_cancelled(storage):
    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=MagicMock())

    # 1. tick raises exception -> logged and loop continues then cancels
    calls = 0

    def error_tick(*args):
        nonlocal calls
        calls += 1
        raise RuntimeError("Tick explosion")

    daemon.tick = error_tick

    with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
        await daemon.run_forever_async(poll_interval_seconds=1)

    assert calls == 1


def test_daemon_run_forever_signal_handling(storage):
    import signal

    daemon = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=MagicMock())
    captured_handler = None

    def fake_signal(sig, handler):
        nonlocal captured_handler
        if sig == signal.SIGINT:
            captured_handler = handler

    with patch("signal.signal", side_effect=fake_signal), patch.object(daemon, "run_forever_async"):
        # run run_forever briefly
        daemon._running = True
        daemon.run_forever(poll_interval_seconds=1)
        if captured_handler:
            captured_handler()
        assert daemon._running is False


def test_calculate_next_job_run_edge_cases(storage):
    from roostr.application.use_cases.daemon import calculate_next_job_run

    job = Job(
        id="edge-job",
        name="Edge Job",
        cwd="/tmp",
        command="echo 1",
        schedule=SchedulePolicy(
            days_of_week=(),
            time_of_day=time(8, 0),
        ),
        target=TerminalTargetConfig(),
    )
    # Empty days_of_week -> None
    assert calculate_next_job_run(job, datetime(2026, 11, 9, 8, 0), storage) is None

    # Daily: now is within slot tolerance window, second=0
    job.schedule = SchedulePolicy(
        days_of_week=(0,),
        time_of_day=time(8, 0),
        tolerance_mode=ToleranceMode.UNTIL_HOUR,
        tolerance_value=12,
    )
    now_in_window = datetime(2026, 11, 9, 8, 30, 0)
    nr = calculate_next_job_run(job, now_in_window, storage)
    assert nr is not None
    assert nr.minute == 31

    # Interval: candidate <= now, second=0
    job.schedule = SchedulePolicy(
        days_of_week=(0,),
        frequency=ScheduleFrequency.INTERVAL_MINUTES,
        interval_value=15,
    )
    nr_int = calculate_next_job_run(job, datetime(2026, 11, 9, 10, 0, 0), storage)
    assert nr_int is not None
    assert nr_int.minute == 1
