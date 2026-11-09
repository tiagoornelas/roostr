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
    default="en",
    help="UI language locale (en, pt_br, es).",
)
@click.option(
    "--theme",
    "-t",
    type=click.Choice(["night", "morning", "tokyo-night", "nord", "dracula"], case_sensitive=False),
    default="night",
    help="UI theme (night, morning, tokyo-night, nord, dracula).",
)
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path to SQLite database.",
)
@click.pass_context
def main(ctx: click.Context, locale: str, theme: str, db: Path | None) -> None:
    """roostr: Wake up your local AI coding agents on schedule."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db
    ctx.obj["locale"] = locale
    ctx.obj["theme"] = theme

    if ctx.invoked_subcommand is None:
        from roostr.ui.app import RoostrApp

        storage = SQLiteStorage(db) if db else get_default_storage()
        app = RoostrApp(storage=storage, locale=locale, theme=theme)
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
        ExecutionStatus.SKIPPED_SENTINEL_EXISTS,
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


if __name__ == "__main__":
    main()
