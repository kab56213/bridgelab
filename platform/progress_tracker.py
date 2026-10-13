
"""
BridgeLab V10 — Project Progress Tracker

Tracks genuine participant actions:
- Enrollment
- First access to resources
- Project submission
- Completed evaluation

Local demonstration only.
"""

from datetime import datetime, timezone
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "instance" / "bridgelab.db"


def get_db():
    db = sqlite3.connect(DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize_progress():
    """Create progress tracking table without deleting data."""
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS resource_access (
                participant_id INTEGER NOT NULL,
                challenge_id INTEGER NOT NULL,
                first_accessed_at TEXT NOT NULL,
                PRIMARY KEY (participant_id, challenge_id),
                FOREIGN KEY (participant_id)
                    REFERENCES participant_accounts(id),
                FOREIGN KEY (challenge_id)
                    REFERENCES challenges(id)
            )
            """
        )
        db.commit()


def mark_resources_accessed(participant_id, challenge_id):
    """Record first resource-page access for an enrolled user."""
    with get_db() as db:
        enrolled = db.execute(
            """
            SELECT 1 FROM enrollments
            WHERE participant_id=?
              AND challenge_id=?
            """,
            (participant_id, challenge_id)
        ).fetchone()

        if not enrolled:
            return False

        db.execute(
            """
            INSERT OR IGNORE INTO resource_access
            (participant_id, challenge_id, first_accessed_at)
            VALUES (?, ?, ?)
            """,
            (
                participant_id,
                challenge_id,
                datetime.now(timezone.utc).isoformat()
            )
        )
        db.commit()

    return True


def get_progress(participant_id, challenge_id):
    """Compute progress using saved database records."""
    with get_db() as db:
        enrollment = db.execute(
            """
            SELECT 1 FROM enrollments
            WHERE participant_id=?
              AND challenge_id=?
            """,
            (participant_id, challenge_id)
        ).fetchone()

        if not enrollment:
            return None

        resources_required = challenge_id == 2

        resource_access = db.execute(
            """
            SELECT 1 FROM resource_access
            WHERE participant_id=?
              AND challenge_id=?
            """,
            (participant_id, challenge_id)
        ).fetchone()

        submission = db.execute(
            """
            SELECT
                s.id,
                s.review_status,
                r.submission_id AS reviewed
            FROM challenge_submissions s
            LEFT JOIN submission_reviews r
                ON r.submission_id=s.id
            WHERE s.participant_id=?
              AND s.challenge_id=?
            """,
            (participant_id, challenge_id)
        ).fetchone()

    stages = [
        {
            "label": "Enroll in a specialization",
            "complete": True
        }
    ]

    if resources_required:
        stages.append({
            "label": "Open challenge resources",
            "complete": bool(resource_access)
        })

    stages.extend([
        {
            "label": "Submit project files",
            "complete": bool(submission)
        },
        {
            "label": "Receive completed evaluation",
            "complete": bool(
                submission
                and submission["review_status"] == "Reviewed"
                and submission["reviewed"] is not None
            )
        }
    ])

    done = sum(s["complete"] for s in stages)

    return {
        "stages": stages,
        "completed": done,
        "total": len(stages),
        "percent": round(100 * done / len(stages))
    }


if __name__ == "__main__":
    initialize_progress()
    print("BridgeLab progress tracker initialized.")
