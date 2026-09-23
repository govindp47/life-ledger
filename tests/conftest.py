"""Shared test fixtures."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Generator

import pytest

from life_ledger.domain.models import Task
from life_ledger.domain.services import StatsService, TaskService, TrackingService
from life_ledger.storage.migrations import apply_migrations
from life_ledger.storage.repositories import EntryRepository, TaskRepository


@pytest.fixture
def conn() -> Generator[sqlite3.Connection, None, None]:
    """Provide an in-memory SQLite database with the current schema."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        apply_migrations(connection)
        yield connection
    finally:
        connection.close()


@pytest.fixture
def task_repo(conn: sqlite3.Connection) -> TaskRepository:
    """Provide a task repository backed by the test database."""
    return TaskRepository(conn)


@pytest.fixture
def entry_repo(conn: sqlite3.Connection) -> EntryRepository:
    """Provide an entry repository backed by the test database."""
    return EntryRepository(conn)


@pytest.fixture
def task_svc(task_repo: TaskRepository) -> TaskService:
    """Provide a task service backed by the test database."""
    return TaskService(task_repo)


@pytest.fixture
def tracking_svc(
    task_repo: TaskRepository,
    entry_repo: EntryRepository,
) -> TrackingService:
    """Provide a tracking service backed by the test database."""
    return TrackingService(task_repo, entry_repo)


@pytest.fixture
def stats_svc(
    task_repo: TaskRepository,
    entry_repo: EntryRepository,
) -> StatsService:
    """Provide a statistics service backed by the test database."""
    return StatsService(task_repo, entry_repo)


@pytest.fixture
def create_task(
    task_svc: TaskService,
) -> Callable[[str, str], Task]:
    """Create a task with arbitrary test-specific data."""

    def factory(name: str, cutoff_message: str) -> Task:
        return task_svc.create_task(name, cutoff_message)

    return factory


@pytest.fixture
def exercise_task(task_svc: TaskService) -> Task:
    """Provide a standard exercise task for tests."""
    return task_svc.create_task(
        "Exercise",
        "At least 30 minutes of physical activity",
    )


@pytest.fixture
def learning_task(task_svc: TaskService) -> Task:
    """Provide a standard learning task for tests."""
    return task_svc.create_task(
        "Learning",
        "At least 45 minutes of focused learning",
    )
