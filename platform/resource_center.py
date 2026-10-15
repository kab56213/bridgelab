from database import database_connection
from pathlib import Path
from flask import Blueprint, abort, send_file, session
import sqlite3
from progress_tracker import mark_resources_accessed

ROOT = Path(__file__).resolve().parent.parent
DATABASE = ROOT / "instance" / "bridgelab.db"
RESOURCE_DIRECTORY = ROOT / "challenges" / "novamart_002"

resource_center = Blueprint(
    "resource_center",
    __name__,
    url_prefix="/resources"
)

RESOURCE_FILES = {
    "instructions": "START_HERE.md",
    "sales": "sales.csv",
    "customers": "customers.csv",
    "inventory": "inventory.csv",
    "expenses": "operating_expenses.csv",
    "campaigns": "campaigns.csv",
}

TRACK_GUIDANCE = {
    "Data & Technology": (
        "Analyze sales, customer patterns, and margins. "
        "Create useful tables or charts and explain "
        "your findings. Coding is optional."
    ),
    "Business & Finance": (
        "Investigate revenue, product costs, and operating "
        "expenses. Build a financial model and recommend "
        "two realistic improvements."
    ),
    "Marketing & Growth": (
        "Analyze customer segments and marketing results. "
        "Develop a practical customer acquisition or "
        "retention strategy with a proposed budget."
    ),
    "Operations & Management": (
        "Analyze inventory and operating processes. "
        "Identify inefficiencies and propose an "
        "implementation plan."
    ),
}


def get_enrollment(challenge_id):
    if session.get("role") != "participant":
        abort(403)

    participant_id = session.get("user_id")

    if not isinstance(participant_id, int):
        abort(403)

    with database_connection(DATABASE) as db:
        db.row_factory = sqlite3.Row

        enrollment = db.execute(
            """
            SELECT e.chosen_track, c.title
            FROM enrollments e
            JOIN challenges c
                ON c.id = e.challenge_id
            WHERE e.participant_id = ?
              AND e.challenge_id = ?
            """,
            (participant_id, challenge_id)
        ).fetchone()

    if enrollment is None:
        abort(403)

    return dict(enrollment)


@resource_center.route("/<int:challenge_id>")
def resource_page(challenge_id):
    from flask import render_template_string

    if challenge_id != 2:
        abort(404)

    enrollment = get_enrollment(challenge_id)
    mark_resources_accessed(
    session["user_id"],
    challenge_id
    )

    files = [
        {"key": key, "name": name}
        for key, name in RESOURCE_FILES.items()
    ]

    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width,initial-scale=1">
        <title>BridgeLab — Resource Center</title>
        <style>
            body {
                background:#f4f0e7;
                color:#192640;
                font:15px Arial,sans-serif;
                padding:30px;
            }
            main {
                max-width:900px;
                margin:auto;
            }
            h1,h2 {
                font-family:Georgia,serif;
            }
            .hero {
                background:#192640;
                color:white;
                padding:30px;
            }
            .card {
                background:#fffdf8;
                border:1px solid #192640;
                padding:20px;
                margin-top:18px;
                box-shadow:4px 4px 0 #192640;
            }
            .button {
                display:inline-block;
                background:#f5d46c;
                padding:12px 16px;
                color:#192640;
                border:1px solid #192640;
                text-decoration:none;
                font-weight:bold;
            }
            .file {
                display:flex;
                justify-content:space-between;
                gap:20px;
                align-items:center;
                padding:14px 0;
                border-bottom:1px solid #c4c5c3;
            }
            @media(max-width:600px) {
                .file {
                    align-items:flex-start;
                    flex-direction:column;
                }
            }
        </style>
    </head>
    <body>
    <main>
        <div class="hero">
            <p>BRIDGELAB / CHALLENGE RESOURCES</p>
            <h1>{{ enrollment.title }}</h1>
            <p>Specialization: {{ enrollment.chosen_track }}</p>
        </div>

        <div class="card">
            <h2>Your Assignment</h2>
            <p>{{ guidance }}</p>
            <p>
                Use the resources below to support
                your recommendations.
            </p>
        </div>

        <div class="card">
            <h2>Download Resources</h2>

            {% for file in files %}
            <div class="file">
                <span>{{ file.name }}</span>
                <a class="button"
                   href="{{ url_for(
                       'resource_center.download_resource',
                       challenge_id=challenge_id,
                       file_key=file.key
                   ) }}">
                    DOWNLOAD
                </a>
            </div>
            {% endfor %}
        </div>

        <p style="margin-top:30px">
            <a href="/participant">
                ← Back to My Projects
            </a>
        </p>
    </main>
    </body>
    </html>
    """

    return render_template_string(
        template,
        enrollment=enrollment,
        guidance=TRACK_GUIDANCE.get(
            enrollment["chosen_track"],
            "Read the challenge instructions and "
            "prepare an evidence-based solution."
        ),
        files=files,
        challenge_id=challenge_id
    )


@resource_center.route(
    "/<int:challenge_id>/download/<file_key>"
)
def download_resource(challenge_id, file_key):
    if challenge_id != 2:
        abort(404)

    get_enrollment(challenge_id)

    filename = RESOURCE_FILES.get(file_key)

    if filename is None:
        abort(404)

    path = RESOURCE_DIRECTORY / filename

    if not path.is_file():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream"
    )
