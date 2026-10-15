
"""
BridgeLab V13 — Upload Integration Tests

Tests real Flask submission routes using fictional
accounts, a temporary database, and temporary files.

Does not modify the live BridgeLab demo database.
"""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform"))

import app_core
from app import app
from database import database_connection


class UploadIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        folder = Path(self.temp.name)
        self.database = folder / "test.db"
        self.uploads = folder / "uploads"
        self.uploads.mkdir()

        for attribute, value in [
            ("DB_PATH", self.database),
            ("UPLOADS", self.uploads),
        ]:
            p = patch.object(app_core, attribute, value)
            p.start()
            self.addCleanup(p.stop)

        with database_connection(self.database) as db:
            db.executescript("""
                CREATE TABLE participant_accounts (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL
                );

                CREATE TABLE challenges (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    status TEXT,
                    deadline TEXT
                );

                CREATE TABLE enrollments (
                    id INTEGER PRIMARY KEY,
                    participant_id INTEGER,
                    challenge_id INTEGER
                );

                CREATE TABLE challenge_submissions (
                    id INTEGER PRIMARY KEY,
                    participant_id INTEGER,
                    challenge_id INTEGER,
                    project_url TEXT,
                    review_status TEXT,
                    project_title TEXT,
                    description TEXT,
                    optional_url TEXT,
                    submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(participant_id, challenge_id)
                );

                CREATE TABLE submission_files (
                    id INTEGER PRIMARY KEY,
                    submission_id INTEGER,
                    stored_name TEXT UNIQUE,
                    original_name TEXT,
                    size_bytes INTEGER
                );

                INSERT INTO participant_accounts
                VALUES (1, 'fictional_participant');

                INSERT INTO challenges
                VALUES (
                    1,
                    'Temporary Upload Test',
                    'Open',
                    '2099-12-31'
                );

                INSERT INTO enrollments
                VALUES (1, 1, 1);
            """)

        self.client = app.test_client()

        with self.client.session_transaction() as sess:
            sess.clear()
            sess["role"] = "participant"
            sess["user_id"] = 1
            sess["_csrf"] = "integration-test-token"

    def submit(self, files, **overrides):
        data = {
            "_csrf": "integration-test-token",
            "challenge_id": "1",
            "project_title": "Fictional Test Project",
            "description": (
                "This is a fictional project used "
                "to test secure file submissions."
            ),
            "optional_url": "",
            "files": [
                (io.BytesIO(content), filename)
                for filename, content in files
            ],
        }

        data.update(overrides)

        return self.client.post(
            "/participant/submit",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=False,
        )

    def counts(self):
        with database_connection(self.database) as db:
            submissions = db.execute(
                "SELECT COUNT(*) FROM challenge_submissions"
            ).fetchone()[0]

            files = db.execute(
                "SELECT COUNT(*) FROM submission_files"
            ).fetchone()[0]

        return submissions, files

    def test_valid_upload_is_saved(self):
        response = self.submit([
            ("analysis.txt", b"BridgeLab test analysis")
        ])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counts(), (1, 1))

        self.assertEqual(
            len(list(self.uploads.iterdir())),
            1
        )

    def test_uploaded_file_can_be_downloaded(self):
        self.submit([
            ("analysis.txt", b"BridgeLab test analysis")
        ])

        with database_connection(self.database) as db:
            file_id = db.execute(
                "SELECT id FROM submission_files"
            ).fetchone()[0]

        response = self.client.get(
            f"/participant/file/{file_id}"
        )

        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_data(),
                b"BridgeLab test analysis"
            )
        finally:
            response.close()

    def test_executable_is_rejected(self):
        self.submit([
            ("malware.exe", b"not a real executable")
        ])

        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(
            len(list(self.uploads.iterdir())),
            0
        )

    def test_fake_pdf_is_rejected(self):
        self.submit([
            ("report.pdf", b"This is not a PDF")
        ])

        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(
            len(list(self.uploads.iterdir())),
            0
        )

    def test_mixed_upload_rolls_back(self):
        self.submit([
            ("valid.txt", b"Valid analysis"),
            ("fake.pdf", b"Invalid PDF contents"),
        ])

        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(
            len(list(self.uploads.iterdir())),
            0
        )

    def test_reviewed_submission_cannot_change(self):
        self.submit([
            ("original.txt", b"Original approved work")
        ])

        with database_connection(self.database) as db:
            db.execute("""
                UPDATE challenge_submissions
                SET review_status='Reviewed'
                WHERE participant_id=1
            """)

        before = self.counts()

        self.submit([
            ("replacement.txt", b"Unauthorized update")
        ])

        self.assertEqual(self.counts(), before)

        with database_connection(self.database) as db:
            row = db.execute("""
                SELECT project_title, review_status
                FROM challenge_submissions
                WHERE participant_id=1
            """).fetchone()

        self.assertEqual(row["review_status"], "Reviewed")
        self.assertEqual(
            row["project_title"],
            "Fictional Test Project"
        )

        self.assertEqual(
            len(list(self.uploads.iterdir())),
            1
        )


    def test_oversized_file_is_rejected(self):
        oversized = b"x" * (10 * 1024 * 1024 + 1)

        response = self.submit([
            ("oversized.txt", oversized)
        ])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(
            len(list(self.uploads.iterdir())),
            0
        )

    def test_too_many_files_are_rejected(self):
        files = [
            (f"file_{i}.txt", b"Test content")
            for i in range(6)
        ]

        response = self.submit(files)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(
            len(list(self.uploads.iterdir())),
            0
        )

    def test_existing_file_limit_is_enforced(self):
        first_batch = [
            (f"project_{i}.txt", b"Test content")
            for i in range(4)
        ]

        self.submit(first_batch)

        self.assertEqual(self.counts(), (1, 4))

        response = self.submit([
            ("extra_1.txt", b"More work"),
            ("extra_2.txt", b"More work")
        ])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counts(), (1, 4))
        self.assertEqual(
            len(list(self.uploads.iterdir())),
            4
        )


    def test_storage_failure_rolls_back_submission(self):
        from unittest.mock import patch
        from werkzeug.datastructures import FileStorage

        original_save = FileStorage.save
        save_count = 0

        def fail_on_second_save(storage, destination, *args, **kwargs):
            nonlocal save_count
            save_count += 1

            if save_count == 2:
                raise OSError("Simulated disk write failure")

            return original_save(
                storage, destination, *args, **kwargs
            )

        with patch.object(
            FileStorage, "save", fail_on_second_save
        ):
            response = self.submit([
                ("first.txt", b"First project file"),
                ("second.txt", b"Second project file"),
            ])

        self.assertEqual(response.status_code, 302)
        self.assertIn("Upload+failed", response.location)

        # The transaction should have rolled back.
        self.assertEqual(self.counts(), (0, 0))

        # No orphaned uploads should remain.
        self.assertEqual(
            list(self.uploads.iterdir()), []
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
