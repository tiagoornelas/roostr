import asyncio
import io
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

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
    ExecutionRecord,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
)
from roostr.infrastructure.storage import SQLiteStorage
from roostr.ui.app import RoostrApp

CLEAN_SVG_FORMAT = """<svg class="rich-terminal" viewBox="0 0 {terminal_width} {terminal_height}" xmlns="http://www.w3.org/2000/svg">
    <!-- Generated with Rich & Textual -->
    <style>

    @font-face {{
        font-family: "Fira Code";
        src: local("FiraCode-Regular"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff2/FiraCode-Regular.woff2") format("woff2"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff/FiraCode-Regular.woff") format("woff");
        font-style: normal;
        font-weight: 400;
    }}
    @font-face {{
        font-family: "Fira Code";
        src: local("FiraCode-Bold"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff2/FiraCode-Bold.woff2") format("woff2"),
                url("https://cdnjs.cloudflare.com/ajax/libs/firacode/6.2.0/woff/FiraCode-Bold.woff") format("woff");
        font-style: bold;
        font-weight: 700;
    }}

    .{unique_id}-matrix {{
        font-family: Fira Code, monospace;
        font-size: {char_height}px;
        line-height: {line_height}px;
        font-variant-east-asian: full-width;
    }}

    {styles}
    </style>

    <defs>
    <clipPath id="{unique_id}-clip-terminal">
      <rect x="0" y="0" width="{terminal_width}" height="{terminal_height}" rx="6" />
    </clipPath>
    {lines}
    </defs>

    <g clip-path="url(#{unique_id}-clip-terminal)">
    {backgrounds}
    <g class="{unique_id}-matrix">
    {matrix}
    </g>
    </g>
</svg>
"""


def export_clean_svg(app: RoostrApp, output_path: Path) -> None:
    width, height = app.size

    console = Console(
        width=width,
        height=height,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        record=True,
        legacy_windows=False,
        safe_box=False,
    )
    screen_render = app.screen._compositor.render_update(
        full=True, screen_stack=app._background_screens, simplify=False
    )
    console.print(screen_render)
    svg_content = console.export_svg(code_format=CLEAN_SVG_FORMAT)
    output_path.write_text(svg_content, encoding="utf-8")


