"""CLI — daily tracking commands: today, log, show, history."""

from __future__ import annotations

from datetime import date

import click
from rich import box
from rich.console import Console
from rich.table import Table

from life_ledger.cli.context import tracking_service
from life_ledger.domain.services import TrackingService

console = Console()


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise click.BadParameter(f"Invalid date {value!r}. Use YYYY-MM-DD format.") from exc


def _ask_yn(prompt: str) -> bool:
    while True:
        answer = (
            click.prompt(
                f"   {prompt}",
                default="",
                show_default=False,
            )
            .strip()
            .lower()
        )

        if answer in {"y", "yes"}:
            return True

        if answer in {"n", "no"}:
            return False

        click.echo("   Please enter y or n.")


def _run_daily_session(
    svc: TrackingService,
    target_date: date,
) -> None:
    """Interactively record all active tasks for a date."""
    tasks_and_entries = svc.get_day_entries(target_date)

    if not tasks_and_entries:
        console.print("\n[dim]No active tasks. Add some with: life-ledger task add[/dim]\n")
        return

    date_label = target_date.strftime("%d %b %Y")

    console.print(f"\n[bold cyan]Daily Tracker — {date_label}[/bold cyan]\n")

    saved = 0

    for index, (task, existing_entry) in enumerate(
        tasks_and_entries,
        start=1,
    ):
        console.print(f"{index}. [bold]{task.name}[/bold]")
        console.print(f"   Minimum: [italic]{task.cutoff_message}[/italic]")

        if existing_entry is not None:
            symbol = "[green]✓[/green]" if existing_entry.completed else "[red]✗[/red]"
            status = "yes" if existing_entry.completed else "no"

            console.print(f"   Already recorded: {symbol} ({status}) — re-enter to update")

        completed = _ask_yn("Done? [y/n]:")
        svc.record_entry_by_id(
            task.id,
            target_date,
            completed,
        )

        saved += 1
        console.print()

    console.print(f"[green]Saved {saved}/{len(tasks_and_entries)} tasks.[/green]\n")


@click.command("today")
def cmd_today() -> None:
    """Record today's daily entries."""
    with tracking_service() as svc:
        _run_daily_session(svc, date.today())


@click.command("log")
@click.option(
    "--date",
    "date_str",
    required=True,
    help="Date to log (YYYY-MM-DD).",
)
def cmd_log(date_str: str) -> None:
    """Record entries for a specific date."""
    target_date = _parse_date(date_str)

    with tracking_service() as svc:
        _run_daily_session(svc, target_date)


@click.command("show")
@click.option(
    "--date",
    "date_str",
    required=True,
    help="Date to show (YYYY-MM-DD).",
)
def cmd_show(date_str: str) -> None:
    """Show active-task entries for a specific date."""
    target_date = _parse_date(date_str)

    with tracking_service() as svc:
        pairs = svc.get_day_entries(target_date)

    date_label = target_date.strftime("%d %b %Y")

    console.print(f"\n[bold cyan]Entries for {date_label}[/bold cyan]\n")

    if not pairs:
        console.print("[dim]No active tasks.[/dim]\n")
        return

    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Task", min_width=20)
    table.add_column("Status", width=14)

    for task, entry in pairs:
        if entry is None:
            status = "[dim]not recorded[/dim]"
        elif entry.completed:
            status = "[green]✓  yes[/green]"
        else:
            status = "[red]✗  no[/red]"

        table.add_row(task.name, status)

    console.print(table)
    console.print()


@click.command("history")
@click.argument("task_name", required=False)
@click.option(
    "--from",
    "from_str",
    default=None,
    help="Start date (YYYY-MM-DD).",
)
@click.option(
    "--to",
    "to_str",
    default=None,
    help="End date (YYYY-MM-DD).",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=60,
    show_default=True,
    help="Maximum number of rows to display.",
)
def cmd_history(
    task_name: str | None,
    from_str: str | None,
    to_str: str | None,
    limit: int,
) -> None:
    """View historical YES/NO entries."""
    from_date = _parse_date(from_str) if from_str else None
    to_date = _parse_date(to_str) if to_str else None

    with tracking_service() as svc:
        history = svc.get_history(
            task_name=task_name,
            from_date=from_date,
            to_date=to_date,
        )

    if not history:
        console.print("\n[dim]No entries found.[/dim]\n")
        return

    title = f"History — {task_name}" if task_name else "History — All Tasks"

    console.print(f"\n[bold cyan]{title}[/bold cyan]\n")

    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
    )

    if not task_name:
        table.add_column("Task", min_width=20)

    table.add_column("Date", width=12)
    table.add_column("Status", width=10)

    for task, entry in history[:limit]:
        symbol = "[green]✓[/green]" if entry.completed else "[red]✗[/red]"

        if task_name:
            table.add_row(
                entry.date.isoformat(),
                symbol,
            )
        else:
            table.add_row(
                task.name,
                entry.date.isoformat(),
                symbol,
            )

    console.print(table)

    if len(history) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(history)} entries. Use --limit to see more.[/dim]"
        )

    console.print()
