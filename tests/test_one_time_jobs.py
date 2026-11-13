import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from roostr.application.use_cases.daemon import DaemonSchedulerUseCase, calculate_next_job_run
from roostr.application.use_cases.execute_job import ExecuteJobUseCase
from roostr.application.use_cases.manage_jobs import ManageJobsUseCase
from roostr.cli import main as cli_main
from roostr.domain.enums import (
    ExecutionStatus,
    ScheduleFrequency,
    ToleranceMode,
    TriggerType,
)
from roostr.domain.models import (
    BackgroundTargetConfig,
    CommandAction,
    ExecutionRecord,
    Job,
    SchedulePolicy,
)
from roostr.infrastructure.launchd import LaunchdSchedulerAdapter
from roostr.infrastructure.storage import SQLiteStorage
from roostr.ui.app import RoostrApp
from roostr.ui.screens.dashboard import JobListItem, OneTimeSectionHeaderItem


def _make_once_job(
    job_id: str = "once-job",
    name: str = "Once Job",
    run_at: datetime | None = None,
    tolerance_mode: ToleranceMode = ToleranceMode.WINDOW_HOURS,
    tolerance_value: int = 2,
    is_paused: bool = False,
) -> Job:
    target_dt = run_at or datetime(2026, 11, 15, 14, 30)
    return Job(
        id=job_id,
        name=name,
        cwd="/tmp",
        schedule=SchedulePolicy(
            frequency=ScheduleFrequency.ONCE,
            run_at=target_dt,
            tolerance_mode=tolerance_mode,
            tolerance_value=tolerance_value,
        ),
        target=BackgroundTargetConfig(notify_on_complete=False),
        action=CommandAction(command="echo once"),
        is_paused=is_paused,
    )


def test_schedule_policy_once_requires_run_at():
    with pytest.raises(ValueError, match="run_at is required"):
        SchedulePolicy(frequency=ScheduleFrequency.ONCE)


def test_schedule_policy_once_windows():
    target = datetime(2026, 11, 15, 22, 0)

    exact = SchedulePolicy(frequency=ScheduleFrequency.ONCE, run_at=target, tolerance_mode=ToleranceMode.EXACT)
    assert exact.is_within_window(datetime(2026, 11, 15, 22, 1))
    assert not exact.is_within_window(datetime(2026, 11, 15, 22, 5))

    win = SchedulePolicy(
        frequency=ScheduleFrequency.ONCE, run_at=target, tolerance_mode=ToleranceMode.WINDOW_HOURS, tolerance_value=3
    )
    assert win.is_within_window(datetime(2026, 11, 16, 0, 30))
    assert not win.is_within_window(datetime(2026, 11, 16, 1, 0))

    until_eod = SchedulePolicy(
        frequency=ScheduleFrequency.ONCE,
        run_at=datetime(2026, 11, 15, 10, 0),
        tolerance_mode=ToleranceMode.UNTIL_HOUR,
        tolerance_value=24,
    )
    assert until_eod.is_within_window(datetime(2026, 11, 15, 23, 59))
    assert not until_eod.is_within_window(datetime(2026, 11, 16, 0, 0))


def test_storage_persists_run_at_and_terminal_execution(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "test.db")
    target = datetime(2026, 11, 15, 14, 30)
    job = _make_once_job(run_at=target)
    storage.save_job(job)

    loaded = storage.get_job("once-job")
    assert loaded is not None
    assert loaded.schedule.frequency == ScheduleFrequency.ONCE
    assert loaded.schedule.run_at == target
    assert loaded.to_dict()["schedule"]["run_at"] == target.isoformat()

    assert not storage.has_terminal_execution("once-job")
    assert storage.get_executed_job_ids() == set()

    # Non-terminal SKIPPED record does not mark job as executed
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="once-job",
            timestamp=target,
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SKIPPED_OUTSIDE_WINDOW,
            details="skipped",
        )
    )
    assert not storage.has_terminal_execution("once-job")

    # Terminal SUCCESS followed by SKIPPED still counts as terminal
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="once-job",
            timestamp=target + timedelta(minutes=1),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="ok",
        )
    )
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="once-job",
            timestamp=target + timedelta(minutes=2),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SKIPPED_ALREADY_RAN,
            details="skipped",
        )
    )
    assert storage.has_terminal_execution("once-job")
    assert storage.get_executed_job_ids() == {"once-job"}


def test_daemon_and_execute_once_idempotency(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "test.db")
    target = datetime(2026, 11, 15, 14, 30)
    job = _make_once_job(run_at=target)
    storage.save_job(job)

    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = (True, "Dispatched")
    notifier = MagicMock()
    exec_uc = ExecuteJobUseCase(storage=storage, dispatcher=dispatcher, notifier=notifier)
    daemon_uc = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=exec_uc)

    # Before run_at -> not due
    assert not daemon_uc.is_job_due(job, datetime(2026, 11, 15, 14, 0))
    assert calculate_next_job_run(job, datetime(2026, 11, 15, 14, 0), storage) == target + timedelta(seconds=2)

    # At run_at -> due and executes once
    results = daemon_uc.tick(now=datetime(2026, 11, 15, 14, 30))
    assert len(results) == 1
    assert results[0][1] == ExecutionStatus.SUCCESS

    # Subsequent ticks -> never due again, next run is None
    assert not daemon_uc.is_job_due(job, datetime(2026, 11, 15, 14, 31))
    assert calculate_next_job_run(job, datetime(2026, 11, 15, 14, 31), storage) is None
    status, _ = exec_uc.execute("once-job", now=datetime(2026, 11, 15, 14, 35), force=False)
    assert status == ExecutionStatus.SKIPPED_ALREADY_RAN


