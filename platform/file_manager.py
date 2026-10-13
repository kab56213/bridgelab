
from pathlib import Path
from datetime import date
from flask import (
    Blueprint, request, session,
    redirect, url_for, abort, current_app
)
import sqlite3
import hmac

ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "instance" / "bridgelab.db"
UPLOADS = ROOT / "instance" / "uploads"

file_manager = Blueprint(
    "file_manager",
    __name__,
    url_prefix="/files"
)


@file_manager.route(
    "/<int:file_id>/remove",
    methods=["POST"]
)
def remove_file(file_id):
    # Only logged-in participants may remove files.
    if session.get("role") != "participant":
        abort(403)

    participant_id = session.get("user_id")

    if not isinstance(participant_id, int):
        abort(403)

    # Protect the action against forged form requests.
    expected_token = session.get("_csrf", "")
    supplied_token = request.form.get("_csrf", "")

    if (
        not expected_token
        or not hmac.compare_digest(
            expected_token, supplied_token
        )
    ):
        abort(400, "Invalid form token.")

    with sqlite3.connect(DATABASE, timeout=10) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")

        row = db.execute(
            """
            SELECT
                f.id,
                f.stored_name,
                f.submission_id,
                s.participant_id,
                s.review_status,
                c.status AS challenge_status,
                c.deadline
            FROM submission_files f
            JOIN challenge_submissions s
                ON s.id = f.submission_id
            JOIN challenges c
                ON c.id = s.challenge_id
            WHERE f.id = ?
              AND s.participant_id = ?
            """,
            (file_id, participant_id)
        ).fetchone()

        if row is None:
            abort(404)

        # Prevent modifications after review or deadline.
        if (
            row["review_status"]
            in ("Under Review", "Reviewed")
            or row["challenge_status"] != "Open"
            or not row["deadline"]
            or row["deadline"] < date.today().isoformat()
        ):
            abort(403, "Submission is locked.")

        # Keep at least one supporting file attached.
        count = db.execute(
            """
            SELECT COUNT(*)
            FROM submission_files
            WHERE submission_id = ?
            """,
            (row["submission_id"],)
        ).fetchone()[0]

        if count <= 1:
            abort(
                400,
                "Upload a replacement before removing "
                "the final project file."
            )

        db.execute(
            """
            DELETE FROM submission_files
            WHERE id = ?
            """,
            (file_id,)
        )

        db.commit()

    # Stored filenames are generated UUIDs, not user paths.
    target = UPLOADS / row["stored_name"]

    try:
        target.unlink(missing_ok=True)
    except OSError:
        # Database removal succeeded; cleanup can be retried.
        current_app.logger.warning(
            "File metadata removed but file cleanup failed: %s",
            row["stored_name"]
        )

    return redirect(
        url_for(
            "participant_dashboard",
            notice="Project file removed successfully."
        )
    )
