
import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform"))

from upload_security import (
    validate_filename,
    validate_upload_bytes,
)


def make_zip(files):
    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer, "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)

    return buffer.getvalue()


class ExtendedUploadTests(unittest.TestCase):

    def test_accept_python(self):
        valid, _ = validate_upload_bytes(
            "analysis.py",
            b"print('BridgeLab')"
        )
        self.assertTrue(valid)

    def test_accept_sql(self):
        valid, _ = validate_upload_bytes(
            "queries.sql",
            b"SELECT * FROM customers;"
        )
        self.assertTrue(valid)

    def test_accept_java(self):
        valid, _ = validate_upload_bytes(
            "Main.java",
            b"class Main {}"
        )
        self.assertTrue(valid)

    def test_accept_valid_zip(self):
        data = make_zip({
            "analysis.txt": "BridgeLab project"
        })

        valid, _ = validate_upload_bytes(
            "project.zip", data
        )
        self.assertTrue(valid)

    def test_reject_corrupt_zip(self):
        valid, _ = validate_upload_bytes(
            "project.zip",
            b"PK\x03\x04this-is-not-a-valid-zip"
        )
        self.assertFalse(valid)

    def test_reject_zip_traversal(self):
        data = make_zip({
            "../secret.txt": "unsafe"
        })

        valid, _ = validate_upload_bytes(
            "project.zip", data
        )
        self.assertFalse(valid)

    def test_reject_fake_docx(self):
        data = make_zip({
            "unrelated.txt": "Not a Word document"
        })

        valid, _ = validate_upload_bytes(
            "report.docx", data
        )
        self.assertFalse(valid)

    def test_reject_invalid_notebook(self):
        valid, _ = validate_upload_bytes(
            "work.ipynb",
            b'{"hello": "world"}'
        )
        self.assertFalse(valid)

    def test_reject_binary_text(self):
        valid, _ = validate_upload_bytes(
            "notes.txt",
            b"\x00\x01\x02"
        )
        self.assertFalse(valid)

    def test_accept_all_existing_extensions(self):
        extensions = [
            "pdf", "docx", "xlsx", "csv", "pptx",
            "png", "jpg", "jpeg", "py", "java",
            "sql", "ipynb", "zip", "txt"
        ]

        for ext in extensions:
            with self.subTest(extension=ext):
                valid, _ = validate_filename(
                    f"project.{ext}"
                )
                self.assertTrue(valid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
