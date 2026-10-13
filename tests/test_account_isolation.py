
"""
BridgeLab V13 — Cross-Account Security Tests

Tests participant ownership and review locks
using an isolated temporary database.

Does not alter existing BridgeLab project records.
"""

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform"))

import app_core
import file_manager
from app import app


class AccountIsolationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        self.addCleanup(self.temp.cleanup)  

        self.folder = Path(self.temp.name)
        self.database = self.folder / "test.db"
        self.uploads = self.folder / "uploads"
        self.uploads.mkdir()

        # Redirect BOTH application modules to
        # temporary files instead of real user data.
        for module, attribute, value in [
            (app_core, "DB_PATH", self.database),
            (app_core, "UPLOADS", self.uploads),
            (file_manager, "DATABASE", self.database),
            (file_manager, "UPLOADS", self.uploads),
        ]:
            mocked = patch.object(module, attribute, value)
            mocked.start()
            self.addCleanup(mocked.stop)

        with sqlite3.connect(self.database) as db:
            db.executescript("""
                CREATE TABLE participant_accounts (
                    id INTEGER PRIMARY KEY,
                    username TEXT
                );

                CREATE TABLE challenges (
                    id INTEGER PRIMARY KEY,
                    status TEXT,
                    deadline TEXT
                );

                CREATE TABLE challenge_submissions (
                    id INTEGER PRIMARY KEY,
                    participant_id INTEGER,
                    challenge_id INTEGER,
                    review_status TEXT
                );

                CREATE TABLE submission_files (
                    id INTEGER PRIMARY KEY,
                    submission_id INTEGER,
                    stored_name TEXT,
                    original_name TEXT,
                    size_bytes INTEGER
                );

                INSERT INTO participant_accounts
                VALUES (1, 'fictional_A');

                INSERT INTO participant_accounts
                VALUES (2, 'fictional_B');

                INSERT INTO challenges
                VALUES (1, 'Open', '2099-12-31');

                INSERT INTO challenge_submissions
                VALUES (1, 1, 1, 'Submitted');

                INSERT INTO submission_files
                VALUES
                (1, 1, 'a_test.txt', 'a_test.txt', 10),
                (2, 1, 'a_backup.txt', 'a_backup.txt', 10);
            """)

        (self.uploads / "a_test.txt").write_text(
            "Test file A"
        )
        (self.uploads / "a_backup.txt").write_text(
            "Backup file"
        )

        self.client = app.test_client()

    def login(self, participant_id, role="participant"):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["role"] = role
            sess["user_id"] = participant_id
            sess["_csrf"] = "test-security-token"

    def remove(self, file_id):
        return self.client.post(
            f"/files/{file_id}/remove",
            data={"_csrf": "test-security-token"},
            follow_redirects=False,
        )

    def test_owner_can_download_file(self):
        self.login(1)

        response = self.client.get(
            "/participant/file/1"
        )

        self.assertEqual(response.status_code, 200)

    def test_other_participant_cannot_download(self):
        self.login(2)

        response = self.client.get(
            "/participant/file/1"
        )

        self.assertEqual(response.status_code, 404)

    def test_other_participant_cannot_remove(self):
        self.login(2)

        response = self.remove(1)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            (self.uploads / "a_test.txt").exists()
        )

    def test_owner_can_remove_when_editable(self):
        self.login(1)

        response = self.remove(1)

        self.assertEqual(response.status_code, 302)

        with sqlite3.connect(self.database) as db:
            remaining = db.execute(
                "SELECT COUNT(*) FROM submission_files"
            ).fetchone()[0]

        self.assertEqual(remaining, 1)
        self.assertFalse(
            (self.uploads / "a_test.txt").exists()
        )

    def test_final_file_cannot_be_removed(self):
        with sqlite3.connect(self.database) as db:
            db.execute(
                "DELETE FROM submission_files WHERE id=2"
            )

        self.login(1)

        response = self.remove(1)

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            (self.uploads / "a_test.txt").exists()
        )

    def test_reviewed_submission_is_locked(self):
        with sqlite3.connect(self.database) as db:
            db.execute(
                """
                UPDATE challenge_submissions
                SET review_status='Reviewed'
                WHERE id=1
                """
            )

        self.login(1)

        response = self.remove(1)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            (self.uploads / "a_test.txt").exists()
        )

    def test_admin_cannot_use_participant_remove(self):
        self.login(1, role="admin")

        response = self.remove(1)

        self.assertEqual(response.status_code, 403)

    def test_invalid_csrf_is_rejected(self):
        self.login(1)

        response = self.client.post(
            "/files/1/remove",
            data={"_csrf": "invalid"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            (self.uploads / "a_test.txt").exists()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
