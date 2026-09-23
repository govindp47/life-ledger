"""Unit tests — daily tracking and history."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from life_ledger.domain.models import (
    ArchivedTaskError,
    InvalidDateError,
    TaskNotFoundError,
)
from life_ledger.domain.services import StatsService, TaskService, TrackingService

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TWO_DAYS_AGO = TODAY - timedelta(days=2)


class TestRecordEntry:
    """Tests for recording explicit YES/NO decisions."""

    def test_record_yes(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        entry = tracking_svc.record_entry(
            "Exercise",
            TODAY,
            completed=True,
        )

        assert entry.task_id == task.id
        assert entry.completed is True
        assert entry.date == TODAY
        assert entry.created_at == entry.updated_at

    def test_record_no(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        entry = tracking_svc.record_entry(
            "Exercise",
            TODAY,
            completed=False,
        )

        assert entry.task_id == task.id
        assert entry.completed is False
        assert entry.date == TODAY

    def test_record_entry_by_id(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        entry = tracking_svc.record_entry_by_id(
            task.id,
            TODAY,
            completed=True,
        )

        assert entry.task_id == task.id
        assert entry.completed is True

    def test_record_nonexistent_task_raises(
        self,
        tracking_svc: TrackingService,
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            tracking_svc.record_entry(
                "DoesNotExist",
                TODAY,
                True,
            )

    def test_record_nonexistent_task_id_raises(
        self,
        tracking_svc: TrackingService,
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            tracking_svc.record_entry_by_id(
                999,
                TODAY,
                True,
            )

    def test_record_archived_task_raises(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        task_svc.archive_task("Exercise")

        with pytest.raises(ArchivedTaskError):
            tracking_svc.record_entry(
                "Exercise",
                TODAY,
                True,
            )

        with pytest.raises(ArchivedTaskError):
            tracking_svc.record_entry_by_id(
                task.id,
                TODAY,
                True,
            )

    def test_record_same_date_updates_existing_entry(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        """Recording the same task/date twice must update, not duplicate."""
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        first = tracking_svc.record_entry(
            "Exercise",
            TODAY,
            completed=False,
        )

        second = tracking_svc.record_entry(
            "Exercise",
            TODAY,
            completed=True,
        )

        assert second.task_id == first.task_id
        assert second.date == first.date
        assert second.completed is True
        assert second.created_at == first.created_at
        assert second.updated_at >= first.updated_at

        pairs = tracking_svc.get_day_entries(TODAY)

        exercise_pairs = [(task, entry) for task, entry in pairs if task.name == "Exercise"]

        assert len(exercise_pairs) == 1

        entry = exercise_pairs[0][1]

        assert entry is not None
        assert entry.completed is True

    def test_record_different_dates_creates_separate_entries(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            True,
        )
        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            False,
        )

        history = tracking_svc.get_history(
            task_name="Exercise",
        )

        assert len(history) == 2

        dates = {entry.date for _, entry in history}

        assert dates == {
            YESTERDAY,
            TODAY,
        }


class TestMissingEntrySemantics:
    """Tests proving that missing records are distinct from NO."""

    def test_missing_entry_is_not_no(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        """No row means NOT RECORDED, not NO."""
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        pairs = tracking_svc.get_day_entries(YESTERDAY)

        exercise_pairs = [(task, entry) for task, entry in pairs if task.name == "Exercise"]

        assert len(exercise_pairs) == 1

        _task, entry = exercise_pairs[0]

        assert entry is None

    def test_missing_entry_does_not_count_as_missed(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        """Missing days must not inflate the missed count."""
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            completed=True,
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        stats = next(stats for stats in overall.task_stats if stats.task.name == "Exercise")

        assert stats.completed == 1
        assert stats.missed == 0
        assert stats.recorded == 1
        assert stats.completion_rate == pytest.approx(1.0)

    def test_explicit_no_counts_as_missed(
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
            completed=False,
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        stats = next(stats for stats in overall.task_stats if stats.task.name == "Exercise")

        assert stats.completed == 0
        assert stats.missed == 1
        assert stats.recorded == 1
        assert stats.completion_rate == pytest.approx(0.0)

    def test_completion_rate_uses_recorded_denominator(
        self,
        conn: sqlite3.Connection,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        stats_svc: StatsService,
    ) -> None:
        """Rate = completed / recorded, not completed / calendar days."""
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

        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            completed=True,
        )
        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            completed=True,
        )
        tracking_svc.record_entry(
            "Exercise",
            TWO_DAYS_AGO,
            completed=False,
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        stats = next(stats for stats in overall.task_stats if stats.task.name == "Exercise")

        assert stats.recorded == 3
        assert stats.completed == 2
        assert stats.missed == 1
        assert stats.completion_rate == pytest.approx(2 / 3)

    def test_zero_recorded_returns_none_rate(
        self,
        task_svc: TaskService,
        stats_svc: StatsService,
    ) -> None:
        """Zero recorded days must produce None, not 0%."""
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        overall = stats_svc.compute_overall_stats(
            30,
            reference_date=TODAY,
        )

        stats = next(stats for stats in overall.task_stats if stats.task.name == "Exercise")

        assert stats.recorded == 0
        assert stats.completed == 0
        assert stats.missed == 0
        assert stats.completion_rate is None


class TestDayEntries:
    """Tests for the daily active-task view."""

    def test_day_entries_contains_all_active_tasks(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.create_task(
            "Learning",
            "45 min",
        )

        pairs = tracking_svc.get_day_entries(TODAY)

        assert len(pairs) == 2

        names = {task.name for task, _entry in pairs}

        assert names == {
            "Exercise",
            "Learning",
        }

    def test_day_entries_distinguishes_recorded_and_missing(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
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

        pairs = tracking_svc.get_day_entries(TODAY)

        by_name = {task.name: entry for task, entry in pairs}

        assert by_name["Exercise"] is not None
        assert by_name["Exercise"].completed is True
        assert by_name["Learning"] is None

    def test_archived_tasks_are_not_in_daily_view(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.create_task(
            "Learning",
            "45 min",
        )

        task_svc.archive_task("Exercise")

        pairs = tracking_svc.get_day_entries(TODAY)

        names = {task.name for task, _entry in pairs}

        assert names == {"Learning"}


class TestHistory:
    """Tests for historical entry retrieval."""

    def test_get_history_all_tasks(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
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
            YESTERDAY,
            False,
        )

        history = tracking_svc.get_history()

        assert len(history) == 2

        assert {(task.name, entry.date, entry.completed) for task, entry in history} == {
            ("Exercise", TODAY, True),
            ("Learning", YESTERDAY, False),
        }

    def test_get_history_filtered_by_task(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
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
            YESTERDAY,
            False,
        )

        history = tracking_svc.get_history(
            task_name="Exercise",
        )

        assert len(history) == 1
        assert history[0][0].name == "Exercise"
        assert history[0][1].date == TODAY
        assert history[0][1].completed is True

    def test_get_history_is_case_insensitive(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
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

        history = tracking_svc.get_history(
            task_name="exercise",
        )

        assert len(history) == 1
        assert history[0][0].name == "Exercise"

    def test_get_history_nonexistent_task_raises(
        self,
        tracking_svc: TrackingService,
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            tracking_svc.get_history(
                task_name="DoesNotExist",
            )

    def test_get_history_date_range(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
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
        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            False,
        )
        tracking_svc.record_entry(
            "Exercise",
            TWO_DAYS_AGO,
            True,
        )

        history = tracking_svc.get_history(
            from_date=YESTERDAY,
            to_date=TODAY,
        )

        dates = {entry.date for _, entry in history}

        assert dates == {
            YESTERDAY,
            TODAY,
        }

    def test_get_history_includes_archived_task_records(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            True,
        )

        task_svc.archive_task("Exercise")

        history = tracking_svc.get_history()

        assert len(history) == 1
        assert history[0][0].id == task.id
        assert history[0][0].is_active is False
        assert history[0][1].date == YESTERDAY

    def test_get_history_is_sorted_newest_first(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            TWO_DAYS_AGO,
            True,
        )
        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            True,
        )
        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            False,
        )

        history = tracking_svc.get_history(
            task_name="Exercise",
        )

        assert [entry.date for _, entry in history] == [
            TODAY,
            YESTERDAY,
            TWO_DAYS_AGO,
        ]

    def test_get_history_invalid_date_range_raises(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        with pytest.raises(InvalidDateError):
            tracking_svc.get_history(
                from_date=TODAY,
                to_date=YESTERDAY,
            )

    def test_get_history_without_dates_returns_all_entries(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            TWO_DAYS_AGO,
            True,
        )
        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            True,
        )
        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            True,
        )

        history = tracking_svc.get_history(
            task_name="Exercise",
        )

        assert len(history) == 3