def test_manage_jobs_clone_preserves_original_and_history(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "test.db")
    uc = ManageJobsUseCase(storage=storage)
    orig = _make_once_job(job_id="release-check", name="Release Check", run_at=datetime(2026, 11, 13, 10, 0))
    uc.create_job(orig)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id=orig.id,
            timestamp=datetime(2026, 11, 13, 10, 0),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="done",
        )
    )

    new_dt = datetime(2026, 11, 16, 9, 0)
    cloned = uc.clone_job(orig.id, run_at=new_dt)
    assert cloned.id != orig.id
    assert cloned.schedule.run_at == new_dt
    assert uc.get_one_time_state(orig) == "executed"
    assert uc.get_one_time_state(cloned) == "scheduled"
    assert storage.count_executions(orig.id) == 1
    assert storage.count_executions(cloned.id) == 0


def test_launchd_plist_for_once_job(tmp_path: Path):
    adapter = LaunchdSchedulerAdapter(agents_dir=tmp_path / "agents", logs_dir=tmp_path / "logs")
    job = _make_once_job(run_at=datetime(2026, 11, 20, 15, 45))
    xml = adapter.generate_plist_xml(job)
    assert "<key>Month</key>" in xml
    assert "<integer>11</integer>" in xml
    assert "<key>Day</key>" in xml
    assert "<integer>20</integer>" in xml
    assert "<key>Hour</key>" in xml
    assert "<integer>15</integer>" in xml
    assert "<key>Minute</key>" in xml
    assert "<integer>45</integer>" in xml


def test_cli_one_time_jobs_parity(tmp_path: Path):
    db_path = tmp_path / "cli.db"
    runner = CliRunner()

    # Create one-time job via --at
    res = runner.invoke(
        cli_main,
        [
            "--db",
            str(db_path),
            "job",
            "create",
            "--name",
            "Deploy Check",
            "--command",
            "echo deploy",
            "--at",
            "2026-11-20 18:00",
            "--target",
            "background",
            "--json",
        ],
    )
    assert res.exit_code == 0, res.output
    created = json.loads(res.output)
    assert created["schedule"]["frequency"] == "once"
    assert created["schedule"]["run_at"].startswith("2026-11-20T18:00")

    # List filtered by --type once --state scheduled
    res_list = runner.invoke(
        cli_main,
        ["--db", str(db_path), "job", "list", "--type", "once", "--state", "scheduled", "--json"],
    )
    assert res_list.exit_code == 0
    items = json.loads(res_list.output)
    assert len(items) == 1
    assert items[0]["one_time_state"] == "scheduled"

    # Update to --frequency once without --at fails cleanly
    res_bad = runner.invoke(
        cli_main,
        ["--db", str(db_path), "job", "create", "--name", "Bad", "--command", "echo x", "--frequency", "once"],
    )
    assert res_bad.exit_code == 1

    # Clone via CLI
    res_clone = runner.invoke(
        cli_main,
        ["--db", str(db_path), "job", "clone", created["id"], "--at", "2026-11-21 09:00", "--json"],
    )
    assert res_clone.exit_code == 0, res_clone.output
    cloned = json.loads(res_clone.output)
    assert cloned["id"] != created["id"]
    assert cloned["schedule"]["run_at"].startswith("2026-11-21T09:00")


@pytest.mark.asyncio
async def test_tui_onetime_tab_separates_scheduled_and_executed(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "tui.db")

    # 1 recurring job
    rec_job = Job(
        id="rec-1",
        name="Daily Audit",
        cwd="/tmp",
        schedule=SchedulePolicy(days_of_week=(0, 1, 2, 3, 4), frequency=ScheduleFrequency.DAILY),
        target=BackgroundTargetConfig(),
        action=CommandAction(command="echo daily"),
    )
    storage.save_job(rec_job)

    # 1 scheduled one-time job and 1 executed one-time job
    ot_sched = _make_once_job(job_id="ot-sched", name="Future One-Time", run_at=datetime(2026, 11, 20, 18, 0))
    ot_exec = _make_once_job(job_id="ot-exec", name="Past One-Time", run_at=datetime(2026, 11, 10, 10, 0))
    storage.save_job(ot_sched)
    storage.save_job(ot_exec)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="ot-exec",
            timestamp=datetime(2026, 11, 10, 10, 0),
            trigger_type=TriggerType.SCHEDULED,
            status=ExecutionStatus.SUCCESS,
            details="ok",
        )
    )

    app = RoostrApp(storage=storage, locale="en")
    async with app.run_test() as pilot:
        await pilot.pause()

        # Default tab is Recurring (only rec-1)
        assert app.dashboard_screen.active_tab == "recurring"
        items_rec = list(app.dashboard_screen.query(JobListItem))
        assert [i.job.id for i in items_rec] == ["rec-1"]

        # Switch to One-Time tab via Tab key
        await pilot.press("tab")
        await pilot.pause()

        assert app.dashboard_screen.active_tab == "onetime"
        headers = list(app.dashboard_screen.query(OneTimeSectionHeaderItem))
        assert [h.section_key for h in headers] == ["scheduled", "executed"]
        assert [h.count for h in headers] == [1, 1]

        items_ot = list(app.dashboard_screen.query(JobListItem))
        assert [i.job.id for i in items_ot] == ["ot-sched", "ot-exec"]
        assert items_ot[0].is_executed is False
        assert items_ot[1].is_executed is True
