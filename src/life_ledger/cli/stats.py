"""CLI — statistics and dashboard commands."""

from __future__ import annotations

from collections.abc import Iterable

import click
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from life_ledger.cli.context import stats_service
from life_ledger.domain.models import OverallStats, TaskStats, Trend

console = Console()

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

_BAR_WIDTH = 14
_MIN_BAR_WIDTH = 1


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_rate(rate: float | None) -> str:
    """Format a completion rate for terminal display."""
    if rate is None:
        return "[dim]—[/dim]"

    return f"{rate:.0%}"


def _fmt_percentage(rate: float | None) -> str:
    """Format a rate as a percentage without Rich markup."""
    if rate is None:
        return "—"

    return f"{rate:.0%}"


def _fmt_trend(trend: Trend) -> str:
    """Render a trend with semantic terminal styling."""
    styles = {
        Trend.UP: ("green", "↑ UP"),
        Trend.DOWN: ("red", "↓ DOWN"),
        Trend.FLAT: ("yellow", "→ FLAT"),
        Trend.INSUFFICIENT: ("dim", "— N/A"),
    }

    color, label = styles[trend]

    return f"[{color}]{label}[/{color}]"


def _rate_bar(
    rate: float | None,
    *,
    width: int = _BAR_WIDTH,
    filled: str = "━",
    empty: str = "─",
) -> str:
    """Create a compact terminal progress bar for a percentage."""
    if rate is None:
        return f"[dim]{empty * width}[/dim]"

    clamped = max(0.0, min(1.0, rate))
    filled_width = round(clamped * width)

    if clamped > 0 and filled_width == 0:
        filled_width = _MIN_BAR_WIDTH

    empty_width = width - filled_width

    return f"[cyan]{filled * filled_width}[/cyan][dim]{empty * empty_width}[/dim]"


def _trend_symbol(trend: Trend) -> str:
    """Return a compact trend symbol."""
    return {
        Trend.UP: "[green]↑[/green]",
        Trend.DOWN: "[red]↓[/red]",
        Trend.FLAT: "[yellow]→[/yellow]",
        Trend.INSUFFICIENT: "[dim]·[/dim]",
    }[trend]


def _period_label(days: int) -> str:
    if days == 1:
        return "TODAY"

    return f"LAST {days} DAYS"


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------


def _metric_panel(
    label: str,
    value: str,
    *,
    subtitle: str | None = None,
    border_style: str = "cyan",
) -> Panel:
    """Create a compact dashboard metric card."""
    content = Text()

    content.append(value, style="bold white")

    if subtitle:
        content.append("\n")
        content.append(subtitle, style="dim")

    return Panel(
        Align.center(content),
        title=f"[bold]{label}[/bold]",
        title_align="left",
        border_style=border_style,
        box=box.ROUNDED,
        padding=(0, 2),
    )


def _build_kpi_row(overall: OverallStats) -> Table:
    """Build the dashboard KPI card row."""
    avg = _fmt_percentage(overall.avg_rate)

    highest = _fmt_percentage(overall.max_rate)
    lowest = _fmt_percentage(overall.min_rate)

    spread = f"{overall.spread:.0%}" if overall.spread is not None else "—"

    coverage = overall.tracked_days / overall.total_days if overall.total_days else 0.0

    table = Table.grid(
        padding=(0, 1),
        expand=True,
    )

    table.add_row(
        _metric_panel(
            "AVERAGE",
            avg,
            subtitle="across tracked tasks",
            border_style="cyan",
        ),
        _metric_panel(
            "HIGHEST",
            highest,
            subtitle="task completion",
            border_style="green",
        ),
        _metric_panel(
            "LOWEST",
            lowest,
            subtitle="task completion",
            border_style="yellow",
        ),
        _metric_panel(
            "SPREAD",
            spread,
            subtitle="between highest / lowest",
            border_style="magenta",
        ),
        _metric_panel(
            "TRACKING",
            f"{coverage:.0%}",
            subtitle=f"{overall.tracked_days}/{overall.total_days} days",
            border_style="blue",
        ),
    )

    return table


# ---------------------------------------------------------------------------
# Task tables
# ---------------------------------------------------------------------------


