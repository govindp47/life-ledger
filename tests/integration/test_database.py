"""Integration tests — SQLite schema, migrations, persistence, constraints."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from life_ledger.domain.services import TaskService, TrackingService
from life_ledger.storage.migrations import apply_migrations
from life_ledger.storage.repositories import EntryRepository, TaskRepository

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)

# ---------------------------------------------------------------------------
# Schema / migrations
# ---------------------------------------------------------------------------


class TestSchema:
    """Tests for database schema creation and migration behavior."""

    @staticmethod
    def _get_tables(
        conn: sqlite3.Connection,
    ) -> set[str]:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

        return {str(row[0]) for row in rows}

    @staticmethod
    def _get_indexes(
        conn: sqlite3.Connection,
        table_name: str,
    ) -> set[str]:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = ?
            """,
            (table_name,),
        ).fetchall()

        return {str(row[0]) for row in rows}

    def test_schema_creates_tasks_table(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        assert "tasks" in self._get_tables(conn)

    def test_schema_creates_daily_entries_table(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        assert "daily_entries" in self._get_tables(conn)

    def test_schema_creates_schema_version_table(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        assert "schema_version" in self._get_tables(conn)

    def test_tasks_have_active_name_unique_index(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        indexes = self._get_indexes(conn, "tasks")

        assert "idx_tasks_active_name" in indexes

    def test_daily_entries_have_date_index(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        indexes = self._get_indexes(
            conn,
            "daily_entries",
        )

        assert "idx_daily_entries_date" in indexes

    def test_migration_is_idempotent(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        """Applying migrations repeatedly must not change the schema."""
        apply_migrations(conn)
        apply_migrations(conn)

        rows = conn.execute(
            """
            SELECT version, description
            FROM schema_version
            ORDER BY version
            """
        ).fetchall()

        assert len(rows) == 1
        assert rows[0][0] == 1
        assert rows[0][1] == "initial schema"

    def test_schema_version_is_recorded(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        version = conn.execute(
            """
            SELECT MAX(version)
            FROM schema_version
            """
        ).fetchone()[0]

        assert version == 1

    def test_unsupported_schema_version_is_rejected(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        conn.execute(
            """
            INSERT INTO schema_version (
                version,
                description,
                applied_at
            )
            VALUES (?, ?, ?)
            """,
            (
                999,
                "unsupported test version",
                "2026-09-22T12:00:00+00:00",
            ),
        )

        with pytest.raises(
            RuntimeError,
            match="unsupported schema version",
        ):
            apply_migrations(conn)


# ---------------------------------------------------------------------------
# Task persistence
# ---------------------------------------------------------------------------


class TestTaskPersistence:
    """Tests for TaskRepository persistence behavior."""

    def test_create_and_retrieve_task(
        self,
        task_repo: TaskRepository,
    ) -> None:
        created = task_repo.create(
            "Exercise",
            "30 min",
        )

        fetched = task_repo.get_by_id(
            created.id,
        )

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Exercise"
        assert fetched.cutoff_message == "30 min"
        assert fetched.is_active

    def test_get_by_id_returns_none_for_missing_task(
        self,
        task_repo: TaskRepository,
    ) -> None:
        assert task_repo.get_by_id(999) is None

    def test_get_by_name_is_case_insensitive(
        self,
        task_repo: TaskRepository,
    ) -> None:
        task_repo.create(
            "Exercise",
            "30 min",
        )

        fetched = task_repo.get_by_name(
            "EXERCISE",
        )

        assert fetched is not None
        assert fetched.name == "Exercise"

    def test_get_by_name_prefers_active_task(
        self,
        task_repo: TaskRepository,
    ) -> None:
        archived = task_repo.create(
            "Exercise",
            "30 min",
        )

        task_repo.archive(
            archived.id,
        )

        active = task_repo.create(
            "Exercise",
            "45 min",
        )

        fetched = task_repo.get_by_name(
            "Exercise",
        )

        assert fetched is not None
        assert fetched.id == active.id
        assert fetched.is_active

    def test_active_duplicate_name_violates_constraint(
        self,
        task_repo: TaskRepository,
    ) -> None:
        task_repo.create(
            "Exercise",
            "30 min",
        )

        with pytest.raises(sqlite3.IntegrityError):
            task_repo.create(
                "Exercise",
                "Different cutoff",
            )

    def test_active_duplicate_name_is_case_insensitive(
        self,
        task_repo: TaskRepository,
    ) -> None:
        task_repo.create(
            "Exercise",
            "30 min",
        )

        with pytest.raises(sqlite3.IntegrityError):
            task_repo.create(
                "exercise",
                "Different cutoff",
            )

    def test_archived_name_can_be_reused(
        self,
        task_repo: TaskRepository,
    ) -> None:
        original = task_repo.create(
            "Exercise",
            "30 min",
        )

        task_repo.archive(
            original.id,
        )

        replacement = task_repo.create(
            "Exercise",
            "45 min",
        )

        assert replacement.id != original.id
        assert replacement.is_active

    def test_archive_sets_archived_at(
        self,
        task_repo: TaskRepository,
    ) -> None:
        created = task_repo.create(
            "Exercise",
            "30 min",
        )

        archived = task_repo.archive(
            created.id,
        )

        assert archived.archived_at is not None
        assert archived.archived_at >= archived.created_at

    def test_restore_clears_archived_at(
        self,
        task_repo: TaskRepository,
    ) -> None:
        created = task_repo.create(
            "Exercise",
            "30 min",
        )

        task_repo.archive(
            created.id,
        )

        restored = task_repo.restore(
            created.id,
        )

        assert restored.archived_at is None
        assert restored.is_active

    def test_list_active_excludes_archived(
        self,
        task_repo: TaskRepository,
    ) -> None:
        exercise = task_repo.create(
            "Exercise",
            "30 min",
        )

        task_repo.create(
            "Learning",
            "45 min",
        )

        task_repo.archive(
            exercise.id,
        )

        active = task_repo.list_active()

        assert {task.name for task in active} == {
            "Learning",
        }

    def test_list_all_includes_archived(
        self,
        task_repo: TaskRepository,
    ) -> None:
        exercise = task_repo.create(
            "Exercise",
            "30 min",
        )

        learning = task_repo.create(
            "Learning",
            "45 min",
        )

        task_repo.archive(
            exercise.id,
        )

        all_tasks = task_repo.list_all()

        assert {task.id for task in all_tasks} == {
            exercise.id,
            learning.id,
        }

        archived = next(task for task in all_tasks if task.id == exercise.id)

        assert archived.is_active is False

    def test_archive_preserves_task_data(
        self,
        task_repo: TaskRepository,
    ) -> None:
        created = task_repo.create(
            "Exercise",
            "At least 30 minutes",
        )

        archived = task_repo.archive(
            created.id,
        )

        assert archived.id == created.id
        assert archived.name == "Exercise"
        assert archived.cutoff_message == ("At least 30 minutes")

    def test_update_persists_name_and_cutoff(
        self,
        task_repo: TaskRepository,
    ) -> None:
        created = task_repo.create(
            "Exercise",
            "30 min",
        )

        updated = task_repo.update(
            created.id,
            "Exercise Daily",
            "45 min",
        )

        assert updated.id == created.id
        assert updated.name == "Exercise Daily"
        assert updated.cutoff_message == "45 min"

    def test_update_missing_task_raises(
        self,
        task_repo: TaskRepository,
    ) -> None:
        with pytest.raises(
            RuntimeError,
            match="could not be updated",
        ):
            task_repo.update(
                999,
                "Exercise",
                "30 min",
            )


# ---------------------------------------------------------------------------
# Daily-entry persistence
# ---------------------------------------------------------------------------


class TestEntryPersistence:
    """Tests for DailyEntryRepository persistence behavior."""

    def test_upsert_creates_entry(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        entry = entry_repo.upsert(
            task.id,
            TODAY,
            True,
        )

        assert entry.task_id == task.id
        assert entry.completed is True
        assert entry.date == TODAY
        assert entry.created_at == entry.updated_at

    def test_upsert_updates_existing_entry(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        original = entry_repo.upsert(
            task.id,
            TODAY,
            False,
        )

        updated = entry_repo.upsert(
            task.id,
            TODAY,
            True,
        )

        assert updated.task_id == original.task_id
        assert updated.date == original.date
        assert updated.completed is True
        assert updated.created_at == original.created_at
        assert updated.updated_at >= original.updated_at

    def test_upsert_same_task_date_keeps_one_row(
        self,
        conn: sqlite3.Connection,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        entry_repo.upsert(
            task.id,
            TODAY,
            False,
        )

        entry_repo.upsert(
            task.id,
            TODAY,
            True,
        )

        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM daily_entries
            WHERE task_id = ?
              AND date = ?
            """,
            (
                task.id,
                TODAY.isoformat(),
            ),
        ).fetchone()[0]

        assert count == 1

    def test_primary_key_rejects_direct_duplicate_insert(
        self,
        conn: sqlite3.Connection,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        entry_repo.upsert(
            task.id,
            TODAY,
            True,
        )

        with pytest.raises(sqlite3.IntegrityError):
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
                    TODAY.isoformat(),
                    1,
                    "2026-09-22T12:00:00+00:00",
                    "2026-09-22T12:00:00+00:00",
                ),
            )

    def test_get_entry_returns_none_for_missing(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        result = entry_repo.get(
            task.id,
            YESTERDAY,
        )

        assert result is None

    def test_foreign_key_is_enforced(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
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
                    999,
                    TODAY.isoformat(),
                    1,
                    "2026-09-22T12:00:00+00:00",
                    "2026-09-22T12:00:00+00:00",
                ),
            )

    def test_completed_check_constraint_rejects_invalid_value(
        self,
        conn: sqlite3.Connection,
        task_repo: TaskRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        with pytest.raises(sqlite3.IntegrityError):
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
                    TODAY.isoformat(),
                    2,
                    "2026-09-22T12:00:00+00:00",
                    "2026-09-22T12:00:00+00:00",
                ),
            )

    def test_list_for_task_returns_entries_in_descending_date_order(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        entry_repo.upsert(
            task.id,
            YESTERDAY,
            False,
        )
        entry_repo.upsert(
            task.id,
            TODAY,
            True,
        )

        results = entry_repo.list_for_task(
            task.id,
        )

        assert [entry.date for entry in results] == [
            TODAY,
            YESTERDAY,
        ]

    def test_list_for_task_date_range_is_inclusive(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        entry_repo.upsert(
            task.id,
            YESTERDAY,
            False,
        )
        entry_repo.upsert(
            task.id,
            TODAY,
            True,
        )

        results = entry_repo.list_for_task(
            task.id,
            from_date=YESTERDAY,
            to_date=TODAY,
        )

        assert len(results) == 2

        dates = {entry.date for entry in results}

        assert dates == {
            YESTERDAY,
            TODAY,
        }

    def test_list_for_task_invalid_range_raises(
        self,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_repo.create(
            "Exercise",
            "30 min",
        )

        with pytest.raises(
            ValueError,
            match="from_date cannot be after to_date",
        ):
            entry_repo.list_for_task(
                task.id,
                from_date=TODAY,
                to_date=YESTERDAY,
            )

    def test_list_for_task_missing_task_returns_empty(
        self,
        entry_repo: EntryRepository,
    ) -> None:
        results = entry_repo.list_for_task(
            999,
        )

        assert results == []


# ---------------------------------------------------------------------------
# Repository / service interaction
# ---------------------------------------------------------------------------


class TestArchivalPreservesHistory:
    """Tests proving archive is lifecycle state, not deletion."""

    def test_archiving_task_preserves_entries(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_svc.create_task(
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

        task_svc.archive_task(
            "Exercise",
        )

        entries = entry_repo.list_for_task(
            task.id,
        )

        assert len(entries) == 2

        assert {entry.date for entry in entries} == {
            TODAY,
            YESTERDAY,
        }

    def test_archived_task_definition_remains_persisted(
        self,
        task_svc: TaskService,
        task_repo: TaskRepository,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        task_svc.archive_task(
            "Exercise",
        )

        persisted = task_repo.get_by_id(
            task.id,
        )

        assert persisted is not None
        assert persisted.id == task.id
        assert persisted.name == "Exercise"
        assert persisted.cutoff_message == "30 min"
        assert persisted.is_active is False
        assert persisted.archived_at is not None

    def test_restored_task_retains_historical_entries(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        entry_repo: EntryRepository,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            TODAY,
            True,
        )

        task_svc.archive_task(
            "Exercise",
        )

        task_svc.restore_task_by_id(
            task.id,
        )

        entries = entry_repo.list_for_task(
            task.id,
        )

        assert len(entries) == 1
        assert entries[0].task_id == task.id
        assert entries[0].date == TODAY
        assert entries[0].completed is True

    def test_archived_task_can_be_reused_without_deleting_history(
        self,
        task_svc: TaskService,
        tracking_svc: TrackingService,
        task_repo: TaskRepository,
        entry_repo: EntryRepository,
    ) -> None:
        original = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        tracking_svc.record_entry(
            "Exercise",
            YESTERDAY,
            True,
        )

        task_svc.archive_task(
            "Exercise",
        )

        replacement = task_svc.create_task(
            "Exercise",
            "45 min",
        )

        assert replacement.id != original.id

        original_entries = entry_repo.list_for_task(
            original.id,
        )

        replacement_entries = entry_repo.list_for_task(
            replacement.id,
        )

        assert len(original_entries) == 1
        assert original_entries[0].date == YESTERDAY
        assert original_entries[0].completed is True
        assert replacement_entries == []

        original_persisted = task_repo.get_by_id(
            original.id,
        )

        assert original_persisted is not None
        assert original_persisted.is_active is False
