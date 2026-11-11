import json
import sys
from datetime import time
from pathlib import Path

import click

from roostr import __version__
from roostr.application.use_cases.execute_job import ExecuteJobUseCase
from roostr.application.use_cases.manage_jobs import ManageJobsUseCase
from roostr.domain.enums import (
    AIHarness,
    ExecutionStatus,
    ScheduleFrequency,
    TargetType,
    TerminalApp,
    ToleranceMode,
)
from roostr.domain.models import (
    AgentAction,
    BackgroundTargetConfig,
    CommandAction,
    HerdrTargetConfig,
    Job,
    SchedulePolicy,
    TerminalTargetConfig,
    parse_days_of_week,
    parse_time_string,
    parse_times_list,
    slugify,
)
from roostr.infrastructure.storage import SQLiteStorage


def get_default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "roostr" / "roostr.db"


def get_default_storage() -> SQLiteStorage:
    return SQLiteStorage(get_default_db_path())


def get_storage_from_ctx(ctx: click.Context, db_param: Path | None = None) -> SQLiteStorage:
    effective_db = db_param or (ctx.obj.get("db") if ctx.obj else None)
    return SQLiteStorage(effective_db) if effective_db else get_default_storage()


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, package_name="roostr", message="roostr %(version)s")
@click.option(
    "--locale",
    "-l",
    type=click.Choice(["en", "pt_br", "es"], case_sensitive=False),
    default=None,
    help="UI language locale (en, pt_br, es).",
)
@click.option(
    "--theme",
    "-t",
    type=click.Choice(["night", "morning", "tokyo-night", "nord", "dracula"], case_sensitive=False),
    default=None,
    help="UI theme (night, morning, tokyo-night, nord, dracula).",
)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path to SQLite database.",
)
@click.pass_context
def main(ctx: click.Context, locale: str | None, theme: str | None, db: Path | None) -> None:
    """roostr: Wake up your local AI coding agents on schedule."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db
    ctx.obj["locale"] = locale
    ctx.obj["theme"] = theme

    if ctx.invoked_subcommand is None:
        from roostr.infrastructure.launchd import LaunchdServiceAdapter
        from roostr.ui.app import RoostrApp

        storage = SQLiteStorage(db) if db else get_default_storage()
        saved_locale = storage.get_setting("locale", "en")
        saved_theme = storage.get_setting("theme", "night")
        effective_locale = locale or saved_locale or "en"
        effective_theme = theme or saved_theme or "night"
        daemon_svc = LaunchdServiceAdapter()
        app = RoostrApp(
            storage=storage,
            locale=effective_locale,
            theme=effective_theme,
            daemon_service=daemon_svc,
        )
        app.run()


# ==============================================================================
# Execution Logic (Shared between `roostr run` and `roostr job run`)
# ==============================================================================


def _execute_single_job(storage: SQLiteStorage, job_id: str, force: bool, json_output: bool) -> None:
    use_case = ExecuteJobUseCase(storage=storage)
    status, message = use_case.execute(job_id, force=force)

    if json_output:
        res = {
            "job_id": job_id,
            "status": status.value,
            "message": message,
            "success": status
            in (
                ExecutionStatus.SUCCESS,
                ExecutionStatus.SKIPPED_ALREADY_RAN,
                ExecutionStatus.SKIPPED_OUTSIDE_WINDOW,
            ),
        }
        click.echo(json.dumps(res, indent=2))
    else:
        click.echo(f"[{status.value}] {message}")

    if status in (
        ExecutionStatus.SUCCESS,
        ExecutionStatus.SKIPPED_ALREADY_RAN,
        ExecutionStatus.SKIPPED_OUTSIDE_WINDOW,
    ):
        sys.exit(0)
    else:
        sys.exit(1)


def _execute_due_jobs(storage: SQLiteStorage, json_output: bool) -> None:
    from roostr.application.use_cases.daemon import DaemonSchedulerUseCase

    execute_uc = ExecuteJobUseCase(storage=storage)
    daemon_uc = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=execute_uc)

    results = daemon_uc.tick()
    if json_output:
        payload = {
            "executed_count": len(results),
            "results": [
                {
                    "job_id": j_id,
                    "status": status.value,
                    "details": details,
                }
                for j_id, status, details in results
            ],
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        if not results:
            click.echo("Tick complete: No jobs due.")
        else:
            click.echo(f"Tick complete: Executed {len(results)} job(s):")
            for j_id, status, details in results:
                click.echo(f"  - [{j_id}] {status.value}: {details}")
    sys.exit(0)


@main.command()
@click.argument("job_id", required=False, default=None)
@click.option("--force", is_flag=True, help="Force execution bypassing schedule/idempotency checks.")
@click.option("--due", is_flag=True, help="Execute all jobs that are currently due.")
@click.option("--json", "json_output", is_flag=True, help="Output execution results in JSON format.")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path to SQLite database.",
)
@click.pass_context
def run(ctx: click.Context, job_id: str | None, force: bool, due: bool, json_output: bool, db: Path | None) -> None:
    """Run a specific job now or execute all currently due jobs."""
    storage = get_storage_from_ctx(ctx, db)

    if due or job_id is None:
        if job_id is not None:
            # If job_id was specified along with --due, prefer running the single job
            _execute_single_job(storage, job_id, force=force, json_output=json_output)
        else:
            _execute_due_jobs(storage, json_output=json_output)
    else:
        _execute_single_job(storage, job_id, force=force, json_output=json_output)


# ==============================================================================
# Job Management Commands (`roostr job ...`)
# ==============================================================================


@main.group(name="job")
def job_group() -> None:
    """Inspect and manage scheduled routines (for AI agents & CLI)."""
    pass


@job_group.command(name="list")
@click.option("--folder", "-f", default=None, help="Filter jobs by folder or subfolder.")
@click.option(
    "--status",
    type=click.Choice(["active", "paused"], case_sensitive=False),
    default=None,
    help="Filter jobs by activation status.",
)
@click.option("--json", "json_output", is_flag=True, help="Output jobs as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_list(
    ctx: click.Context, folder: str | None, status: str | None, json_output: bool, db: Path | None
) -> None:
    """List configured jobs with schedule and target summaries."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    is_paused = None
    if status:
        is_paused = status.lower() == "paused"

    jobs = use_case.list_jobs(folder=folder, is_paused=is_paused)

    if json_output:
        payload = [j.to_dict() for j in jobs]
        click.echo(json.dumps(payload, indent=2))
        return

    if not jobs:
        click.echo("No jobs found.")
        return

    # Formatted table output
    click.echo(f"{'ID':<24} {'NAME':<28} {'SCHEDULE':<24} {'TARGET':<16} {'STATUS':<10} {'FOLDER'}")
    click.echo("-" * 115)
    for j in jobs:
        stat_str = "PAUSED" if j.is_paused else "ACTIVE"
        folder_str = j.folder or "-"
        target_str = j.target.target_type.value
        if isinstance(j.target, HerdrTargetConfig) and j.target.space:
            target_str = f"herdr/{j.target.space}"
        elif isinstance(j.target, TerminalTargetConfig):
            target_str = f"terminal/{j.target.app.value}"

        if j.schedule.frequency == ScheduleFrequency.DAILY:
            times = ",".join(t.strftime("%H:%M") for t in j.schedule.times_of_day)
            sched_str = f"daily at {times}"
        else:
            sched_str = f"every {j.schedule.interval_value}{j.schedule.frequency.value[9:10]}"

        click.echo(
            f"{j.id:<24} {j.name[:26]:<28} {sched_str[:22]:<24} {target_str[:14]:<16} {stat_str:<10} {folder_str}"
        )


