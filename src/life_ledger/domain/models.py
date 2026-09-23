"""Domain models — pure dataclasses, no framework dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Task:
    """A long-lived daily commitment tracked by LifeLedger."""

    id: int
    name: str
    cutoff_message: str
    created_at: datetime
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError("Task id must be positive.")

        if not self.name.strip():
            raise ValueError("Task name must not be empty.")

        if not self.cutoff_message.strip():
            raise ValueError("Task cutoff message must not be empty.")

        if self.archived_at is not None and self.archived_at < self.created_at:
            raise ValueError("Task cannot be archived before it was created.")

    @property
    def is_active(self) -> bool:
        """Return whether the task is currently active."""
        return self.archived_at is None

    @property
    def created_date(self) -> date:
        """Return the calendar date on which the task was created."""
        return self.created_at.date()

    @property
    def archived_date(self) -> date | None:
        """Return the calendar date on which the task was archived."""
        return self.archived_at.date() if self.archived_at else None


@dataclass(frozen=True, slots=True)
class DailyEntry:
    """A user's explicit YES/NO decision for a task on a calendar date."""

    task_id: int
    date: date
    completed: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.task_id <= 0:
            raise ValueError("Daily entry task_id must be positive.")

        if self.updated_at < self.created_at:
            raise ValueError("Daily entry cannot be updated before it was created.")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class Trend(Enum):
    """Direction of change between comparable statistics periods."""

    UP = "↑"
    DOWN = "↓"
    FLAT = "→"
    INSUFFICIENT = "—"


@dataclass(frozen=True, slots=True)
class TaskStats:
    """Statistics for a single task over a defined calendar period."""

    task: Task
    start_date: date
    end_date: date
    completed: int
    missed: int
    recorded: int
    completion_rate: float | None
    current_streak: int
    longest_streak: int
    recent_7d_rate: float | None
    recent_30d_rate: float | None
    recent_90d_rate: float | None
    trend: Trend

    @property
    def period_days(self) -> int:
        """Return the number of calendar days in the statistics period."""
        return (self.end_date - self.start_date).days + 1

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("Statistics end date cannot precede start date.")

        if self.completed < 0:
            raise ValueError("Completed count cannot be negative.")

        if self.missed < 0:
            raise ValueError("Missed count cannot be negative.")

        if self.recorded != self.completed + self.missed:
            raise ValueError("Recorded count must equal completed + missed.")

        if self.current_streak < 0:
            raise ValueError("Current streak cannot be negative.")

        if self.longest_streak < 0:
            raise ValueError("Longest streak cannot be negative.")

        if self.current_streak > self.longest_streak:
            raise ValueError("Current streak cannot exceed longest streak.")

        if self.completion_rate is None:
            if self.recorded != 0:
                raise ValueError("Completion rate must be present when entries are recorded.")
        else:
            if self.recorded == 0:
                raise ValueError("Completion rate must be None when no entries are recorded.")
            if not 0.0 <= self.completion_rate <= 1.0:
                raise ValueError("Completion rate must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class OverallStats:
    """Aggregate statistics across active tasks for a calendar period."""

    start_date: date
    end_date: date
    task_stats: tuple[TaskStats, ...]
    avg_rate: float | None
    min_rate: float | None
    max_rate: float | None
    spread: float | None
    tracked_days: int
    total_days: int

    @property
    def period_days(self) -> int:
        """Return the number of calendar days in the statistics period."""
        return (self.end_date - self.start_date).days + 1

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("Statistics end date cannot precede start date.")

        if self.total_days != self.period_days:
            raise ValueError("total_days must match the statistics date range.")

        if self.tracked_days < 0:
            raise ValueError("Tracked days cannot be negative.")

        if self.tracked_days > self.total_days:
            raise ValueError("Tracked days cannot exceed total days.")

        rates = [
            stats.completion_rate for stats in self.task_stats if stats.completion_rate is not None
        ]

        if not rates:
            if any(
                value is not None
                for value in (self.avg_rate, self.min_rate, self.max_rate, self.spread)
            ):
                raise ValueError("Aggregate rates must be None when no task has recorded data.")
            return

        if self.avg_rate is None:
            raise ValueError("Average rate must be present when task rates exist.")

        if self.min_rate is None or self.max_rate is None:
            raise ValueError("Minimum and maximum rates must be present when task rates exist.")

        if not 0.0 <= self.avg_rate <= 1.0:
            raise ValueError("Average rate must be between 0 and 1.")

        if not 0.0 <= self.min_rate <= 1.0:
            raise ValueError("Minimum rate must be between 0 and 1.")

        if not 0.0 <= self.max_rate <= 1.0:
            raise ValueError("Maximum rate must be between 0 and 1.")

        if self.min_rate > self.max_rate:
            raise ValueError("Minimum rate cannot exceed maximum rate.")

        if self.spread is not None and not 0.0 <= self.spread <= 1.0:
            raise ValueError("Spread must be between 0 and 1.")

        if len(rates) < 2:
            if self.spread is not None:
                raise ValueError("Spread must be None when fewer than two tasks have data.")
        else:
            if self.spread is None:
                raise ValueError("Spread must be present when at least two tasks have data.")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LifeLedgerError(Exception):
    """Base exception for LifeLedger domain/application errors."""


class TaskNotFoundError(LifeLedgerError):
    """Raised when a requested task does not exist."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Task not found: {name!r}")
        self.name = name


class TaskAlreadyExistsError(LifeLedgerError):
    """Raised when an active task with the same name already exists."""

    def __init__(self, name: str) -> None:
        super().__init__(f"A task named {name!r} already exists.")
        self.name = name


class ArchivedTaskError(LifeLedgerError):
    """Raised when an operation requires an active task."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Task {name!r} is archived. Restore it first.")
        self.name = name


class NotArchivedError(LifeLedgerError):
    """Raised when restoring a task that is already active."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Task {name!r} is not archived.")
        self.name = name


class InvalidTaskError(LifeLedgerError):
    """Raised when task data violates a domain rule."""


class InvalidDateError(LifeLedgerError):
    """Raised when a supplied date is invalid."""
