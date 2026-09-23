"""CLI application context and service construction."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from life_ledger.config import get_db_path
from life_ledger.domain.services import StatsService, TaskService, TrackingService
from life_ledger.storage.database import get_connection
from life_ledger.storage.migrations import apply_migrations
from life_ledger.storage.repositories import EntryRepository, TaskRepository


@contextmanager
def database_connection() -> Generator[sqlite3.Connection, None, None]:
    """Open an initialized LifeLedger database connection."""
    db_path = get_db_path()

    with get_connection(db_path) as connection:
        apply_migrations(connection)
        yield connection


@contextmanager
def task_service() -> Generator[TaskService, None, None]:
    """Provide a task service for one CLI command."""
    with database_connection() as connection:
        yield TaskService(TaskRepository(connection))


@contextmanager
def tracking_service() -> Generator[TrackingService, None, None]:
    """Provide a tracking service for one CLI command."""
    with database_connection() as connection:
        yield TrackingService(
            TaskRepository(connection),
            EntryRepository(connection),
        )


@contextmanager
def stats_service() -> Generator[StatsService, None, None]:
    """Provide a statistics service for one CLI command."""
    with database_connection() as connection:
        yield StatsService(
            TaskRepository(connection),
            EntryRepository(connection),
        )