@job_group.command(name="show")
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, help="Output job details as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_show(ctx: click.Context, job_id: str, json_output: bool, db: Path | None) -> None:
    """Show detailed configuration and recent status of a specific job."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    job = use_case.get_job(job_id)
    if not job:
        click.echo(f"Error: Job '{job_id}' not found.", err=True)
        sys.exit(1)

    last_exec = storage.get_last_execution(job_id)

    if json_output:
        data = job.to_dict()
        data["last_execution"] = last_exec.to_dict() if last_exec else None
        click.echo(json.dumps(data, indent=2))
        return

    # Visual Human-Readable Output
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days_str = ", ".join(day_names[d] for d in sorted(job.schedule.days_of_week))

    click.echo(f"Job: {job.name} ({job.id})")
    click.echo("=" * 60)
    click.echo(f"Status:       {'PAUSED' if job.is_paused else 'ACTIVE'}")
    click.echo(f"Folder:       {job.folder or '(none)'}")
    click.echo(f"Working Dir:  {job.cwd}")
    click.echo(f"Created At:   {job.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo()
    click.echo("Action:")
    click.echo(f"  Type:       {job.action.action_type.value}")
    if isinstance(job.action, AgentAction):
        click.echo(f"  Harness:    {job.action.harness.value}")
        click.echo(f"  Prompt:     {job.action.prompt}")
    click.echo(f"  Command:    {job.command}")
    click.echo()
    click.echo("Schedule:")
    click.echo(f"  Frequency:  {job.schedule.frequency.value}")
    if job.schedule.frequency == ScheduleFrequency.DAILY:
        times_str = ", ".join(t.strftime("%H:%M") for t in job.schedule.times_of_day)
        click.echo(f"  Times:      {times_str}")
    else:
        click.echo(f"  Interval:   {job.schedule.interval_value}")
    click.echo(f"  Days:       {days_str}")
    click.echo(f"  Tolerance:  {job.schedule.tolerance_mode.value} (value: {job.schedule.tolerance_value})")
    if job.schedule.start_time or job.schedule.end_time:
        st = job.schedule.start_time.strftime("%H:%M") if job.schedule.start_time else "start of day"
        et = job.schedule.end_time.strftime("%H:%M") if job.schedule.end_time else "end of day"
        click.echo(f"  Window:     {st} -> {et}")
    click.echo()
    click.echo("Target:")
    click.echo(f"  Type:       {job.target.target_type.value}")
    if isinstance(job.target, HerdrTargetConfig):
        click.echo(f"  Space:      {job.target.space}")
        click.echo(f"  Tab Name:   {job.target.tab_template}")
    elif isinstance(job.target, TerminalTargetConfig):
        click.echo(f"  App:        {job.target.app.value}")
        click.echo(f"  Keep Open:  {job.target.keep_open}")
    elif isinstance(job.target, BackgroundTargetConfig):
        click.echo(f"  Notify:     {job.target.notify_on_complete}")
    click.echo()
    click.echo("Last Execution:")
    if last_exec:
        ts = last_exec.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"  [{last_exec.status.value.upper()}] {ts} ({last_exec.trigger_type.value})")
        if last_exec.details:
            click.echo(f"  Details: {last_exec.details}")
    else:
        click.echo("  Never executed.")


@job_group.command(name="create")
@click.option("--name", "-n", required=True, help="Descriptive name of the routine.")
@click.option("--prompt", "-p", default=None, help="AI prompt instruction (for AI coding harness).")
@click.option("--command", "-c", default=None, help="Custom shell command (alternative to prompt).")
@click.option(
    "--harness",
    type=click.Choice(["claude", "antigravity", "agy", "cursor", "codex"], case_sensitive=False),
    default="claude",
    help="AI coding harness to execute (default: claude).",
)
@click.option(
    "--target",
    type=click.Choice(["herdr", "terminal", "background"], case_sensitive=False),
    default="herdr",
    help="Execution target (default: herdr).",
)
@click.option("--cwd", default=None, help="Working directory (default: current working directory).")
@click.option("--folder", "-f", default=None, help="Folder hierarchy (e.g. Work/Daily).")
@click.option("--id", "custom_id", default=None, help="Custom job ID (inferred from name if omitted).")
@click.option("--times", "-t", default="08:00", help="Comma-separated times (e.g. 08:00, 7am,2:30pm).")
@click.option(
    "--frequency",
    type=click.Choice(["daily", "interval_hours", "interval_minutes"], case_sensitive=False),
    default="daily",
    help="Schedule frequency (default: daily).",
)
@click.option("--interval", type=int, default=1, help="Interval step value if interval frequency.")
@click.option("--days", default="all", help="Active days (e.g. mon,tue,wed or all, weekdays).")
@click.option(
    "--tolerance",
    type=click.Choice(["exact", "until_hour", "window_hours"], case_sensitive=False),
    default="window_hours",
    help="Tolerance catch-up mode (default: window_hours).",
)
@click.option("--tolerance-value", type=int, default=1, help="Tolerance window value (default: 1).")
@click.option("--start-time", default=None, help="Active window start time (e.g. 09:00).")
@click.option("--end-time", default=None, help="Active window end time (e.g. 18:00).")
@click.option("--space", default="Roostr", help="Herdr workspace space name (default: Roostr).")
@click.option("--tab-template", default="{job.name} {DD}/{MM}", help="Herdr tab template.")
@click.option(
    "--terminal-app",
    type=click.Choice(["auto", "terminal", "ghostty", "iterm2", "kitty"], case_sensitive=False),
    default="auto",
    help="Terminal emulator app (default: auto).",
)
@click.option("--keep-open/--no-keep-open", default=True, help="Keep terminal window open after run.")
@click.option("--notify/--no-notify", default=True, help="Show desktop notification on background run.")
@click.option("--paused", is_flag=True, default=False, help="Create job in paused state.")
@click.option("--json", "json_output", is_flag=True, help="Output created job as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_create(
    ctx: click.Context,
    name: str,
    prompt: str | None,
    command: str | None,
    harness: str,
    target: str,
    cwd: str | None,
    folder: str | None,
    custom_id: str | None,
    times: str,
    frequency: str,
    interval: int,
    days: str,
    tolerance: str,
    tolerance_value: int,
    start_time: str | None,
    end_time: str | None,
    space: str,
    tab_template: str,
    terminal_app: str,
    keep_open: bool,
    notify: bool,
    paused: bool,
    json_output: bool,
    db: Path | None,
) -> None:
    """Create a new scheduled routine for AI agents or shell scripts."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    # Resolve ID
    base_id = custom_id or slugify(name)
    job_id = base_id
    counter = 2
    while storage.get_job(job_id) is not None:
        job_id = f"{base_id}-{counter}"
        counter += 1

    # Resolve Working Directory
    resolved_cwd = cwd or str(Path.cwd())

    # Resolve Action
    if command:
        action = CommandAction(command=command)
    else:
        if not prompt:
            click.echo("Error: Either --prompt or --command is required.", err=True)
            sys.exit(1)
        harness_key = "antigravity" if harness.lower() == "agy" else harness.lower()
        action = AgentAction(harness=AIHarness(harness_key), prompt=prompt)

    # Resolve Schedule
    days_tuple = parse_days_of_week(days)
    times_tuple = parse_times_list(times)
    parsed_start = parse_time_string(start_time) if start_time else None
    parsed_end = parse_time_string(end_time) if end_time else None

    schedule = SchedulePolicy(
        days_of_week=days_tuple,
        times_of_day=times_tuple,
        time_of_day=times_tuple[0] if times_tuple else time(8, 0),
        frequency=ScheduleFrequency(frequency.lower()),
        interval_value=interval,
        tolerance_mode=ToleranceMode(tolerance.lower()),
        tolerance_value=tolerance_value,
        start_time=parsed_start,
        end_time=parsed_end,
    )

    # Resolve Target
    target_type = TargetType(target.lower())
    if target_type == TargetType.HERDR:
        target_cfg = HerdrTargetConfig(space=space, tab_template=tab_template)
    elif target_type == TargetType.TERMINAL:
        target_cfg = TerminalTargetConfig(app=TerminalApp(terminal_app.lower()), keep_open=keep_open)
    else:
        target_cfg = BackgroundTargetConfig(notify_on_complete=notify)

    new_job = Job(
        id=job_id,
        name=name,
        cwd=resolved_cwd,
        schedule=schedule,
        target=target_cfg,
        action=action,
        is_paused=paused,
        folder=folder,
    )

    use_case.create_job(new_job)

    if json_output:
        click.echo(json.dumps(new_job.to_dict(), indent=2))
    else:
        click.echo(f"✓ Created job '{new_job.name}' (id: {new_job.id})")