def populate_demo_db(storage: SQLiteStorage) -> None:
    # 3 concise folders representing modern AI software factory workflows
    storage.save_folder("Factory")
    storage.save_folder("Discovery")
    storage.save_folder("Operations")

    # Job 1: Automated Code Review
    job1 = Job(
        id="code-review-ai",
        name="Automated Code Review",
        cwd="/Users/developer/roostr",
        action=AgentAction(
            harness=AIHarness.CLAUDE,
            prompt=(
                "/agentic-code-review\n"
                "1. Audit open PRs for architecture boundaries, test sanity, and DoD rules\n"
                "2. Run project linters and post structured review verdicts with inline fixes"
            ),
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
            tab_template="Code Review {DD}/{MM}",
        ),
        folder="Factory",
    )
    storage.save_job(job1)

    # Job 2: Jira Bugfix Agent
    job2 = Job(
        id="jira-bugfix-agent",
        name="Jira Bugfix Agent",
        cwd="/Users/developer/backend",
        action=AgentAction(
            harness=AIHarness.CURSOR,
            prompt="Fetch assigned Jira bug tickets, reproduce test cases, and create fix branches",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(15, 30),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=19,
        ),
        target=HerdrTargetConfig(
            space="Factory",
            tab_template="Jira Fix {DD}/{MM}",
        ),
        folder="Factory",
    )
    storage.save_job(job2)

    # Job 3: Architecture Improver
    job3 = Job(
        id="arch-improver",
        name="Architecture Improver",
        cwd="/Users/developer/backend",
        action=AgentAction(
            harness=AIHarness.ANTIGRAVITY,
            prompt="Analyze complexity metrics across domain layers and draft structural clean-architecture PRs",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 2),  # Mon, Wed
            times_of_day=(time(7, 0),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=HerdrTargetConfig(
            space="Factory",
            tab_template="Arch Decouple {DD}/{MM}",
        ),
        folder="Factory",
    )
    storage.save_job(job3)

    # Job 4: Support Feature Miner
    job4 = Job(
        id="support-miner",
        name="Support Feature Miner",
        cwd="/Users/developer/product",
        action=AgentAction(
            harness=AIHarness.CLAUDE,
            prompt="Analyze daily support tickets, cluster recurring customer friction, and draft feature proposals with PRD specs",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(18, 0),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.UNTIL_HOUR,
            tolerance_value=21,
        ),
        target=HerdrTargetConfig(
            space="Discovery",
            tab_template="Feature Backlog {DD}/{MM}",
        ),
        folder="Discovery",
    )
    storage.save_job(job4)

    # Job 5: PR Security Audit
    job5 = Job(
        id="sec-audit",
        name="PR Security Audit",
        cwd="/Users/developer/roostr",
        action=AgentAction(
            harness=AIHarness.CODEX,
            prompt="Scan active branches and lockfiles for vulnerabilities and leaked secrets",
        ),
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(10, 0),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=HerdrTargetConfig(
            space="Operations",
            tab_template="Sec Audit {DD}/{MM}",
        ),
        folder="Operations",
    )
    storage.save_job(job5)

    # Job 6: Staging Smoke Tests
    job6 = Job(
        id="staging-smoke",
        name="Staging Smoke Tests",
        cwd="/Users/developer/backend",
        command="pytest tests/e2e -m smoke --target=staging",
        schedule=SchedulePolicy(
            days_of_week=(0, 1, 2, 3, 4),
            times_of_day=(time(12, 0),),
            frequency=ScheduleFrequency.DAILY,
            tolerance_mode=ToleranceMode.EXACT,
        ),
        target=TerminalTargetConfig(
            app=TerminalApp.GHOSTTY,
            keep_open=False,
        ),
        folder="Operations",
        is_paused=True,
    )
    storage.save_job(job6)

    # Execution history for jobs
    today = date.today()
    # Job 1: Automated Code Review (Ran today at 08:30)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="code-review-ai",
            timestamp=datetime(today.year, today.month, today.day, 8, 30, 15),
            status=ExecutionStatus.SUCCESS,
            details="Dispatched /agentic-code-review into Herdr space 'Factory' tab 'Code Review 10/11'",
            trigger_type=TriggerType.SCHEDULED,
        )
    )
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="code-review-ai",
            timestamp=datetime(today.year, today.month, max(1, today.day - 1), 8, 30, 2),
            status=ExecutionStatus.SUCCESS,
            details="Reviewed PR #42: /agentic-code-review passed, zero security issues, approved",
            trigger_type=TriggerType.SCHEDULED,
        )
    )
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="code-review-ai",
            timestamp=datetime(today.year, today.month, max(1, today.day - 2), 8, 31, 45),
            status=ExecutionStatus.SUCCESS,
            details="Reviewed PR #39: /agentic-code-review remediation verified, clean lint (3m24s)",
            trigger_type=TriggerType.SCHEDULED,
        )
    )

    # Job 3: Architecture Improver (Ran today at 07:00)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="arch-improver",
            timestamp=datetime(today.year, today.month, today.day, 7, 0, 24),
            status=ExecutionStatus.SUCCESS,
            details="Refactored domain boundary: decoupled storage port from UI handlers",
            trigger_type=TriggerType.SCHEDULED,
        )
    )

    # Job 5: PR Security Audit (Ran today at 10:00)
    storage.record_execution(
        ExecutionRecord(
            id=None,
            job_id="sec-audit",
            timestamp=datetime(today.year, today.month, today.day, 10, 0, 18),
            status=ExecutionStatus.SUCCESS,
            details="Scanned 4 active branches: zero vulnerabilities detected in lockfile",
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

    # Widescreen terminal size: 176 cols x 32 rows
    # Spacious layout with clean non-exhausting sidebar and compact typography
    no_scroll_css = "* { scrollbar-size: 0 0; } #jobs-list { scrollbar-size-vertical: 0; } #inspector { scrollbar-size-vertical: 0; }"

    # 1. Render Night Theme Dashboard
    app_night = RoostrApp(storage=storage, locale="en", theme="night", daemon_service=daemon_mock)
    app_night.stylesheet.add_source(no_scroll_css)
    async with app_night.run_test(size=(176, 32)) as pilot:
        await pilot.pause(0.2)
        pilot.app.dashboard_screen.refresh_jobs("code-review-ai")
        await pilot.pause(0.2)
        svg_night = output_dir / "roostr-dashboard-night.svg"
        export_clean_svg(app_night, svg_night)
        print(f"Generated clean SVG: {svg_night}")

    # 2. Render Tokyo Night Theme (Featured in README)
    app_tokyo = RoostrApp(storage=storage, locale="en", theme="tokyo-night", daemon_service=daemon_mock)
    app_tokyo.stylesheet.add_source(no_scroll_css)
    async with app_tokyo.run_test(size=(176, 32)) as pilot:
        await pilot.pause(0.2)
        pilot.app.dashboard_screen.refresh_jobs("code-review-ai")
        await pilot.pause(0.2)
        svg_tokyo = output_dir / "roostr-dashboard-tokyo-night.svg"
        export_clean_svg(app_tokyo, svg_tokyo)
        print(f"Generated clean SVG: {svg_tokyo}")

    # Clean up demo db
    if db_path.exists():
        db_path.unlink()


if __name__ == "__main__":
    assets_dir = Path(__file__).resolve().parent.parent / "docs" / "assets"
    asyncio.run(generate_assets(assets_dir))
