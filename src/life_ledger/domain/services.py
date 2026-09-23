"""Domain and application services.

Business rules live here. This layer has no Click or Rich dependencies.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from datetime import date, timedelta

from life_ledger.domain.models import (
    ArchivedTaskError,
    DailyEntry,
    InvalidDateError,
    InvalidTaskError,
    NotArchivedError,
    OverallStats,
    Task,
    TaskAlreadyExistsError,
    TaskNotFoundError,
    TaskStats,
    Trend,
)
from life_ledger.storage.repositories import EntryRepository, TaskRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TREND_FLAT_THRESHOLD = 0.05
TREND_MIN_RECORDED = 3

MAX_NAME_LENGTH = 200
MAX_CUTOFF_LENGTH = 500


# ---------------------------------------------------------------------------
# Task service
# ---------------------------------------------------------------------------


class TaskService:
    """Application operations for task lifecycle management."""

    def __init__(self, task_repo: TaskRepository) -> None:
        self._tasks = task_repo

    def create_task(self, name: str, cutoff_message: str) -> Task:
        """Create a new active task."""
        name = name.strip()
        cutoff_message = cutoff_message.strip()

        _validate_task_fields(name, cutoff_message)

        # Only an active task blocks creation of the same name.
        existing = self._tasks.get_by_name(name)

        if existing is not None and existing.is_active:
            raise TaskAlreadyExistsError(name)

        try:
            task = self._tasks.create(name, cutoff_message)
        except sqlite3.IntegrityError as exc:
            raise TaskAlreadyExistsError(name) from exc

        logger.info("Created task id=%d", task.id)
        return task

    def edit_task(
        self,
        name: str,
        new_name: str | None = None,
        new_cutoff: str | None = None,
    ) -> Task:
        """Edit an active task."""
        task = self._require_task(name)

        if not task.is_active:
            raise ArchivedTaskError(task.name)

        updated_name = new_name.strip() if new_name is not None else task.name
        updated_cutoff = new_cutoff.strip() if new_cutoff is not None else task.cutoff_message

        _validate_task_fields(updated_name, updated_cutoff)

        if updated_name.casefold() != task.name.casefold():
            existing = self._tasks.get_by_name(updated_name)

            if existing is not None and existing.id != task.id:
                if existing.is_active:
                    raise TaskAlreadyExistsError(updated_name)

                # An archived task with the same name does not block the
                # rename because the database allows multiple archived
                # historical task definitions.
                #
                # The partial unique index only protects active tasks.

        try:
            updated_task = self._tasks.update(
                task.id,
                updated_name,
                updated_cutoff,
            )
        except sqlite3.IntegrityError as exc:
            raise TaskAlreadyExistsError(updated_name) from exc

        logger.info("Edited task id=%d", task.id)
        return updated_task

    def archive_task(self, name: str) -> Task:
        """Archive an active task without deleting its history."""
        task = self._require_task(name)

        if not task.is_active:
            raise ArchivedTaskError(task.name)

        archived_task = self._tasks.archive(task.id)

        logger.info("Archived task id=%d", task.id)
        return archived_task

    def restore_task(self, name: str) -> Task:
        """Restore an archived task.

        Restoration fails if another active task already uses the same name.
        """
        task = self._require_task(name)

        if task.is_active:
            raise NotArchivedError(task.name)

        active_task = self._tasks.get_by_name(task.name)

        if active_task is not None and active_task.is_active and active_task.id != task.id:
            raise TaskAlreadyExistsError(task.name)

        try:
            restored_task = self._tasks.restore(task.id)
        except sqlite3.IntegrityError as exc:
            raise TaskAlreadyExistsError(task.name) from exc

        logger.info("Restored task id=%d", task.id)
        return restored_task

    def restore_task_by_id(self, task_id: int) -> Task:
        task = self._tasks.get_by_id(task_id)

        if task is None:
            raise TaskNotFoundError(str(task_id))

        if task.is_active:
            raise NotArchivedError(task.name)

        existing = self._tasks.get_by_name(task.name)

        if existing is not None and existing.is_active and existing.id != task.id:
            raise TaskAlreadyExistsError(task.name)

        try:
            restored_task = self._tasks.restore(task.id)
        except sqlite3.IntegrityError as exc:
            raise TaskAlreadyExistsError(task.name) from exc

        logger.info("Restored task id=%d", task.id)
        return restored_task

    def list_active_tasks(self) -> list[Task]:
        """Return all active tasks."""
        return self._tasks.list_active()

    def list_all_tasks(self) -> list[Task]:
        """Return all tasks, including archived tasks."""
        return self._tasks.list_all()

    def get_task(self, name: str) -> Task:
        """Return a task by exact case-insensitive name."""
        return self._require_task(name)

    def _require_task(self, name: str) -> Task:
        normalized_name = name.strip()

        if not normalized_name:
            raise InvalidTaskError("Task name cannot be empty.")

        task = self._tasks.get_by_name(normalized_name)

        if task is None:
            raise TaskNotFoundError(normalized_name)

        return task


# ---------------------------------------------------------------------------
# Tracking service
# ---------------------------------------------------------------------------


class TrackingService:
    """Application operations for daily tracking."""

    def __init__(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        self._tasks = task_repo
        self._entries = entry_repo

    def record_entry(
        self,
        task_name: str,
        entry_date: date,
        completed: bool,
    ) -> DailyEntry:
        """Record or update a daily entry for an active task."""
        task = self._require_active_task(task_name)

        entry = self._entries.upsert(
            task.id,
            entry_date,
            completed,
        )

        logger.debug(
            "Recorded daily entry for task id=%d on %s",
            task.id,
            entry_date,
        )

        return entry

    def record_entry_by_id(
        self,
        task_id: int,
        entry_date: date,
        completed: bool,
    ) -> DailyEntry:
        """Record or update a daily entry using a task ID."""
        task = self._tasks.get_by_id(task_id)

        if task is None:
            raise TaskNotFoundError(str(task_id))

        if not task.is_active:
            raise ArchivedTaskError(task.name)

        return self._entries.upsert(
            task.id,
            entry_date,
            completed,
        )

    def get_day_entries(
        self,
        entry_date: date,
    ) -> list[tuple[Task, DailyEntry | None]]:
        """Return every active task paired with its entry for a date."""
        result: list[tuple[Task, DailyEntry | None]] = []

        for task in self._tasks.list_active():
            entry = self._entries.get(task.id, entry_date)
            result.append((task, entry))

        return result

    def get_history(
        self,
        task_name: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[Task, DailyEntry]]:
        """Return historical entries with optional task/date filtering."""
        if from_date is not None and to_date is not None:
            _validate_date_range(from_date, to_date)

        if task_name is not None:
            task = self._require_task(task_name)
            tasks = [task]
        else:
            tasks = self._tasks.list_all()

        result: list[tuple[Task, DailyEntry]] = []

        for task in tasks:
            entries = self._entries.list_for_task(
                task.id,
                from_date,
                to_date,
            )

            result.extend((task, entry) for entry in entries)

        result.sort(
            key=lambda item: (
                item[1].date,
                item[0].name.casefold(),
            ),
            reverse=True,
        )

        return result

    def _require_task(self, name: str) -> Task:
        normalized_name = name.strip()

        if not normalized_name:
            raise InvalidTaskError("Task name cannot be empty.")

        task = self._tasks.get_by_name(normalized_name)

        if task is None:
            raise TaskNotFoundError(normalized_name)

        return task

    def _require_active_task(self, name: str) -> Task:
        task = self._require_task(name)

        if not task.is_active:
            raise ArchivedTaskError(task.name)

        return task


# ---------------------------------------------------------------------------
# Statistics service
# ---------------------------------------------------------------------------


class StatsService:
    """Calculate transparent historical and balance statistics."""

    def __init__(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        self._tasks = task_repo
        self._entries = entry_repo

    def compute_overall_stats(
        self,
        days: int,
        reference_date: date | None = None,
    ) -> OverallStats:
        """Calculate statistics for tasks whose lifecycle overlaps the period."""
        _validate_days(days)

        end_date = reference_date or date.today()
        start_date = end_date - timedelta(days=days - 1)

        eligible_tasks = [
            task
            for task in self._tasks.list_all()
            if task.created_date <= end_date
            and (task.archived_date is None or task.archived_date >= start_date)
        ]

        task_stats = [
            self._compute_task_stats(
                task=task,
                start_date=start_date,
                end_date=end_date,
            )
            for task in eligible_tasks
        ]

        task_stats.sort(key=lambda stats: stats.task.name.casefold())

        rates = [stats.completion_rate for stats in task_stats if stats.completion_rate is not None]

        avg_rate = sum(rates) / len(rates) if rates else None

        min_rate = min(rates) if rates else None
        max_rate = max(rates) if rates else None

        spread = (
            max_rate - min_rate
            if len(rates) >= 2 and min_rate is not None and max_rate is not None
            else None
        )

        tracked_days = self._count_tracked_days(
            start_date,
            end_date,
        )

        return OverallStats(
            start_date=start_date,
            end_date=end_date,
            task_stats=tuple(task_stats),
            avg_rate=avg_rate,
            min_rate=min_rate,
            max_rate=max_rate,
            spread=spread,
            tracked_days=tracked_days,
            total_days=days,
        )

    def compute_task_stats_by_name(
        self,
        task_name: str,
        days: int,
        reference_date: date | None = None,
    ) -> TaskStats:
        """Calculate statistics for a specific task."""
        _validate_days(days)

        task = self._tasks.get_by_name(task_name.strip())

        if task is None:
            raise TaskNotFoundError(task_name)

        end_date = reference_date or date.today()
        start_date = end_date - timedelta(days=days - 1)

        return self._compute_task_stats(
            task=task,
            start_date=start_date,
            end_date=end_date,
        )

    def _compute_task_stats(
        self,
        task: Task,
        start_date: date,
        end_date: date,
    ) -> TaskStats:
        """Calculate statistics for one task over a date range."""
        effective_start, effective_end = _effective_period(
            task,
            start_date,
            end_date,
        )

        if effective_start > effective_end:
            completed = 0
            missed = 0
            completion_rate = None
        else:
            completed, missed = self._entries.get_period_stats(
                task.id,
                effective_start,
                effective_end,
            )

            recorded = completed + missed
            completion_rate = completed / recorded if recorded > 0 else None

        entries = self._entries.get_all_entries_for_task(task.id)

        streak_reference = _streak_reference_date(
            task,
            end_date,
        )

        current_streak, longest_streak = _compute_streaks(
            entries,
            streak_reference,
        )

        recent_7d_rate = self._rate_for_period(
            task,
            end_date - timedelta(days=6),
            end_date,
        )

        recent_30d_rate = self._rate_for_period(
            task,
            end_date - timedelta(days=29),
            end_date,
        )

        recent_90d_rate = self._rate_for_period(
            task,
            end_date - timedelta(days=89),
            end_date,
        )

        trend = self._compute_trend(
            task,
            end_date,
            period_days=end_date.toordinal() - start_date.toordinal() + 1,
        )

        return TaskStats(
            task=task,
            start_date=start_date,
            end_date=end_date,
            completed=completed,
            missed=missed,
            recorded=completed + missed,
            completion_rate=completion_rate,
            current_streak=current_streak,
            longest_streak=longest_streak,
            recent_7d_rate=recent_7d_rate,
            recent_30d_rate=recent_30d_rate,
            recent_90d_rate=recent_90d_rate,
            trend=trend,
        )

    def _rate_for_period(
        self,
        task: Task,
        start_date: date,
        end_date: date,
    ) -> float | None:
        """Calculate completion rate for an inclusive date range."""
        effective_start, effective_end = _effective_period(
            task,
            start_date,
            end_date,
        )

        if effective_start > effective_end:
            return None

        completed, missed = self._entries.get_period_stats(
            task.id,
            effective_start,
            effective_end,
        )

        recorded = completed + missed

        if recorded == 0:
            return None

        return completed / recorded

    def _compute_trend(
        self,
        task: Task,
        reference_date: date,
        period_days: int,
    ) -> Trend:
        """Compare the current period with the previous comparable period."""
        current_end = reference_date
        current_start = current_end - timedelta(days=period_days - 1)

        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)

        current_rate = self._rate_for_period(
            task,
            current_start,
            current_end,
        )

        previous_rate = self._rate_for_period(
            task,
            previous_start,
            previous_end,
        )

        current_recorded = self._recorded_count(
            task,
            current_start,
            current_end,
        )

        previous_recorded = self._recorded_count(
            task,
            previous_start,
            previous_end,
        )

        if (
            current_rate is None
            or previous_rate is None
            or current_recorded < TREND_MIN_RECORDED
            or previous_recorded < TREND_MIN_RECORDED
        ):
            return Trend.INSUFFICIENT

        delta = current_rate - previous_rate

        if delta > TREND_FLAT_THRESHOLD:
            return Trend.UP

        if delta < -TREND_FLAT_THRESHOLD:
            return Trend.DOWN

        return Trend.FLAT

    def _recorded_count(
        self,
        task: Task,
        start_date: date,
        end_date: date,
    ) -> int:
        """Return the number of explicit YES/NO records in a period."""
        effective_start, effective_end = _effective_period(
            task,
            start_date,
            end_date,
        )

        if effective_start > effective_end:
            return 0

        completed, missed = self._entries.get_period_stats(
            task.id,
            effective_start,
            effective_end,
        )

        return completed + missed

    def _count_tracked_days(
        self,
        start_date: date,
        end_date: date,
    ) -> int:
        """Count distinct calendar days with at least one recorded entry.

        Historical records are included even if their task is now archived.
        This keeps tracking coverage a historical measure rather than an
        active-task-only measure.
        """
        tracked_dates: set[date] = set()

        for task in self._tasks.list_all():
            entries = self._entries.list_for_task(
                task.id,
                start_date,
                end_date,
            )

            tracked_dates.update(entry.date for entry in entries)

        return len(tracked_dates)


# ---------------------------------------------------------------------------
# Pure calculation helpers
# ---------------------------------------------------------------------------


def _compute_streaks(
    entries: Sequence[DailyEntry],
    reference_date: date,
) -> tuple[int, int]:
    """Return current and longest completed-day streaks.

    Rules:

    - YES contributes to a streak.
    - NO breaks a streak.
    - NOT RECORDED breaks a streak.
    - Current streak only exists if the reference date is explicitly YES.
    - The longest streak is calculated across all recorded history.
    """
    if not entries:
        return 0, 0

    lookup = {entry.date: entry.completed for entry in entries}

    longest = 0
    run = 0
    previous_date: date | None = None

    for entry_date in sorted(lookup):
        completed = lookup[entry_date]

        if not completed:
            run = 0
            previous_date = entry_date
            continue

        if previous_date is not None and (entry_date - previous_date).days == 1:
            run += 1
        else:
            run = 1

        longest = max(longest, run)
        previous_date = entry_date

    current = 0
    cursor = reference_date

    while lookup.get(cursor) is True:
        current += 1
        cursor -= timedelta(days=1)

    return current, longest


def _effective_period(
    task: Task,
    start_date: date,
    end_date: date,
) -> tuple[date, date]:
    """Restrict a requested period to the task's lifecycle."""
    if start_date > end_date:
        raise InvalidDateError("Statistics start date cannot be after end date.")

    effective_start = max(
        start_date,
        task.created_date,
    )

    effective_end = end_date

    if task.archived_date is not None:
        effective_end = min(
            effective_end,
            task.archived_date,
        )

    return effective_start, effective_end


def _streak_reference_date(
    task: Task,
    requested_end: date,
) -> date:
    """Return the latest date on which the task could have an active streak."""
    if task.archived_date is None:
        return requested_end

    return min(
        requested_end,
        task.archived_date,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_task_fields(
    name: str,
    cutoff_message: str,
) -> None:
    """Validate user-provided task fields."""
    if not name:
        raise InvalidTaskError("Task name cannot be empty.")

    if len(name) > MAX_NAME_LENGTH:
        raise InvalidTaskError(f"Task name must be at most {MAX_NAME_LENGTH} characters.")

    if not cutoff_message:
        raise InvalidTaskError("Cutoff message cannot be empty.")

    if len(cutoff_message) > MAX_CUTOFF_LENGTH:
        raise InvalidTaskError(f"Cutoff message must be at most {MAX_CUTOFF_LENGTH} characters.")


def _validate_days(days: int) -> None:
    """Validate a statistics window."""
    if days <= 0:
        raise InvalidDateError("Statistics period must contain at least one day.")


def _validate_date_range(
    from_date: date,
    to_date: date,
) -> None:
    """Validate an inclusive date range."""
    if from_date > to_date:
        raise InvalidDateError("Start date cannot be after end date.")
