"""CLI entry point — root command group."""

from __future__ import annotations

import logging
import sys

import click

from life_ledger.cli.stats import cmd_dashboard, cmd_stats
from life_ledger.cli.tasks import task_group
from life_ledger.cli.tracking import (
    cmd_history,
    cmd_log,
    cmd_show,
    cmd_today,
)
from life_ledger.domain.models import LifeLedgerError


@click.group()
@click.version_option(package_name="life-ledger")
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    hidden=True,
    help="Enable debug logging.",
)
def cli(debug: bool) -> None:
    """LifeLedger — track whether you are meeting your daily commitments."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


cli.add_command(task_group, name="task")
cli.add_command(cmd_today, name="today")
cli.add_command(cmd_log, name="log")
cli.add_command(cmd_show, name="show")
cli.add_command(cmd_history, name="history")
cli.add_command(cmd_stats, name="stats")
cli.add_command(cmd_dashboard, name="dashboard")


def main() -> None:
    """Application entry point."""
    try:
        cli(standalone_mode=False)
    except LifeLedgerError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.Abort:
        click.echo("\nAborted.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
