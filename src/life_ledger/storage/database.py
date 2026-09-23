"""SQLite connection and transaction management."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from life_ledger.storage.migrations import apply_migrations


@contextmanager
def get_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a configured SQLite connection.

    The connection is configured for:
    - foreign-key enforcement
    - WAL journaling
    - a short busy timeout
    - sqlite3.Row access

    The connection uses autocommit mode. Multi-statement operations should
    explicitly use the ``transaction`` context manager.
    """
    db_path = db_path.expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        db_path,
        timeout=5.0,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(
    connection: sqlite3.Connection,
) -> Generator[None, None, None]:
    """Execute multiple database operations atomically."""
    if connection.in_transaction:
        raise RuntimeError("Cannot start a nested database transaction.")

    connection.execute("BEGIN")

    try:
        yield
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def initialize_db(db_path: Path) -> None:
    """Create or migrate the database to the current schema."""
    with get_connection(db_path) as connection:
        apply_migrations(connection)
