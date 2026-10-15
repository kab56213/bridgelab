
"""
BridgeLab V13 — Database Connection Management

Ensures SQLite connections are closed after use.

Supports:
- Transaction commit
- Transaction rollback
- Automatic connection cleanup

Local demonstration only.
"""

import sqlite3
from contextlib import contextmanager


@contextmanager
def database_connection(database_path, timeout=10):
    """
    Open, manage, and close a SQLite connection.

    Usage:

        with database_connection(DB_PATH) as db:
            db.execute("SELECT 1")
    """

    connection = sqlite3.connect(
        database_path,
        timeout=timeout
    )

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")

        with connection:
            yield connection

    finally:
        connection.close()


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "test.db"

        with database_connection(db_path) as db:
            db.execute(
                "CREATE TABLE example (id INTEGER)"
            )
            db.execute(
                "INSERT INTO example VALUES (1)"
            )

        with database_connection(db_path) as db:
            row = db.execute(
                "SELECT COUNT(*) AS total FROM example"
            ).fetchone()

        assert row["total"] == 1

        print(
            "PASS: Database connection and "
            "transaction management."
        )
