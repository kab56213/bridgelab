
"""
BridgeLab V13 — Basic Access Security Tests

Tests:
- Unauthenticated users cannot open private resources.
- Unauthenticated users cannot download participant files.
- Unauthenticated users cannot remove project files.
- Unauthenticated users cannot access the administrator dashboard.

Uses Flask's local test client.
Does not modify project records.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform"))

from app import app


class BridgeLabSecurityTests(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_private_resources_require_login(self):
        response = self.client.get("/resources/2")
        self.assertEqual(response.status_code, 403)

    def test_participant_files_require_login(self):
        response = self.client.get(
            "/participant/file/1",
            follow_redirects=False
        )
        self.assertIn(response.status_code, (302, 303, 403))

    def test_file_removal_requires_login(self):
        response = self.client.post(
            "/files/1/remove",
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_dashboard_requires_login(self):
        response = self.client.get(
            "/",
            follow_redirects=False
        )
        self.assertIn(response.status_code, (302, 303))

    def test_participant_dashboard_requires_login(self):
        response = self.client.get(
            "/participant",
            follow_redirects=False
        )
        self.assertIn(response.status_code, (302, 303))


if __name__ == "__main__":
    unittest.main(verbosity=2)