def _build_stats_table(
    task_stats: Iterable[TaskStats],
) -> Table:
    """Build the detailed statistics table."""
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        padding=(0, 1),
        expand=True,
    )

    table.add_column(
        "TASK",
        min_width=20,
        ratio=3,
    )
    table.add_column(
        "COMPLETION",
        min_width=24,
        ratio=3,
    )
    table.add_column(
        "DONE",
        width=6,
        justify="right",
    )
    table.add_column(
        "MISSED",
        width=7,
        justify="right",
    )
    table.add_column(
        "RECORDED",
        width=9,
        justify="right",
    )
    table.add_column(
        "STREAK",
        width=8,
        justify="right",
    )
    table.add_column(
        "TREND",
        width=10,
        justify="center",
    )

    for stats in task_stats:
        rate = stats.completion_rate

        if rate is None:
            completion = f"[dim]—[/dim] {_rate_bar(None, width=12)}"
        else:
            completion = f"[bold]{rate:.0%}[/bold] {_rate_bar(rate, width=12)}"

        streak = (
            f"[bold]{stats.current_streak}[/bold]" if stats.current_streak > 0 else "[dim]0[/dim]"
        )

        table.add_row(
            f"[bold]{stats.task.name}[/bold]",
            completion,
            str(stats.completed),
            str(stats.missed),
            str(stats.recorded),
            streak,
            _fmt_trend(stats.trend),
        )

    return table


def _build_dashboard_table(
    task_stats: Iterable[TaskStats],
) -> Table:
    """Build the compact dashboard task table."""
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        padding=(0, 1),
        expand=True,
    )

    table.add_column(
        "",
        width=2,
        justify="center",
    )
    table.add_column(
        "TASK",
        min_width=18,
        ratio=2,
    )
    table.add_column(
        "CURRENT",
        min_width=20,
        ratio=3,
    )
    table.add_column(
        "7D",
        min_width=12,
        ratio=2,
    )
    table.add_column(
        "30D",
        min_width=12,
        ratio=2,
    )
    table.add_column(
        "90D",
        min_width=12,
        ratio=2,
    )
    table.add_column(
        "STREAK",
        width=8,
        justify="right",
    )
    table.add_column(
        "TREND",
        width=8,
        justify="center",
    )

    for stats in task_stats:
        current = (
            f"[bold]{_fmt_percentage(stats.completion_rate)}[/bold] "
            f"{_rate_bar(stats.completion_rate, width=9)}"
        )

        def period(rate: float | None) -> str:
            return f"{_fmt_percentage(rate)} {_rate_bar(rate, width=6)}"

        streak = (
            f"[bold green]{stats.current_streak}[/bold green]"
            if stats.current_streak > 0
            else "[dim]0[/dim]"
        )

        table.add_row(
            _trend_symbol(stats.trend),
            f"[bold]{stats.task.name}[/bold]",
            current,
            period(stats.recent_7d_rate),
            period(stats.recent_30d_rate),
            period(stats.recent_90d_rate),
            streak,
            _fmt_trend(stats.trend),
        )

    return table


# ---------------------------------------------------------------------------
# Summary / observations
# ---------------------------------------------------------------------------


