"""Repository layer — all SQL access lives here."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime

from life_ledger.domain.models import DailyEntry, Task


class TaskRepository:
    """Persistence operations for Task entities."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, name: str, cutoff_message: str) -> Task:
        """Persist and return a new task."""
        now = _utc_now()

        cursor = self._connection.execute(
            """
            INSERT INTO tasks (
                name,
                cutoff_message,
                created_at,
                archived_at
            )
            VALUES (?, ?, ?, NULL)
            """,
            (
                name,
                cutoff_message,
                _serialize_datetime(now),
            ),
        )

        task_id = cursor.lastrowid

        if task_id is None:
            raise RuntimeError("Failed to obtain the created task ID.")

        task = self.get_by_id(task_id)

        if task is None:
            raise RuntimeError(f"Task {task_id} was inserted but could not be retrieved.")

        return task

    def get_by_id(self, task_id: int) -> Task | None:
        """Return a task by its stable identifier."""
        row = self._connection.execute(
            """
            SELECT
                id,
                name,
                cutoff_message,
                created_at,
                archived_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        ).fetchone()

        return _task_from_row(row) if row is not None else None

    def get_by_name(self, name: str) -> Task | None:
        """Return a task by exact case-insensitive name."""
        row = self._connection.execute(
            """
            SELECT
                id,
                name,
                cutoff_message,
                created_at,
                archived_at
            FROM tasks
            WHERE name = ? COLLATE NOCASE
            ORDER BY archived_at IS NOT NULL, id DESC
            LIMIT 1
            """,
            (name,),
        ).fetchone()

        return _task_from_row(row) if row is not None else None

    def list_active(self) -> list[Task]:
        """Return all active tasks ordered by name."""
        rows = self._connection.execute(
            """
            SELECT
                id,
                name,
                cutoff_message,
                created_at,
                archived_at
            FROM tasks
            WHERE archived_at IS NULL
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()

        return [_task_from_row(row) for row in rows]

    def list_all(self) -> list[Task]:
        """Return all tasks, including archived tasks."""
        rows = self._connection.execute(
            """
            SELECT
                id,
                name,
                cutoff_message,
                created_at,
                archived_at
            FROM tasks
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()

        return [_task_from_row(row) for row in rows]

    def update(
        self,
        task_id: int,
        name: str,
        cutoff_message: str,
    ) -> Task:
        """Update a task and return its new state."""
        cursor = self._connection.execute(
            """
            UPDATE tasks
            SET
                name = ?,
                cutoff_message = ?
            WHERE id = ?
            """,
            (
                name,
                cutoff_message,
                task_id,
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(f"Task {task_id} could not be updated because it does not exist.")

        task = self.get_by_id(task_id)

        if task is None:
            raise RuntimeError(f"Task {task_id} was updated but could not be retrieved.")

        return task

    def archive(self, task_id: int) -> Task:
        """Archive a task while preserving its historical records."""
        now = _serialize_datetime(_utc_now())

        cursor = self._connection.execute(
            """
            UPDATE tasks
            SET archived_at = ?
            WHERE id = ?
              AND archived_at IS NULL
            """,
            (now, task_id),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Task {task_id} could not be archived because it is missing or already archived."
            )

        task = self.get_by_id(task_id)

        if task is None:
            raise RuntimeError(f"Task {task_id} was archived but could not be retrieved.")

        return task

    def restore(self, task_id: int) -> Task:
        """Restore an archived task."""
        cursor = self._connection.execute(
            """
            UPDATE tasks
            SET archived_at = NULL
            WHERE id = ?
              AND archived_at IS NOT NULL
            """,
            (task_id,),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Task {task_id} could not be restored because it is missing or already active."
            )

        task = self.get_by_id(task_id)

        if task is None:
            raise RuntimeError(f"Task {task_id} was restored but could not be retrieved.")

        return task


class EntryRepository:
    """Persistence operations for daily tracking entries."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(
        self,
        task_id: int,
        entry_date: date,
        completed: bool,
    ) -> DailyEntry:
        """Insert or update a daily entry."""
        now = _serialize_datetime(_utc_now())
        date_value = entry_date.isoformat()

        self._connection.execute(
            """
            INSERT INTO daily_entries (
                task_id,
                date,
                completed,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(task_id, date)
            DO UPDATE SET
                completed = excluded.completed,
                updated_at = excluded.updated_at
            """,
            (
                task_id,
                date_value,
                int(completed),
                now,
                now,
            ),
        )

        entry = self.get(task_id, entry_date)

        if entry is None:
            raise RuntimeError("Daily entry was persisted but could not be retrieved.")

        return entry

    def get(
        self,
        task_id: int,
        entry_date: date,
    ) -> DailyEntry | None:
        """Return a daily entry for a task/date pair."""
        row = self._connection.execute(
            """
            SELECT
                task_id,
                date,
                completed,
                created_at,
                updated_at
            FROM daily_entries
            WHERE task_id = ?
              AND date = ?
            """,
            (
                task_id,
                entry_date.isoformat(),
            ),
        ).fetchone()

        return _entry_from_row(row) if row is not None else None

    def list_for_task(
        self,
        task_id: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[DailyEntry]:
        """Return task entries within an optional inclusive date range."""
        conditions = ["task_id = ?"]
        parameters: list[object] = [task_id]

        if from_date is not None:
            conditions.append("date >= ?")
            parameters.append(from_date.isoformat())

        if to_date is not None:
            conditions.append("date <= ?")
            parameters.append(to_date.isoformat())

        if from_date is not None and to_date is not None:
            if from_date > to_date:
                raise ValueError("from_date cannot be after to_date.")

        where_clause = " AND ".join(conditions)

        rows = self._connection.execute(
            f"""
            SELECT
                task_id,
                date,
                completed,
                created_at,
                updated_at
            FROM daily_entries
            WHERE {where_clause}
            ORDER BY date DESC
            """,
            parameters,
        ).fetchall()

        return [_entry_from_row(row) for row in rows]

    def list_for_date(self, entry_date: date) -> list[DailyEntry]:
        """Return all entries recorded for a calendar date."""
        rows = self._connection.execute(
            """
            SELECT
                task_id,
                date,
                completed,
                created_at,
                updated_at
            FROM daily_entries
            WHERE date = ?
            ORDER BY task_id
            """,
            (entry_date.isoformat(),),
        ).fetchall()

        return [_entry_from_row(row) for row in rows]

    def get_period_stats(
        self,
        task_id: int,
        from_date: date,
        to_date: date,
    ) -> tuple[int, int]:
        """Return completed and missed counts for an inclusive date range."""
        if from_date > to_date:
            raise ValueError("from_date cannot be after to_date.")

        row = self._connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END),
                    0
                ) AS completed,
                COALESCE(
                    SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END),
                    0
                ) AS missed
            FROM daily_entries
            WHERE task_id = ?
              AND date >= ?
              AND date <= ?
            """,
            (
                task_id,
                from_date.isoformat(),
                to_date.isoformat(),
            ),
        ).fetchone()

        if row is None:
            return 0, 0

        return int(row["completed"]), int(row["missed"])

    def get_all_entries_for_task(
        self,
        task_id: int,
    ) -> list[DailyEntry]:
        """Return all entries for a task ordered oldest first."""
        rows = self._connection.execute(
            """
            SELECT
                task_id,
                date,
                completed,
                created_at,
                updated_at
            FROM daily_entries
            WHERE task_id = ?
            ORDER BY date ASC
            """,
            (task_id,),
        ).fetchall()

        return [_entry_from_row(row) for row in rows]


# ---------------------------------------------------------------------------
# SQLite → domain conversion
# ---------------------------------------------------------------------------


def _task_from_row(row: sqlite3.Row) -> Task:
    """Convert a SQLite task row into a domain Task."""
    return Task(
        id=int(row["id"]),
        name=str(row["name"]),
        cutoff_message=str(row["cutoff_message"]),
        created_at=_parse_datetime(row["created_at"]),
        archived_at=(
            _parse_datetime(row["archived_at"]) if row["archived_at"] is not None else None
        ),
    )


def _entry_from_row(row: sqlite3.Row) -> DailyEntry:
    """Convert a SQLite entry row into a domain DailyEntry."""
    return DailyEntry(
        task_id=int(row["task_id"]),
        date=date.fromisoformat(str(row["date"])),
        completed=bool(row["completed"]),
        created_at=_parse_datetime(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
    )


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _serialize_datetime(value: datetime) -> str:
    """Serialize a datetime as a normalized UTC ISO-8601 timestamp."""
    if value.tzinfo is None:
        raise ValueError("Cannot serialize a naive datetime.")

    return value.astimezone(UTC).isoformat(timespec="milliseconds")


def _parse_datetime(value: str) -> datetime:
    """Parse a stored ISO-8601 timestamp and return a timezone-aware datetime."""
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError("Stored timestamp is missing timezone information.")

    return parsed.astimezone(UTC)