@job_group.command(name="update")
@click.argument("job_id")
@click.option("--name", "-n", default=None, help="Updated job name.")
@click.option("--prompt", "-p", default=None, help="Updated AI prompt.")
@click.option("--command", "-c", default=None, help="Updated shell command.")
@click.option(
    "--harness",
    type=click.Choice(["claude", "antigravity", "agy", "cursor", "codex"], case_sensitive=False),
    default=None,
    help="Updated AI harness.",
)
@click.option(
    "--target",
    type=click.Choice(["herdr", "terminal", "background"], case_sensitive=False),
    default=None,
    help="Updated execution target.",
)
@click.option("--cwd", default=None, help="Updated working directory.")
@click.option("--folder", "-f", default=None, help="Updated folder ('none' or '' to clear).")
@click.option("--times", "-t", default=None, help="Updated comma-separated times.")
@click.option(
    "--frequency",
    type=click.Choice(["daily", "interval_hours", "interval_minutes"], case_sensitive=False),
    default=None,
    help="Updated schedule frequency.",
)
@click.option("--interval", type=int, default=None, help="Updated interval step value.")
@click.option("--days", default=None, help="Updated active days.")
@click.option(
    "--tolerance",
    type=click.Choice(["exact", "until_hour", "window_hours"], case_sensitive=False),
    default=None,
    help="Updated tolerance catch-up mode.",
)
@click.option("--tolerance-value", type=int, default=None, help="Updated tolerance window value.")
@click.option("--space", default=None, help="Updated Herdr space.")
@click.option("--tab-template", default=None, help="Updated Herdr tab template.")
@click.option(
    "--terminal-app",
    type=click.Choice(["auto", "terminal", "ghostty", "iterm2", "kitty"], case_sensitive=False),
    default=None,
    help="Updated terminal app.",
)
@click.option("--keep-open/--no-keep-open", default=None, help="Keep terminal open after run.")
@click.option("--notify/--no-notify", default=None, help="Notify on background run.")
@click.option("--json", "json_output", is_flag=True, help="Output updated job as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_update(
    ctx: click.Context,
    job_id: str,
    name: str | None,
    prompt: str | None,
    command: str | None,
    harness: str | None,
    target: str | None,
    cwd: str | None,
    folder: str | None,
    times: str | None,
    frequency: str | None,
    interval: int | None,
    days: str | None,
    tolerance: str | None,
    tolerance_value: int | None,
    space: str | None,
    tab_template: str | None,
    terminal_app: str | None,
    keep_open: bool | None,
    notify: bool | None,
    json_output: bool,
    db: Path | None,
) -> None:
    """Update fields of an existing job."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    job = use_case.get_job(job_id)
    if not job:
        click.echo(f"Error: Job '{job_id}' not found.", err=True)
        sys.exit(1)

    # Update Name & CWD
    if name is not None:
        job.name = name
    if cwd is not None:
        job.cwd = cwd

    # Update Folder
    if folder is not None:
        if folder.strip().lower() in ("", "none", "-"):
            job.folder = None
        else:
            job.folder = folder

    # Update Action
    if command is not None:
        job.action = CommandAction(command=command)
    elif prompt is not None or harness is not None:
        current_harness = (
            job.action.harness.value if isinstance(job.action, AgentAction) else "claude"
        )
        current_prompt = job.action.prompt if isinstance(job.action, AgentAction) else ""
        new_harness = harness or current_harness
        if new_harness.lower() == "agy":
            new_harness = "antigravity"
        new_prompt = prompt if prompt is not None else current_prompt
        job.action = AgentAction(harness=AIHarness(new_harness.lower()), prompt=new_prompt)

    # Update Target
    if target is not None:
        t_type = TargetType(target.lower())
        if t_type == TargetType.HERDR:
            job.target = HerdrTargetConfig(
                space=space or "Roostr",
                tab_template=tab_template or "{job.name} {DD}/{MM}",
            )
        elif t_type == TargetType.TERMINAL:
            job.target = TerminalTargetConfig(
                app=TerminalApp(terminal_app.lower()) if terminal_app else TerminalApp.AUTO,
                keep_open=keep_open if keep_open is not None else True,
            )
        elif t_type == TargetType.BACKGROUND:
            job.target = BackgroundTargetConfig(
                notify_on_complete=notify if notify is not None else True,
            )
    else:
        # Update target fields in place
        if isinstance(job.target, HerdrTargetConfig):
            if space is not None:
                job.target.space = space
            if tab_template is not None:
                job.target.tab_template = tab_template
        elif isinstance(job.target, TerminalTargetConfig):
            if terminal_app is not None:
                job.target.app = TerminalApp(terminal_app.lower())
            if keep_open is not None:
                job.target.keep_open = keep_open
        elif isinstance(job.target, BackgroundTargetConfig):
            if notify is not None:
                job.target.notify_on_complete = notify

    # Update Schedule
    if times is not None:
        job.schedule.times_of_day = parse_times_list(times)
        job.schedule.time_of_day = job.schedule.times_of_day[0]
    if days is not None:
        job.schedule.days_of_week = parse_days_of_week(days)
    if frequency is not None:
        job.schedule.frequency = ScheduleFrequency(frequency.lower())
    if interval is not None:
        job.schedule.interval_value = interval
    if tolerance is not None:
        job.schedule.tolerance_mode = ToleranceMode(tolerance.lower())
    if tolerance_value is not None:
        job.schedule.tolerance_value = tolerance_value

    use_case.update_job(job)

    if json_output:
        click.echo(json.dumps(job.to_dict(), indent=2))
    else:
        click.echo(f"✓ Updated job '{job.name}' ({job.id})")


@job_group.command(name="pause")
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, help="Output status as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_pause(ctx: click.Context, job_id: str, json_output: bool, db: Path | None) -> None:
    """Pause a scheduled routine."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    job = use_case.get_job(job_id)
    if not job:
        click.echo(f"Error: Job '{job_id}' not found.", err=True)
        sys.exit(1)

    use_case.set_paused(job_id, paused=True)
    if json_output:
        click.echo(json.dumps({"job_id": job_id, "is_paused": True}))
    else:
        click.echo(f"✓ Paused job '{job.name}' ({job_id})")


