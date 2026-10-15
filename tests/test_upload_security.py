
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform"))

from upload_security import (
    validate_filename,
    validate_file_size,
    validate_file_signature,
    validate_upload,
)


class UploadSecurityTests(unittest.TestCase):

    def test_valid_pdf(self):
        valid, _ = validate_upload(
            "report.pdf",
            1024,
            b"%PDF-1.7\n"
        )
        self.assertTrue(valid)

    def test_reject_executable(self):
        valid, _ = validate_filename("virus.exe")
        self.assertFalse(valid)

    def test_reject_path_traversal(self):
        valid, _ = validate_filename("../../secret.pdf")
        self.assertFalse(valid)

    def test_reject_windows_path(self):
        valid, _ = validate_filename(
            r"..\..\secret.pdf"
        )
        self.assertFalse(valid)

    def test_reject_oversized_file(self):
        valid, _ = validate_file_size(
            11 * 1024 * 1024
        )
        self.assertFalse(valid)

    def test_reject_empty_file(self):
        valid, _ = validate_file_size(0)
        self.assertFalse(valid)

    def test_reject_disguised_pdf(self):
        valid, _ = validate_file_signature(
            "report.pdf",
            b"NOT A PDF FILE"
        )
        self.assertFalse(valid)

    def test_accept_python_project(self):
        valid, _ = validate_upload(
            "analysis.py",
            100,
            b"print('Hello BridgeLab')"
        )
        self.assertTrue(valid)

    def test_reject_unsupported_archive(self):
        valid, _ = validate_filename(
            "project.rar"
        )
        self.assertFalse(valid)

    def test_reject_missing_filename(self):
        valid, _ = validate_filename("")
        self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