def _build_summary(overall: OverallStats) -> Panel:
    """Build a factual statistical summary panel."""
    lines: list[str] = []

    if overall.max_rate is not None:
        max_task = next(
            (stats for stats in overall.task_stats if stats.completion_rate == overall.max_rate),
            None,
        )

        if max_task is not None:
            lines.append(
                f"[green]Highest[/green]  [bold]{max_task.task.name}[/bold]  {overall.max_rate:.0%}"
            )

    if overall.min_rate is not None:
        min_task = next(
            (stats for stats in overall.task_stats if stats.completion_rate == overall.min_rate),
            None,
        )

        if min_task is not None:
            lines.append(
                f"[yellow]Lowest[/yellow]   "
                f"[bold]{min_task.task.name}[/bold]  "
                f"{overall.min_rate:.0%}"
            )

    if overall.spread is not None:
        lines.append(f"[magenta]Spread[/magenta]   {overall.spread:.0%} percentage points")

    lines.append(f"[blue]Tracking[/blue]  {overall.tracked_days} / {overall.total_days} days")

    return Panel(
        Group(*lines),
        title="[bold]PERIOD SUMMARY[/bold]",
        title_align="left",
        border_style="bright_black",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _build_trend_panel(overall: OverallStats) -> Panel | None:
    """Build a trend summary panel when trend data exists."""
    increasing = [stats for stats in overall.task_stats if stats.trend == Trend.UP]

    decreasing = [stats for stats in overall.task_stats if stats.trend == Trend.DOWN]

    flat = [stats for stats in overall.task_stats if stats.trend == Trend.FLAT]

    if not increasing and not decreasing and not flat:
        return None

    content = Table.grid(
        padding=(0, 3),
    )

    if increasing:
        content.add_row(
            "[green]↑[/green]",
            "[green]Increasing[/green]",
            ", ".join(stats.task.name for stats in increasing),
        )

    if decreasing:
        content.add_row(
            "[red]↓[/red]",
            "[red]Declining[/red]",
            ", ".join(stats.task.name for stats in decreasing),
        )

    if flat:
        content.add_row(
            "[yellow]→[/yellow]",
            "[yellow]Flat[/yellow]",
            ", ".join(stats.task.name for stats in flat),
        )

    return Panel(
        content,
        title="[bold]TREND SNAPSHOT[/bold]",
        title_align="left",
        border_style="bright_black",
        box=box.ROUNDED,
        padding=(1, 1),
    )


# ---------------------------------------------------------------------------
# Stats command
# ---------------------------------------------------------------------------


@click.command("stats")
@click.option(
    "--days",
    type=click.IntRange(min=1),
    default=30,
    show_default=True,
    help="Number of calendar days to analyze.",
)
def cmd_stats(days: int) -> None:
    """Show detailed completion statistics."""
    with stats_service() as svc:
        overall = svc.compute_overall_stats(days)

    if not overall.task_stats:
        console.print("\n[dim]No active tasks. Add some with: life-ledger task add[/dim]\n")
        return

    label = _period_label(days)

    console.print()
    console.print(
        Rule(
            f"[bold cyan] LIFELEDGER · {label} [/bold cyan]",
            style="cyan",
        )
    )
    console.print()

    console.print(_build_kpi_row(overall))
    console.print()

    console.print("[bold]TASK PERFORMANCE[/bold]")
    console.print()

    console.print(_build_stats_table(overall.task_stats))

    console.print()

    summary = _build_summary(overall)
    console.print(summary)

    console.print()


# ---------------------------------------------------------------------------
# Dashboard command
# ---------------------------------------------------------------------------


@click.command("dashboard")
@click.option(
    "--days",
    type=click.IntRange(min=1),
    default=30,
    show_default=True,
    help="Number of calendar days to analyze.",
)
def cmd_dashboard(days: int) -> None:
    """Show the LifeLedger personal balance dashboard."""
    with stats_service() as svc:
        overall = svc.compute_overall_stats(days)

    if not overall.task_stats:
        console.print("\n[dim]No active tasks. Add some with: life-ledger task add[/dim]\n")
        return

    label = _period_label(days)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    console.print()

    title = Text()
    title.append("LIFE LEDGER", style="bold cyan")
    title.append("  /  ", style="dim")
    title.append("PERSONAL BALANCE", style="bold white")

    subtitle = Text(
        f"{label.lower()}  ·  {overall.start_date:%d %b %Y} → {overall.end_date:%d %b %Y}",
        style="dim",
    )

    header = Group(
        Align.center(title),
        Align.center(subtitle),
    )

    console.print(
        Panel(
            header,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )

    console.print()

    # ------------------------------------------------------------------
    # KPI cards
    # ------------------------------------------------------------------

    console.print(_build_kpi_row(overall))
    console.print()

    # ------------------------------------------------------------------
    # Main task matrix
    # ------------------------------------------------------------------

    console.print("[bold]COMMITMENT PULSE[/bold]")
    console.print("[dim]Current period performance with recent-window context[/dim]")
    console.print()

    console.print(_build_dashboard_table(overall.task_stats))

    console.print()

    # ------------------------------------------------------------------
    # Summary + trends
    # ------------------------------------------------------------------

    summary = _build_summary(overall)
    trend_panel = _build_trend_panel(overall)

    if trend_panel is not None:
        layout = Table.grid(
            expand=True,
            padding=(0, 1),
        )
        layout.add_row(
            summary,
            trend_panel,
        )
        console.print(layout)
    else:
        console.print(summary)

    console.print()

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    console.print(
        Rule(
            "[dim]YES = explicitly completed · NO = explicitly missed · — = not recorded[/dim]",
            style="bright_black",
        )
    )
    console.print()