@job_group.command(name="resume")
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, help="Output status as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_resume(ctx: click.Context, job_id: str, json_output: bool, db: Path | None) -> None:
    """Resume a paused scheduled routine."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    job = use_case.get_job(job_id)
    if not job:
        click.echo(f"Error: Job '{job_id}' not found.", err=True)
        sys.exit(1)

    use_case.set_paused(job_id, paused=False)
    if json_output:
        click.echo(json.dumps({"job_id": job_id, "is_paused": False}))
    else:
        click.echo(f"✓ Resumed job '{job.name}' ({job_id})")


@job_group.command(name="delete")
@click.argument("job_id")
@click.option("--yes", "-y", is_flag=True, help="Confirm deletion without prompting.")
@click.option("--json", "json_output", is_flag=True, help="Output deletion status as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_delete(ctx: click.Context, job_id: str, yes: bool, json_output: bool, db: Path | None) -> None:
    """Delete a scheduled routine."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    job = use_case.get_job(job_id)
    if not job:
        click.echo(f"Error: Job '{job_id}' not found.", err=True)
        sys.exit(1)

    if not yes and not json_output:
        click.confirm(f"Are you sure you want to delete job '{job.name}' ({job_id})?", abort=True)

    use_case.delete_job(job_id)

    if json_output:
        click.echo(json.dumps({"job_id": job_id, "deleted": True}))
    else:
        click.echo(f"✓ Deleted job '{job.name}' ({job_id})")


