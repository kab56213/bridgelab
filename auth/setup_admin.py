
from pathlib import Path
from getpass import getpass
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "instance" / "bridgelab.db"

sys.path.insert(0, str(ROOT))

from auth.security import hash_password


def setup_admin():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 45)
    print("BRIDGELAB ADMIN ACCOUNT SETUP")
    print("=" * 45)

    username = input("Admin username: ").strip()

    if not (
        3 <= len(username) <= 40
        and all(c.isalnum() or c in "_-" for c in username)
    ):
        print("Invalid username.")
        return

    password = getpass("Admin password (12+ characters): ")
    confirm = getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match.")
        return

    try:
        password_hash = hash_password(password)
    except ValueError as error:
        print(error)
        return

    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        existing = db.execute(
            "SELECT id FROM admins WHERE username = ?",
            (username,)
        ).fetchone()

        if existing:
            print("This administrator already exists.")
            return

        db.execute(
            """
            INSERT INTO admins (username, password_hash)
            VALUES (?, ?)
            """,
            (username, password_hash)
        )

        db.commit()

    print()
    print("Administrator account created successfully.")
    print("Password stored as a secure hash.")


if __name__ == "__main__":
    setup_admin()
