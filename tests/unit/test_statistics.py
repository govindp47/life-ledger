"""Unit tests — statistics, streaks, trends, spread, and lifecycle."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from life_ledger.domain.models import DailyEntry, Trend
from life_ledger.domain.services import (
    StatsService,
    TaskService,
    TrackingService,
    _compute_streaks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)


def _make_entries(
    *values: tuple[date, bool],
) -> list[DailyEntry]:
    timestamp = datetime.now(UTC)

    return [
        DailyEntry(
            task_id=1,
            date=entry_date,
            completed=completed,
            created_at=timestamp,
            updated_at=timestamp,
        )
        for entry_date, completed in values
    ]


def _record_period(
    tracking_svc: TrackingService,
    task_name: str,
    start_date: date,
    days: int,
    completed_count: int,
) -> None:
    """Record exactly completed_count YES entries in a period."""
    for offset in range(days):
        entry_date = start_date + timedelta(days=offset)
        tracking_svc.record_entry(
            task_name,
            entry_date,
            completed=offset < completed_count,
        )


# ---------------------------------------------------------------------------
# Streak tests
# ---------------------------------------------------------------------------


class TestStreaks:
    """Tests for consecutive explicit YES entries."""

    def test_empty_entries_give_zero_streaks(self) -> None:
        current, longest = _compute_streaks(
            [],
            TODAY,
        )

        assert current == 0
        assert longest == 0

    def test_single_yes_today_gives_streak_one(self) -> None:
        entries = _make_entries(
            (TODAY, True),
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 1
        assert longest == 1

    def test_single_no_today_gives_zero_current_streak(self) -> None:
        entries = _make_entries(
            (TODAY, False),
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 0
        assert longest == 0

    def test_consecutive_yes_entries_form_streak(self) -> None:
        entries = _make_entries(*[(TODAY - timedelta(days=offset), True) for offset in range(5)])

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 5
        assert longest == 5

    def test_no_breaks_streak(self) -> None:
        entries = _make_entries(
            (TODAY, True),
            (YESTERDAY, False),
            (TWO_DAYS_AGO, True),
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 1
        assert longest == 1

    def test_missing_day_breaks_streak(self) -> None:
        entries = _make_entries(
            (TODAY, True),
            (TWO_DAYS_AGO, True),
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 1
        assert longest == 1

    def test_longest_streak_across_missing_day(self) -> None:
        base = date(2026, 9, 1)

        entries = _make_entries(
            *[
                (base + timedelta(days=offset), True)
                for offset in (
                    0,
                    1,
                    2,
                    4,
                    5,
                    6,
                    7,
                    8,
                )
            ]
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 0
        assert longest == 5

    def test_today_missing_gives_zero_current_streak(self) -> None:
        entries = _make_entries(
            (YESTERDAY, True),
            (TWO_DAYS_AGO, True),
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 0
        assert longest == 2

    def test_no_today_breaks_current_streak_but_longest_remains(
        self,
    ) -> None:
        entries = _make_entries(
            (TODAY, False),
            (YESTERDAY, True),
            (TWO_DAYS_AGO, True),
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 0
        assert longest == 2

    def test_streak_does_not_jump_over_multiple_missing_days(
        self,
    ) -> None:
        entries = _make_entries(
            (TODAY, True),
            (TODAY - timedelta(days=3), True),
        )

        current, longest = _compute_streaks(
            entries,
            TODAY,
        )

        assert current == 1
        assert longest == 1


# ---------------------------------------------------------------------------
# Trend tests
# ---------------------------------------------------------------------------


class TestTrend:
    """Tests for comparable-period trend classification."""

    def test_trend_up(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?
            WHERE id = ?
            """,
            (
                "2026-01-01T12:00:00+00:00",
                task.id,
            ),
        )
        conn.commit()

        reference = date(2026, 9, 22)

        # Previous period:
        # ref-13 ... ref-7 = 2/7 = 28.6%
        previous_start = reference - timedelta(days=13)

        _record_period(
            tracking_svc,
            "Exercise",
            previous_start,
            days=7,
            completed_count=2,
        )

        # Current period:
        # ref-6 ... ref = 6/7 = 85.7%
        current_start = reference - timedelta(days=6)

        _record_period(
            tracking_svc,
            "Exercise",
            current_start,
            days=7,
            completed_count=6,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=reference,
        )

        stats = overall.task_stats[0]

        assert stats.trend == Trend.UP

    def test_trend_down(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?
            WHERE id = ?
            """,
            (
                "2026-01-01T12:00:00+00:00",
                task.id,
            ),
        )
        conn.commit()

        reference = date(2026, 9, 22)

        previous_start = reference - timedelta(days=13)

        _record_period(
            tracking_svc,
            "Exercise",
            previous_start,
            days=7,
            completed_count=7,
        )

        current_start = reference - timedelta(days=6)

        _record_period(
            tracking_svc,
            "Exercise",
            current_start,
            days=7,
            completed_count=2,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=reference,
        )

        stats = overall.task_stats[0]

        assert stats.trend == Trend.DOWN

    def test_trend_flat_when_delta_is_below_threshold(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?
            WHERE id = ?
            """,
            (
                "2026-01-01T12:00:00+00:00",
                task.id,
            ),
        )
        conn.commit()

        reference = date(2026, 9, 22)

        # Previous: 4/7 = 57.14%
        previous_start = reference - timedelta(days=13)

        _record_period(
            tracking_svc,
            "Exercise",
            previous_start,
            days=7,
            completed_count=4,
        )

        # Current: 4/7 = 57.14%
        current_start = reference - timedelta(days=6)

        _record_period(
            tracking_svc,
            "Exercise",
            current_start,
            days=7,
            completed_count=4,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=reference,
        )

        stats = overall.task_stats[0]

        assert stats.trend == Trend.FLAT

    def test_trend_threshold_behavior(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?
            WHERE id = ?
            """,
            (
                "2026-01-01T12:00:00+00:00",
                task.id,
            ),
        )
        conn.commit()

        reference = date(2026, 9, 22)

        # 7-day periods only permit rates in increments of 1/7.
        # 4/7 -> 5/7 is exactly 14.29 percentage points.
        # 4/7 -> 4/7 is 0 points.
        #
        # Verify that a change smaller than the 5pp threshold remains FLAT.
        previous_start = reference - timedelta(days=13)

        _record_period(
            tracking_svc,
            "Exercise",
            previous_start,
            days=7,
            completed_count=4,
        )

        current_start = reference - timedelta(days=6)

        _record_period(
            tracking_svc,
            "Exercise",
            current_start,
            days=7,
            completed_count=4,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=reference,
        )

        assert overall.task_stats[0].trend == Trend.FLAT

    def test_trend_requires_three_recorded_days_in_both_periods(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        reference = TODAY

        # Current period: 2 recorded.
        tracking_svc.record_entry(
            "Exercise",
            reference,
            True,
        )
        tracking_svc.record_entry(
            "Exercise",
            reference - timedelta(days=1),
            True,
        )

        # Previous period: 7 recorded.
        previous_start = reference - timedelta(days=13)

        _record_period(
            tracking_svc,
            "Exercise",
            previous_start,
            days=7,
            completed_count=0,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=reference,
        )

        assert overall.task_stats[0].trend == Trend.INSUFFICIENT

    def test_trend_insufficient_without_previous_data(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        reference = TODAY

        for offset in range(3):
            tracking_svc.record_entry(
                "Exercise",
                reference - timedelta(days=offset),
                True,
            )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=reference,
        )

        assert overall.task_stats[0].trend == Trend.INSUFFICIENT


# ---------------------------------------------------------------------------
# Spread and overall statistics
# ---------------------------------------------------------------------------


class TestOverallStats:
    """Tests for aggregate task statistics."""

    def test_spread_calculation(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        exercise = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        learning = task_svc.create_task(
            "Learning",
            "45 min",
        )

        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?
            WHERE id IN (?, ?)
            """,
            (
                "2026-01-01T12:00:00+00:00",
                exercise.id,
                learning.id,
            ),
        )
        conn.commit()

        reference = date(2026, 9, 22)
        start = reference - timedelta(days=3)

        _record_period(
            tracking_svc,
            "Exercise",
            start,
            days=4,
            completed_count=4,
        )

        _record_period(
            tracking_svc,
            "Learning",
            start,
            days=4,
            completed_count=1,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=reference,
        )

        assert overall.max_rate == pytest.approx(1.0)
        assert overall.min_rate == pytest.approx(0.25)
        assert overall.avg_rate == pytest.approx(0.625)
        assert overall.spread == pytest.approx(0.75)

    def test_spread_is_none_with_single_task(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            True,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=TODAY,
        )

        assert overall.avg_rate == pytest.approx(1.0)
        assert overall.min_rate == pytest.approx(1.0)
        assert overall.max_rate == pytest.approx(1.0)
        assert overall.spread is None

    def test_no_data_gives_none_rates(
        self,
        task_svc: TaskService,
        stats_svc: StatsService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        assert overall.avg_rate is None
        assert overall.min_rate is None
        assert overall.max_rate is None
        assert overall.spread is None

    def test_total_days_matches_requested_period(
        self,
        task_svc: TaskService,
        stats_svc: StatsService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        assert overall.total_days == 30
        assert overall.period_days == 30
        assert overall.start_date == TODAY - timedelta(days=29)
        assert overall.end_date == TODAY

    def test_tracked_days_counts_distinct_calendar_days(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.create_task(
            "Learning",
            "45 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            True,
        )
        tracking_svc.record_entry(
            "Learning",
            TODAY,
            False,
        )
        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            True,
        )

        overall = stats_svc.compute_overall_stats(
            7,
            reference_date=TODAY,
        )

        # Two task entries on TODAY still represent one tracked day.
        assert overall.tracked_days == 2


# ---------------------------------------------------------------------------
# Lifecycle eligibility
# ---------------------------------------------------------------------------


class TestLifecycleEligibility:
    """Tests for task creation/archive boundaries."""

    def test_new_task_not_penalized_for_old_dates(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        created_date = TODAY - timedelta(days=5)

        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?
            WHERE id = ?
            """,
            (
                f"{created_date.isoformat()}T12:00:00+00:00",
                task.id,
            ),
        )

        tracking_svc.record_entry(
            "Exercise",
            created_date,
            True,
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        stats = next(stats for stats in overall.task_stats if stats.task.id == task.id)

        assert stats.recorded == 1
        assert stats.completed == 1
        assert stats.missed == 0
        assert stats.completion_rate == pytest.approx(1.0)

    def test_entry_before_task_creation_is_excluded_from_statistics(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        created_date = TODAY - timedelta(days=5)

        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?
            WHERE id = ?
            """,
            (
                f"{created_date.isoformat()}T12:00:00+00:00",
                task.id,
            ),
        )

        # This row is inserted directly because the normal tracking service
        # intentionally only allows recording active tasks, but historical
        # database state must still be handled correctly by statistics.
        conn.execute(
            """
            INSERT INTO daily_entries (
                task_id,
                date,
                completed,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                task.id,
                (created_date - timedelta(days=1)).isoformat(),
                1,
                "2026-09-20T12:00:00+00:00",
                "2026-09-20T12:00:00+00:00",
            ),
        )

        conn.execute(
            """
            INSERT INTO daily_entries (
                task_id,
                date,
                completed,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                task.id,
                created_date.isoformat(),
                0,
                "2026-09-21T12:00:00+00:00",
                "2026-09-21T12:00:00+00:00",
            ),
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        stats = next(stats for stats in overall.task_stats if stats.task.id == task.id)

        assert stats.recorded == 1
        assert stats.completed == 0
        assert stats.missed == 1
        assert stats.completion_rate == pytest.approx(0.0)

    def test_archived_task_statistics_stop_at_archive_date(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        stats_svc: StatsService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        created_date = TODAY - timedelta(days=10)
        archive_date = TODAY - timedelta(days=3)

        conn.execute(
            """
            UPDATE tasks
            SET
                created_at = ?,
                archived_at = ?
            WHERE id = ?
            """,
            (
                f"{created_date.isoformat()}T12:00:00+00:00",
                f"{archive_date.isoformat()}T12:00:00+00:00",
                task.id,
            ),
        )

        # These rows deliberately cover both sides of the archive boundary.
        conn.executemany(
            """
            INSERT INTO daily_entries (
                task_id,
                date,
                completed,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    task.id,
                    (archive_date - timedelta(days=1)).isoformat(),
                    1,
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
                (
                    task.id,
                    archive_date.isoformat(),
                    1,
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
                (
                    task.id,
                    (archive_date + timedelta(days=1)).isoformat(),
                    0,
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
                (
                    task.id,
                    TODAY.isoformat(),
                    0,
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
            ],
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        stats = next(stats for stats in overall.task_stats if stats.task.id == task.id)

        assert stats.recorded == 2
        assert stats.completed == 2
        assert stats.missed == 0
        assert stats.completion_rate == pytest.approx(1.0)
