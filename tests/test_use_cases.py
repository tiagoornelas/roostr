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


def test_manage_jobs_pure_storage_without_scheduler(storage, terminal_job):
    use_case = ManageJobsUseCase(storage=storage)
    use_case.create_job(terminal_job)
    assert storage.get_job("review-pr") is not None

    use_case.toggle_pause("review-pr")
    assert storage.get_job("review-pr").is_paused is True

    use_case.delete_job("review-pr")
    assert storage.get_job("review-pr") is None


def test_execute_job_multi_times_of_day_idempotency(storage):
    job = Job(
        id="multi-exec-test",
        name="Multi Exec Test",
        cwd="/tmp",
        command="echo ok",
        schedule=SchedulePolicy(
            days_of_week=(0,),
            times_of_day=(time(7, 0), time(14, 30)),
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=TerminalTargetConfig(app=TerminalApp.AUTO),
    )
    storage.save_job(job)

    dispatcher_mock = MagicMock()
    dispatcher_mock.dispatch.return_value = (True, "Dispatched")
    notifier_mock = MagicMock()
    use_case = ExecuteJobUseCase(storage=storage, dispatcher=dispatcher_mock, notifier=notifier_mock)

    # 1. Run at 07:00 -> SUCCESS
    status1, _ = use_case.execute("multi-exec-test", now=datetime(2026, 11, 9, 7, 0))
    assert status1 == ExecutionStatus.SUCCESS

    # 2. Run at 07:01 -> SKIPPED_ALREADY_RAN
    status2, _ = use_case.execute("multi-exec-test", now=datetime(2026, 11, 9, 7, 1))
    assert status2 == ExecutionStatus.SKIPPED_ALREADY_RAN

    # 3. Run at 14:30 -> SUCCESS (different slot!)
    status3, _ = use_case.execute("multi-exec-test", now=datetime(2026, 11, 9, 14, 30))
    assert status3 == ExecutionStatus.SUCCESS

    # 4. Run at 14:31 -> SKIPPED_ALREADY_RAN
    status4, _ = use_case.execute("multi-exec-test", now=datetime(2026, 11, 9, 14, 31))
    assert status4 == ExecutionStatus.SKIPPED_ALREADY_RAN


def test_manage_jobs_update_job(storage, terminal_job):
    scheduler_mock = MagicMock()
    use_case = ManageJobsUseCase(storage=storage, scheduler=scheduler_mock)
    use_case.create_job(terminal_job)
    assert scheduler_mock.install.call_count == 1

    # Update job with new name and cwd
    updated_job = Job(
        id=terminal_job.id,
        name="Review PR (Updated)",
        cwd="/new/path",
        command=terminal_job.command,
        schedule=terminal_job.schedule,
        target=terminal_job.target,
        is_paused=False,
        created_at=terminal_job.created_at,
    )
    use_case.update_job(updated_job)

    # Storage should reflect updated attributes
    stored = storage.get_job("review-pr")
    assert stored is not None
    assert stored.name == "Review PR (Updated)"
    assert stored.cwd == "/new/path"
    assert scheduler_mock.install.call_count == 2

    # Update paused job -> should pause scheduler
    updated_job.is_paused = True
    use_case.update_job(updated_job)
    assert scheduler_mock.pause.call_count == 1
    assert scheduler_mock.pause.call_args[0][0] == "review-pr"


def test_execute_job_missing_job(storage):
    use_case = ExecuteJobUseCase(storage=storage)
    status, msg = use_case.execute("non-existent")
    assert status == ExecutionStatus.FAILED
    assert "not found" in msg


def test_execute_job_paused_not_forced(storage, terminal_job):
    terminal_job.is_paused = True
    storage.save_job(terminal_job)
    use_case = ExecuteJobUseCase(storage=storage)
    status, msg = use_case.execute(terminal_job.id, force=False)
    assert status == ExecutionStatus.SKIPPED_ALREADY_RAN
    assert "paused" in msg


def test_execute_job_interval_skips_when_ran_recently(storage):
    from roostr.domain.enums import ScheduleFrequency

    interval_job = Job(
        id="interval-skip",
        name="Interval Skip",
        cwd="/tmp",
        command="echo 1",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
            frequency=ScheduleFrequency.INTERVAL_MINUTES,
            interval_value=30,
        ),
        target=TerminalTargetConfig(),
    )
    storage.save_job(interval_job)
    now = datetime(2026, 11, 9, 10, 0)
    # Recorded execution 5 minutes ago
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=interval_job.id,
            timestamp=datetime(2026, 11, 9, 9, 55),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
        )
    )

    use_case = ExecuteJobUseCase(storage=storage)
    status, msg = use_case.execute(interval_job.id, now=now)
    assert status == ExecutionStatus.SKIPPED_ALREADY_RAN
    assert "Already ran recently" in msg