@job_group.command(name="run")
@click.argument("job_id")
@click.option("--force", is_flag=True, help="Force execution bypassing schedule/idempotency checks.")
@click.option("--json", "json_output", is_flag=True, help="Output execution results as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def job_run(ctx: click.Context, job_id: str, force: bool, json_output: bool, db: Path | None) -> None:
    """Run a specific job now (alias to `roostr run <job_id>`)."""
    storage = get_storage_from_ctx(ctx, db)
    _execute_single_job(storage, job_id, force=force, json_output=json_output)


# ==============================================================================
# Folder Management Commands (`roostr folder ...`)
# ==============================================================================


@main.group(name="folder")
def folder_group() -> None:
    """Manage job organization folders and subfolders."""
    pass


@folder_group.command(name="list")
@click.option("--json", "json_output", is_flag=True, help="Output folders as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def folder_list(ctx: click.Context, json_output: bool, db: Path | None) -> None:
    """List all configured folders and their job counts."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    folders = use_case.list_folders()
    jobs = use_case.list_jobs()

    counts = {f: 0 for f in folders}
    for j in jobs:
        if j.folder and j.folder in counts:
            counts[j.folder] += 1

    if json_output:
        payload = [{"name": f, "job_count": counts[f]} for f in folders]
        click.echo(json.dumps(payload, indent=2))
        return

    if not folders:
        click.echo("No folders found.")
        return

    click.echo(f"{'FOLDER':<35} {'JOBS'}")
    click.echo("-" * 45)
    for f in folders:
        click.echo(f"{f:<35} {counts[f]}")


@folder_group.command(name="create")
@click.argument("name")
@click.option("--json", "json_output", is_flag=True, help="Output status as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def folder_create(ctx: click.Context, name: str, json_output: bool, db: Path | None) -> None:
    """Create a new 1st or 2nd level folder (e.g. Work/Daily)."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    try:
        cleaned = use_case.create_folder(name)
        if json_output:
            click.echo(json.dumps({"folder": cleaned, "created": True}))
        else:
            click.echo(f"✓ Created folder '{cleaned}'")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@folder_group.command(name="delete")
@click.argument("name")
@click.option("--json", "json_output", is_flag=True, help="Output status as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def folder_delete(ctx: click.Context, name: str, json_output: bool, db: Path | None) -> None:
    """Delete an empty folder."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    try:
        use_case.delete_folder(name)
        if json_output:
            click.echo(json.dumps({"folder": name, "deleted": True}))
        else:
            click.echo(f"✓ Deleted folder '{name}'")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ==============================================================================
# Execution History Command (`roostr history ...`)
# ==============================================================================


@main.command(name="history")
@click.argument("job_id", required=False, default=None)
@click.option("--limit", "-n", type=int, default=20, help="Number of records to fetch (default: 20).")
@click.option("--json", "json_output", is_flag=True, help="Output execution history as JSON.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="Custom path to SQLite database.")
@click.pass_context
def history(ctx: click.Context, job_id: str | None, limit: int, json_output: bool, db: Path | None) -> None:
    """View recent execution history for a specific job or all jobs."""
    storage = get_storage_from_ctx(ctx, db)
    use_case = ManageJobsUseCase(storage=storage)

    records = use_case.get_recent_executions(job_id=job_id, limit=limit)

    if json_output:
        payload = [r.to_dict() for r in records]
        click.echo(json.dumps(payload, indent=2))
        return

    if not records:
        target_name = f"job '{job_id}'" if job_id else "any job"
        click.echo(f"No execution history found for {target_name}.")
        return

    click.echo(f"{'ID':<6} {'JOB ID':<24} {'TIMESTAMP':<20} {'TRIGGER':<12} {'STATUS':<20} {'DETAILS'}")
    click.echo("-" * 110)
    for r in records:
        rec_id = str(r.id) if r.id is not None else "-"
        ts = r.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        click.echo(
            f"{rec_id:<6} {r.job_id[:22]:<24} {ts:<20} {r.trigger_type.value:<12} {r.status.value:<20} {r.details}"
        )


# ==============================================================================
# Herdr Registration Command
# ==============================================================================


@main.command(name="setup-herdr")
def setup_herdr() -> None:
    """Register Roostr in Herdr App with custom Rooster SVG icon."""
    from roostr.infrastructure.targets.herdr import register_herdr_program

    if register_herdr_program():
        click.echo("✓ Successfully registered Roostr in Herdr App (~/.config/herdr-app/programs.json)")
    else:
        click.echo("Herdr App not found (~/.config/herdr-app). Skipping registration.")


# ==============================================================================
# Help Command (`roostr help [topic]`)
# ==============================================================================


@main.command(name="help")
@click.argument("topic", required=False, default=None)
@click.pass_context
def help_cmd(ctx: click.Context, topic: str | None) -> None:
    """Show help for Roostr commands or a specific topic (e.g. roostr help job)."""
    root = ctx.find_root()
    if not topic:
        click.echo(root.get_help())
        return

    # Check if topic is a command/group
    cmd = root.command.get_command(root, topic)
    if cmd:
        with click.Context(cmd, parent=root, info_name=topic) as sub_ctx:
            click.echo(cmd.get_help(sub_ctx))
    else:
        click.echo(f"Unknown topic or command '{topic}'. Available commands:\n")
        click.echo(root.get_help())



# ==============================================================================
# Daemon Management Commands
# ==============================================================================


@main.group()
def daemon() -> None:
    """Manage the background scheduler daemon."""
    pass


@daemon.command(name="run")
@click.option(
    "--interval",
    "-i",
    type=int,
    default=60,
    help="Poll interval in seconds (default: 60).",
)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path to SQLite database.",
)
@click.pass_context
def daemon_run(ctx: click.Context, interval: int, db: Path | None) -> None:
    """Run the scheduler daemon in foreground."""
    from roostr.application.use_cases.daemon import DaemonSchedulerUseCase

    storage = get_storage_from_ctx(ctx, db)
    execute_uc = ExecuteJobUseCase(storage=storage)
    daemon_uc = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=execute_uc)

    click.echo(f"Starting Roostr daemon (poll interval: {interval}s)...")
    try:
        daemon_uc.run_forever(poll_interval_seconds=interval)
    except KeyboardInterrupt:
        click.echo("\nRoostr daemon stopped.")


@daemon.command(name="tick")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path to SQLite database.",
)
@click.pass_context
def daemon_tick(ctx: click.Context, db: Path | None) -> None:
    """Run a single tick evaluation of all active jobs."""
    storage = get_storage_from_ctx(ctx, db)
    _execute_due_jobs(storage, json_output=False)


@daemon.command(name="install")
def daemon_install() -> None:
    """Install and load the background daemon LaunchAgent."""
    from roostr.infrastructure.launchd import LaunchdServiceAdapter

    adapter = LaunchdServiceAdapter()
    try:
        plist_path = adapter.install()
        click.echo(f"✓ Roostr daemon installed and loaded at {plist_path}")
    except Exception as e:
        click.echo(f"✗ Failed to install Roostr daemon: {e}", err=True)
        sys.exit(1)


@daemon.command(name="uninstall")
def daemon_uninstall() -> None:
    """Unload and remove the background daemon LaunchAgent."""
    from roostr.infrastructure.launchd import LaunchdServiceAdapter

    adapter = LaunchdServiceAdapter()
    try:
        adapter.uninstall()
        click.echo("✓ Roostr daemon unloaded and uninstalled.")
    except Exception as e:
        click.echo(f"✗ Failed to uninstall Roostr daemon: {e}", err=True)
        sys.exit(1)


@daemon.command(name="status")
def daemon_status() -> None:
    """Check the status of the background daemon LaunchAgent."""
    from roostr.infrastructure.launchd import LaunchdServiceAdapter

    adapter = LaunchdServiceAdapter()
    if adapter.is_running():
        click.echo("● Roostr daemon is running (loaded in launchd).")
    else:
        click.echo("○ Roostr daemon is stopped (not loaded in launchd).")


if __name__ == "__main__":
    main()
