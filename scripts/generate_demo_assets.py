import asyncio
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock

from roostr.domain.enums import (
    AIHarness,
    ExecutionStatus,
    ScheduleFrequency,
    TerminalApp,
    ToleranceMode,
    TriggerType,
)
from roostr.domain.models import (
    AgentAction,
    BackgroundTargetConfig,
    ExecutionRecord,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
)
from roostr.infrastructure.storage import SQLiteStorage
from roostr.ui.app import RoostrApp


def populate_demo_db(storage: SQLiteStorage) -> None:
    # Folders
    storage.save_folder("Factory/Audits")
    storage.save_folder("Factory/Agents")
    storage.save_folder("Maintenance/Ops")

    # 1. Morning PR & Security Audit
    job1 = Job(
        id="morning-pr-audit",
        name="Morning PR & Security Audit",
        cwd="/Users/developer/factory/workspace",
        action=AgentAction(
            harness=AIHarness.ANTIGRAVITY,
            prompt="Audit open PRs, run security scanners, and prepare delivery summaries",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),  # Mon-Fri
            times_of_day=(time(8, 30),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=12,
        ),
        target=HerdrTargetConfig(
            space="Factory",
            tab_template="PR Audit {DD}/{MM}",
        ),
        folder="Factory/Audits",
    )
    storage.save_job(job1)

    # 2. Daily Backlog Triage
    job2 = Job(
        id="backlog-triage",
        name="Daily Backlog Refinement & Triage",
        cwd="/Users/developer/factory/workspace",
        action=AgentAction(
            harness=AIHarness.CLAUDE,
            prompt="Review open issues, tag unlabelled tickets, and flag blockers",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(9, 15),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=HerdrTargetConfig(
            space="Factory",
            tab_template="Triage {DD}/{MM}",
        ),
        folder="Factory/Audits",
    )
    storage.save_job(job2)

    # 3. Flaky Test Sweeper
    job3 = Job(
        id="flaky-test-sweep",
        name="Regression & Flaky Test Sweeper",
        cwd="/Users/developer/factory/services/core",
        action=AgentAction(
            harness=AIHarness.CURSOR,
            prompt="Run quarantine test suite and isolate failures",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(17, 30),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=20,
        ),
        target=HerdrTargetConfig(
            space="CI-Workers",
            tab_template="Tests {DD}/{MM}",
        ),
        folder="Factory/Agents",
    )
    storage.save_job(job3)

    # 4. Dependency Health Check
    job4 = Job(
        id="dependency-health",
        name="Staging Dependency Advisory Scan",
        cwd="/Users/developer/factory/workspace",
        action=AgentAction(
            harness=AIHarness.CODEX,
            prompt="Audit npm, cargo and pip advisories against staging",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(12, 0),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=TerminalTargetConfig(
            app=TerminalApp.GHOSTTY,
            keep_open=True,
        ),
        folder="Factory/Agents",
    )
    storage.save_job(job4)

    # 5. Git Stale Branches Cleanup
    job5 = Job(
        id="git-cleanup",
        name="Workspace Stale Branches Cleanup",
        cwd="/Users/developer/factory/workspace",
        command="git fetch -p && git branch -vv | grep 'gone]' | awk '{print $1}' | xargs git branch -d",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(18, 45),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=TerminalTargetConfig(
            app=TerminalApp.TERMINAL,
            keep_open=False,
        ),
        folder="Maintenance/Ops",
    )
    storage.save_job(job5)

    # 6. Database WAL Checkpoint
    job6 = Job(
        id="db-wal-checkpoint",
        name="Database WAL Checkpoint & Backup",
        cwd="/Users/developer/factory/storage",
        command='sqlite3 factory.db "PRAGMA wal_checkpoint(TRUNCATE);" && cp factory.db backups/',
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
            times_of_day=(time(23, 30),),
            frequency=ScheduleFrequency.DAILY,
        ),
        target=BackgroundTargetConfig(
            notify_on_complete=True,
        ),
        folder="Maintenance/Ops",
        is_paused=True,
    )
    storage.save_job(job6)

    # Add realistic execution history
    today = date.today()
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="morning-pr-audit",
            timestamp=datetime(today.year, today.month, today.day, 8, 30, 42),
            status=ExecutionStatus.SUCCESS,
            details="Dispatched into Herdr space 'Factory' tab 'PR Audit 10/11'",
            trigger_type=TriggerType.SCHEDULED,
        )
    )
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="morning-pr-audit",
            timestamp=datetime(today.year, today.month, max(1, today.day - 1), 8, 30, 14),
            status=ExecutionStatus.SUCCESS,
            details="Completed 4 audits, 0 critical advisories (duration: 4m12s)",
            trigger_type=TriggerType.SCHEDULED,
        )
    )
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="morning-pr-audit",
            timestamp=datetime(today.year, today.month, max(1, today.day - 2), 8, 31, 2),
            status=ExecutionStatus.SUCCESS,
            details="Completed 2 audits (duration: 3m45s)",
            trigger_type=TriggerType.SCHEDULED,
        )
    )


async def generate_assets(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "demo.db"
    if db_path.exists():
        db_path.unlink()

    storage = SQLiteStorage(db_path)
    populate_demo_db(storage)

    daemon_mock = MagicMock()
    daemon_mock.is_running.return_value = True

    # 1. Render Night Theme Dashboard
    app_night = RoostrApp(storage=storage, locale="en", theme="night", daemon_service=daemon_mock)
    async with app_night.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.2)
        pilot.app.dashboard_screen.refresh_jobs("morning-pr-audit")
        await pilot.pause(0.2)
        svg_night = output_dir / "roostr-dashboard-night.svg"
        app_night.save_screenshot(str(svg_night))
        print(f"Generated: {svg_night}")

        # Open New Job Modal to snapshot the creation screen
        await pilot.press("n")
        await pilot.pause(0.3)
        svg_modal = output_dir / "roostr-modal-night.svg"
        app_night.save_screenshot(str(svg_modal))
        print(f"Generated: {svg_modal}")

    # 2. Render Tokyo Night Theme
    app_tokyo = RoostrApp(storage=storage, locale="en", theme="tokyo-night", daemon_service=daemon_mock)
    async with app_tokyo.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.2)
        pilot.app.dashboard_screen.refresh_jobs("morning-pr-audit")
        await pilot.pause(0.2)
        svg_tokyo = output_dir / "roostr-dashboard-tokyo-night.svg"
        app_tokyo.save_screenshot(str(svg_tokyo))
        print(f"Generated: {svg_tokyo}")

    # Clean up demo db
    if db_path.exists():
        db_path.unlink()


if __name__ == "__main__":
    assets_dir = Path(__file__).resolve().parent.parent / "docs" / "assets"
    asyncio.run(generate_assets(assets_dir))
