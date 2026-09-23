"""SQLite schema migrations."""

from __future__ import annotations

import sqlite3

Migration = tuple[int, str, tuple[str, ...]]


MIGRATIONS: tuple[Migration, ...] = (
    (
        1,
        "initial schema",
        (
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE,
                cutoff_message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                archived_at TEXT
            )
            """,
            """
            CREATE UNIQUE INDEX idx_tasks_active_name
            ON tasks(name COLLATE NOCASE)
            WHERE archived_at IS NULL
            """,
            """
            CREATE TABLE daily_entries (
                task_id INTEGER NOT NULL
                    REFERENCES tasks(id),
                date TEXT NOT NULL,
                completed INTEGER NOT NULL
                    CHECK (completed IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (task_id, date)
            )
            """,
            """
            CREATE INDEX idx_daily_entries_date
            ON daily_entries(date)
            """,
        ),
    ),
)


def _validate_migrations() -> None:
    """Validate migration definitions before they are applied."""
    versions = [version for version, _, _ in MIGRATIONS]

    if versions != sorted(versions):
        raise RuntimeError("Database migrations must be ordered by version.")

    if len(versions) != len(set(versions)):
        raise RuntimeError("Database migration versions must be unique.")


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations atomically and in version order."""
    _validate_migrations()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )

    applied_versions = {
        row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")
    }

    known_versions = {version for version, _, _ in MIGRATIONS}
    unsupported_versions = applied_versions - known_versions

    if unsupported_versions:
        versions = ", ".join(str(version) for version in sorted(unsupported_versions))
        raise RuntimeError(f"Database contains unsupported schema version(s): {versions}")

    for version, description, statements in MIGRATIONS:
        if version in applied_versions:
            continue

        try:
            conn.execute("BEGIN")

            for statement in statements:
                conn.execute(statement)

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
                    version,
                    description,
                    _utc_now_iso(),
                ),
            )

            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds")
