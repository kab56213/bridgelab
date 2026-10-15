
"""
BridgeLab V13 — Upload Security
Version 2

Validates participant project uploads without saving them.

Supports:
PDF, Word, Excel, CSV, PowerPoint, PNG, JPG,
JPEG, Python, Java, SQL, Jupyter Notebook,
ZIP, and TXT.

This is file-format validation, not antivirus scanning.
"""

import io
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".csv", ".pptx",
    ".png", ".jpg", ".jpeg", ".py", ".java",
    ".sql", ".ipynb", ".zip", ".txt"
}

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES = 5
MAX_ARCHIVE_MEMBERS = 1000
MAX_ARCHIVE_UNCOMPRESSED = 100 * 1024 * 1024

SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
    ".zip": (b"PK\x03\x04",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}

OFFICE_REQUIRED_FILES = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}

TEXT_EXTENSIONS = {
    ".csv", ".txt", ".py", ".java", ".sql"
}


def validate_filename(filename):
    if not isinstance(filename, str):
        return False, "A valid filename is required."

    if not filename.strip():
        return False, "A filename is required."

    if "/" in filename or "\\" in filename:
        return False, "File paths are not permitted."

    if "\x00" in filename:
        return False, "Invalid filename."

    cleaned = secure_filename(filename)

    if not cleaned or cleaned in {".", ".."}:
        return False, "Invalid filename."

    if len(cleaned) > 150:
        return False, "Filename is too long."

    extension = Path(cleaned).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return False, "Unsupported file type."

    return True, cleaned


def validate_file_size(size_bytes):
    if type(size_bytes) is not int:
        return False, "Invalid file size."

    if size_bytes <= 0:
        return False, "Empty files are not permitted."

    if size_bytes > MAX_FILE_SIZE:
        return False, "File exceeds the 10 MB limit."

    return True, "Valid file size."


def validate_file_signature(filename, header):
    valid, result = validate_filename(filename)

    if not valid:
        return False, result

    if not isinstance(header, bytes):
        return False, "Invalid file contents."

    extension = Path(result).suffix.lower()

    signatures = SIGNATURES.get(extension)

    if signatures and not any(
        header.startswith(signature)
        for signature in signatures
    ):
        return (
            False,
            "File contents do not match its extension."
        )

    return True, "File signature accepted."


def validate_archive(data, extension):
    """
    Inspect ZIP structure without extracting files.
    """

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()

            if not members:
                return False, "Archive is empty."

            if len(members) > MAX_ARCHIVE_MEMBERS:
                return False, "Archive contains too many files."

            total_uncompressed = 0
            names = set()

            for member in members:
                name = member.filename
                normalized = name.replace("\\", "/")
                path = PurePosixPath(normalized)

                if (
                    not name
                    or name.startswith("/")
                    or "\\" in name
                    or ":" in name
                    or ".." in path.parts
                    or "\x00" in name
                ):
                    return (
                        False,
                        "Archive contains an unsafe path."
                    )

                if member.flag_bits & 0x1:
                    return (
                        False,
                        "Encrypted archives are not supported."
                    )

                file_mode = member.external_attr >> 16

                if stat.S_ISLNK(file_mode):
                    return (
                        False,
                        "Archive contains a symbolic link."
                    )

                total_uncompressed += member.file_size

                if (
                    total_uncompressed
                    > MAX_ARCHIVE_UNCOMPRESSED
                ):
                    return (
                        False,
                        "Archive expands beyond the safety limit."
                    )

                if (
                    member.file_size > 1024 * 1024
                    and member.file_size
                    > max(member.compress_size, 1) * 100
                ):
                    return (
                        False,
                        "Suspicious archive compression ratio."
                    )

                names.add(normalized)

            if extension in OFFICE_REQUIRED_FILES:
                required = OFFICE_REQUIRED_FILES[extension]

                if (
                    required not in names
                    or "[Content_Types].xml" not in names
                ):
                    return (
                        False,
                        "Office document structure is invalid."
                    )

            # Verify the compressed data and CRC checks.
            # Do not extract files to disk.
            for member in members:
                if member.is_dir():
                    continue

                with archive.open(member) as source:
                    while source.read(64 * 1024):
                        pass

    except (
        zipfile.BadZipFile,
        RuntimeError,
        OSError,
        ValueError,
        EOFError,
    ):
        return False, "Corrupted or invalid archive."

    return True, "Archive structure accepted."


def validate_file_content(filename, data):
    """
    Deeper validation using complete file bytes.

    This function must only receive bounded uploads.
    """

    valid, cleaned = validate_filename(filename)

    if not valid:
        return False, cleaned

    if not isinstance(data, bytes):
        return False, "Invalid file contents."

    valid, reason = validate_file_size(len(data))

    if not valid:
        return False, reason

    valid, reason = validate_file_signature(
        cleaned, data[:32]
    )

    if not valid:
        return False, reason

    extension = Path(cleaned).suffix.lower()

    if extension in {
        ".zip", ".docx", ".xlsx", ".pptx"
    }:
        return validate_archive(data, extension)

    if extension == ".pdf":
        if b"%%EOF" not in data[-2048:]:
            return False, "PDF appears incomplete."

    elif extension == ".png":
        if len(data) < 33 or data[12:16] != b"IHDR":
            return False, "Invalid PNG structure."

    elif extension in {".jpg", ".jpeg"}:
        if not data.endswith(b"\xff\xd9"):
            return False, "JPEG appears incomplete."

    elif extension == ".ipynb":
        try:
            notebook = json.loads(
                data.decode("utf-8-sig")
            )
        except (ValueError, UnicodeError):
            return False, "Invalid Jupyter notebook."

        if (
            not isinstance(notebook, dict)
            or not isinstance(notebook.get("cells"), list)
            or "nbformat" not in notebook
        ):
            return False, "Invalid notebook structure."

    elif extension in TEXT_EXTENSIONS:
        if b"\x00" in data:
            return False, "Binary content in text file."

        try:
            data.decode("utf-8-sig")
        except UnicodeError:
            return (
                False,
                "Text file must use UTF-8 encoding."
            )

    return True, "File content validated."


def validate_upload(filename, size_bytes, header):
    """
    Backward-compatible preliminary validation.

    Existing BridgeLab tests use this function.
    """

    valid, reason = validate_filename(filename)

    if not valid:
        return False, reason

    valid, reason = validate_file_size(size_bytes)

    if not valid:
        return False, reason

    return validate_file_signature(filename, header)


def validate_upload_bytes(filename, data):
    """
    Complete validation for a bounded file.

    Returns (True, message) or (False, reason).
    """

    return validate_file_content(filename, data)