def test_execute_job_background_notifier_on_failure(storage):
    from roostr.domain.models import BackgroundTargetConfig

    bg_job = Job(
        id="bg-notify",
        name="BG Notify",
        cwd="/tmp",
        command="echo 1",
        schedule=SchedulePolicy((0, 1, 2, 3, 4, 5, 6), time(9, 0)),
        target=BackgroundTargetConfig(notify_on_complete=True),
    )
    storage.save_job(bg_job)
    dispatcher_mock = MagicMock()
    dispatcher_mock.dispatch.return_value = (False, "Command exited with 1")
    notifier_mock = MagicMock()

    use_case = ExecuteJobUseCase(storage=storage, dispatcher=dispatcher_mock, notifier=notifier_mock)
    status, msg = use_case.execute(bg_job.id, now=datetime(2026, 11, 9, 9, 0))
    assert status == ExecutionStatus.FAILED
    assert notifier_mock.notify.call_count == 1
    assert "Roostr — BG Notify" in notifier_mock.notify.call_args[1]["title"] or "Roostr — BG Notify" in str(
        notifier_mock.notify.call_args
    )


def test_manage_jobs_toggle_pause_nonexistent_and_delete_folder(storage):
    use_case = ManageJobsUseCase(storage=storage)
    # Nonexistent job toggle_pause returns False
    assert use_case.toggle_pause("nonexistent") is False

    # Folder operations
    use_case.create_folder("TestFolder")
    assert "TestFolder" in use_case.list_folders()
    use_case.delete_folder("TestFolder")
    assert "TestFolder" not in use_case.list_folders()


def test_execute_job_outside_window_skips(storage, terminal_job):
    # Active day Monday, time 09:00, exact tolerance
    terminal_job.schedule = SchedulePolicy((0,), time(9, 0), tolerance_mode=ToleranceMode.EXACT)
    storage.save_job(terminal_job)
    use_case = ExecuteJobUseCase(storage=storage)
    # Executed Monday at 11:00 -> outside window
    status, msg = use_case.execute(terminal_job.id, now=datetime(2026, 11, 9, 11, 0))
    assert status == ExecutionStatus.SKIPPED_OUTSIDE_WINDOW
    assert "Outside of scheduled window" in msg


def test_execute_job_interval_hours_skips_when_ran_recently(storage):
    from roostr.domain.enums import ScheduleFrequency

    interval_job = Job(
        id="interval-hours-skip",
        name="Interval Hours Skip",
        cwd="/tmp",
        command="echo 1",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
            frequency=ScheduleFrequency.INTERVAL_HOURS,
            interval_value=2,
        ),
        target=TerminalTargetConfig(),
    )
    storage.save_job(interval_job)
    now = datetime(2026, 11, 9, 10, 0)
    # Ran 30 minutes ago
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=interval_job.id,
            timestamp=datetime(2026, 11, 9, 9, 30),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
        )
    )

    use_case = ExecuteJobUseCase(storage=storage)
    status, msg = use_case.execute(interval_job.id, now=now)
    assert status == ExecutionStatus.SKIPPED_ALREADY_RAN
    assert "Already ran recently" in msg
