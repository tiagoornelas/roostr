import sys
from pathlib import Path

import click

from roostr.application.use_cases.execute_job import ExecuteJobUseCase
from roostr.domain.enums import ExecutionStatus
from roostr.infrastructure.storage import SQLiteStorage


def get_default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "roostr" / "roostr.db"


def get_default_storage() -> SQLiteStorage:
    return SQLiteStorage(get_default_db_path())


@click.group(invoke_without_command=True)
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
        from roostr.ui.app import RoostrApp

        storage = SQLiteStorage(db) if db else get_default_storage()
        saved_locale = storage.get_setting("locale", "en")
        saved_theme = storage.get_setting("theme", "night")
        effective_locale = locale or saved_locale or "en"
        effective_theme = theme or saved_theme or "night"
        app = RoostrApp(storage=storage, locale=effective_locale, theme=effective_theme)
        app.run()


@main.command()
@click.argument("job_id")
@click.option("--force", is_flag=True, help="Force execution bypassing schedule/idempotency checks.")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path to SQLite database.",
)
@click.pass_context
def run(ctx: click.Context, job_id: str, force: bool, db: Path | None) -> None:
    """Run a specific job now (used by launchd or CLI)."""
    effective_db = db or (ctx.obj.get("db") if ctx.obj else None)
    storage = SQLiteStorage(effective_db) if effective_db else get_default_storage()
    use_case = ExecuteJobUseCase(storage=storage)

    status, message = use_case.execute(job_id, force=force)
    click.echo(f"[{status.value}] {message}")

    if status in (
        ExecutionStatus.SUCCESS,
        ExecutionStatus.SKIPPED_ALREADY_RAN,
        ExecutionStatus.SKIPPED_OUTSIDE_WINDOW,
    ):
        sys.exit(0)
    else:
        sys.exit(1)


@main.command(name="setup-herdr")
def setup_herdr() -> None:
    """Register Roostr in Herdr App with custom Rooster SVG icon."""
    from roostr.infrastructure.targets.herdr import register_herdr_program

    if register_herdr_program():
        click.echo("✓ Successfully registered Roostr in Herdr App (~/.config/herdr-app/programs.json)")
    else:
        click.echo("Herdr App not found (~/.config/herdr-app). Skipping registration.")


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

    effective_db = db or (ctx.obj.get("db") if ctx.obj else None)
    storage = SQLiteStorage(effective_db) if effective_db else get_default_storage()
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
    from roostr.application.use_cases.daemon import DaemonSchedulerUseCase

    effective_db = db or (ctx.obj.get("db") if ctx.obj else None)
    storage = SQLiteStorage(effective_db) if effective_db else get_default_storage()
    execute_uc = ExecuteJobUseCase(storage=storage)
    daemon_uc = DaemonSchedulerUseCase(storage=storage, execute_job_use_case=execute_uc)

    results = daemon_uc.tick()
    if not results:
        click.echo("Tick complete: No jobs due.")
    else:
        click.echo(f"Tick complete: Executed {len(results)} job(s):")
        for j_id, status, details in results:
            click.echo(f"  - [{j_id}] {status.value}: {details}")


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
