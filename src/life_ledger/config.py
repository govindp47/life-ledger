"""LifeLedger application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)

_ENV_DB_DIR = "LIFE_LEDGER_DB"
_DATA_DIR_NAME = ".life-ledger"
_DB_NAME = "tracker.db"


def get_data_dir() -> Path:
    """Return the directory used to store LifeLedger user data.

    ``LIFE_LEDGER_DB`` may override the database file location. When the
    override is set, its parent directory is considered the data directory.

    The returned directory is created if it does not already exist.
    """
    override = os.getenv(_ENV_DB_DIR)

    if override:
        data_dir = Path(override).expanduser()
    else:
        data_dir = Path.home()

    data_dir = data_dir / _DATA_DIR_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    """Return the SQLite database path.

    By default the database is stored at:

        ~/.life-ledger/tracker.db

    ``LIFE_LEDGER_DB`` can be used to override the complete database path,
    which is useful for tests and custom installations.
    """
    return get_data_dir() / _DB_NAME
