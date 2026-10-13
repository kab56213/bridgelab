
from pathlib import Path
from functools import wraps
from datetime import date, timedelta
from urllib.parse import urlparse
from uuid import uuid4
import sqlite3
import secrets
import hmac
import sys
import time

from flask import (
    Flask, request, redirect, url_for,
    render_template_string, session, abort, send_file
)
from werkzeug.utils import secure_filename


ROOT = Path(__file__).resolve().parent.parent
INSTANCE = ROOT / "instance"
DB_PATH = INSTANCE / "bridgelab.db"
SECRET_PATH = INSTANCE / ".flask_secret"
UPLOADS = INSTANCE / "uploads"

INSTANCE.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))

from auth.security import hash_password, verify_password


if not SECRET_PATH.exists():
    SECRET_PATH.write_text(secrets.token_hex(32))

app = Flask(__name__)

from resource_center import resource_center
app.register_blueprint(resource_center)

from file_manager import file_manager
app.register_blueprint(file_manager)

app.secret_key = SECRET_PATH.read_text().strip()

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    MAX_CONTENT_LENGTH=26 * 1024 * 1024
)

TRACKS = [
    "Data & Technology",
    "Business & Finance",
    "Marketing & Growth",
    "Operations & Management"
]

CATEGORIES = [
    "Multidisciplinary",
    *TRACKS,
    "Data Analytics",
    "Software Development",
    "Business Analysis"
]

STATUSES = ["Draft", "Open", "Closed"]

ALLOWED = {
    ".pdf", ".docx", ".xlsx", ".csv", ".pptx",
    ".png", ".jpg", ".jpeg", ".py", ".java",
    ".sql", ".ipynb", ".zip", ".txt"
}

MAX_FILE = 10 * 1024 * 1024
MAX_FILES = 5

RUBRIC = [
    ("Accuracy and evidence", "accuracy", 30),
    ("Problem-solving and recommendations", "solution", 30),
    ("Feasibility and implementation", "feasibility", 20),
    ("Communication", "communication", 10),
    ("Originality and documentation", "originality", 10)
]

LOGIN_ATTEMPTS = {}


# =============================================
# DATABASE AND MIGRATION
# =============================================

def get_db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize_database():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            skill TEXT NOT NULL,
            joined_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER UNIQUE NOT NULL,
            project_url TEXT NOT NULL,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER UNIQUE NOT NULL,
            technical_accuracy INTEGER NOT NULL,
            problem_solving INTEGER NOT NULL,
            presentation INTEGER NOT NULL,
            originality INTEGER NOT NULL,
            documentation INTEGER NOT NULL,
            total_score INTEGER NOT NULL,
            evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            track TEXT NOT NULL,
            description TEXT NOT NULL,
            deliverables TEXT NOT NULL,
            deadline TEXT,
            prize_usd REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Draft'
        );

        CREATE TABLE IF NOT EXISTS participant_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            skill TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            enrolled_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(participant_id, challenge_id),
            FOREIGN KEY(participant_id)
                REFERENCES participant_accounts(id),
            FOREIGN KEY(challenge_id)
                REFERENCES challenges(id)
        );

        CREATE TABLE IF NOT EXISTS challenge_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            project_url TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'Submitted',
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(participant_id, challenge_id),
            FOREIGN KEY(participant_id)
                REFERENCES participant_accounts(id),
            FOREIGN KEY(challenge_id)
                REFERENCES challenges(id)
        );

        CREATE TABLE IF NOT EXISTS submission_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(submission_id)
                REFERENCES challenge_submissions(id)
        );

        CREATE TABLE IF NOT EXISTS submission_reviews (
            submission_id INTEGER PRIMARY KEY,
            accuracy INTEGER NOT NULL,
            solution INTEGER NOT NULL,
            feasibility INTEGER NOT NULL,
            communication INTEGER NOT NULL,
            originality INTEGER NOT NULL,
            total_score INTEGER NOT NULL,
            feedback TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(submission_id)
                REFERENCES challenge_submissions(id)
        );
        """)

        cols = {
            r["name"]
            for r in db.execute("PRAGMA table_info(enrollments)")
        }

        if "chosen_track" not in cols:
            db.execute(
                "ALTER TABLE enrollments "
                "ADD COLUMN chosen_track TEXT NOT NULL DEFAULT ''"
            )

        cols = {
            r["name"]
            for r in db.execute(
                "PRAGMA table_info(challenge_submissions)"
            )
        }

        if "project_title" not in cols:
            db.execute(
                "ALTER TABLE challenge_submissions "
                "ADD COLUMN project_title TEXT NOT NULL DEFAULT ''"
            )

        if "description" not in cols:
            db.execute(
                "ALTER TABLE challenge_submissions "
                "ADD COLUMN description TEXT NOT NULL DEFAULT ''"
            )

        if "optional_url" not in cols:
            db.execute(
                "ALTER TABLE challenge_submissions "
                "ADD COLUMN optional_url TEXT NOT NULL DEFAULT ''"
            )

        if db.execute(
            "SELECT COUNT(*) FROM challenges"
        ).fetchone()[0] == 0:
            db.execute(
                """
                INSERT INTO challenges
                (title, track, description, deliverables,
                 deadline, prize_usd, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Retail Analytics Challenge 001",
                    "Data Analytics",
                    "Analyze a synthetic retail dataset "
                    "and recommend improvements.",
                    "Cleaned dataset, analysis, charts "
                    "and recommendations.",
                    None,
                    100,
                    "Draft"
                )
            )

        db.commit()


# =============================================
# SECURITY AND UTILITIES
# =============================================

def csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    supplied = request.form.get("_csrf", "")
    if not hmac.compare_digest(supplied, csrf()):
        abort(400, "Invalid form token")


def required_role(role):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if session.get("role") != role:
                return redirect(
                    url_for(
                        "admin_login"
                        if role == "admin"
                        else "participant_login"
                    )
                )

            table = (
                "admins"
                if role == "admin"
                else "participant_accounts"
            )

            with get_db() as db:
                row = db.execute(
                    f"SELECT id FROM {table} WHERE id=?",
                    (session.get("user_id"),)
                ).fetchone()

            if not row:
                session.clear()
                return redirect(
                    url_for(
                        "admin_login"
                        if role == "admin"
                        else "participant_login"
                    )
                )

            return fn(*args, **kwargs)

        return wrapped

    return decorate


def start_session(uid, role):
    session.clear()
    session.update(
        user_id=uid,
        role=role,
        _csrf=secrets.token_urlsafe(32)
    )
    session.permanent = True


def valid_handle(s):
    return (
        3 <= len(s) <= 40
        and all(
            c.isascii()
            and (c.isalnum() or c in "_-")
            for c in s
        )
    )


def open_challenge(c):
    return (
        c["status"] == "Open"
        and c["deadline"]
        and c["deadline"] >= date.today().isoformat()
    )


def validated_url(url):
    if not url:
        return True

    try:
        x = urlparse(url)
        return (
            x.scheme == "https"
            and bool(x.hostname)
            and x.username is None
            and x.password is None
            and len(url) <= 500
        )
    except ValueError:
        return False


def message(endpoint, msg, error=False):
    return redirect(
        url_for(
            endpoint,
            **{"error" if error else "notice": msg}
        )
    )


# =============================================
# RETRO-MODERN DESIGN
# =============================================

CSS = """
:root {
    --navy:#192640;
    --blue:#3454c8;
    --cream:#f4f0e7;
    --paper:#fffdf8;
    --yellow:#f5d46c;
    --mint:#c9edda;
    --line:#c4c5c3;
}

* { box-sizing:border-box; }

body {
    margin:0;
    background:var(--cream);
    color:var(--navy);
    font:14px Arial,sans-serif;
}

a { color:var(--blue); }

input,select,textarea,button {
    font:inherit;
}

input,select,textarea {
    width:100%;
    padding:12px;
    background:white;
    border:1px solid #a0a6ae;
    border-radius:0;
}

textarea { min-height:95px; }

label {
    display:block;
    margin:15px 0 7px;
    font:bold 11px 'Courier New',monospace;
}

.top {
    background:var(--navy);
    color:white;
    padding:12px 4%;
    display:flex;
    justify-content:space-between;
    gap:12px;
    flex-wrap:wrap;
    font:11px 'Courier New',monospace;
}

.top a { color:white; }

.shell {
    max-width:1480px;
    margin:auto;
    padding:30px 24px 65px;
}

.brand {
    display:flex;
    justify-content:space-between;
    align-items:center;
    border-bottom:3px solid var(--navy);
    padding-bottom:23px;
    gap:18px;
}

.logo {
    font:bold clamp(37px,5vw,61px) Georgia,serif;
    letter-spacing:-3px;
}

.logo span { color:var(--blue); }

.tagline {
    font:11px 'Courier New',monospace;
    margin-top:7px;
    color:#687385;
}

.stamp {
    background:var(--yellow);
    border:1px solid var(--navy);
    padding:12px;
    box-shadow:4px 4px 0 var(--navy);
    font:bold 11px 'Courier New',monospace;
}

.layout {
    display:grid;
    grid-template-columns:225px minmax(0,1fr);
    gap:26px;
    margin-top:25px;
}

.sidebar,.panel,.challenge,.stat {
    background:var(--paper);
    border:1px solid var(--navy);
    box-shadow:3px 3px 0 #c1c4c9;
}

.sidebar {
    padding:18px;
    height:fit-content;
}

.sidebar a {
    display:block;
    padding:13px 7px;
    border-top:1px dashed var(--line);
    font-weight:bold;
    text-decoration:none;
}

.hero {
    background:var(--navy);
    color:white;
    padding:34px;
}

.hero h1 {
    font:bold clamp(28px,4vw,44px) Georgia,serif;
    margin:14px 0;
}

.hero p {
    color:#d3ddea;
    line-height:1.8;
}

.mono {
    font:bold 11px 'Courier New',monospace;
}

.gold { color:var(--yellow); }

.heading {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:10px;
    margin:30px 0 15px;
}

.heading h2 {
    font:bold 24px Georgia,serif;
    margin:0;
}

.panel {
    padding:20px;
    margin-bottom:18px;
}

.challenge {
    padding:23px;
    margin-bottom:17px;
}

.challenge h3 {
    font:bold 25px Georgia,serif;
    margin:13px 0;
}

.challenge p { line-height:1.7; }

.pill {
    display:inline-block;
    padding:6px 10px;
    margin:4px 5px 4px 0;
    background:var(--mint);
    border:1px solid #93a89e;
    font:bold 10px 'Courier New',monospace;
}

.btn {
    display:inline-block;
    background:var(--blue);
    color:white;
    border:1px solid var(--navy);
    padding:13px 18px;
    margin:15px 8px 0 0;
    text-decoration:none;
    font:bold 11px 'Courier New',monospace;
    box-shadow:3px 3px 0 var(--navy);
    cursor:pointer;
}

.yellow {
    background:var(--yellow);
    color:var(--navy);
}

.stats {
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:13px;
}

.stat { padding:20px; }

.stat strong {
    display:block;
    font:bold 36px Georgia,serif;
    margin-top:12px;
}

.notice,.warning,.error {
    padding:14px;
    margin:16px 0;
    border:1px solid;
}

.notice { background:var(--mint); }
.warning { background:#fff0c4; }
.error { background:#ffe2df; }

table {
    width:100%;
    border-collapse:collapse;
}

th,td {
    text-align:left;
    padding:12px;
    border-bottom:1px solid var(--line);
}

th {
    font:bold 11px 'Courier New',monospace;
    background:#e8e8e3;
}

.scroll { overflow-x:auto; }

.auth {
    max-width:480px;
    margin:55px auto;
    background:var(--paper);
    border:2px solid var(--navy);
    padding:33px;
    box-shadow:7px 7px 0 var(--navy);
}

footer {
    border-top:1px solid var(--navy);
    margin-top:45px;
    padding-top:20px;
    font:11px 'Courier New',monospace;
    color:#687385;
}

small { color:#687385; }

.grid {
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:18px;
}

@media(max-width:950px) {
    .layout { grid-template-columns:1fr; }
    .stats { grid-template-columns:repeat(2,1fr); }
}

@media(max-width:650px) {
    .shell { padding:18px 12px; }
    .grid { grid-template-columns:1fr; }
    .stamp { display:none; }
    .hero { padding:23px; }
}
"""


def render(body, title="BridgeLab", **data):
    template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width,initial-scale=1">
    <title>""" + title + """ — BridgeLab</title>
    <style>""" + CSS + """</style>
</head>
<body>
<div class="top">
    <span>BRIDGELAB NETWORK // PROJECT SYSTEM</span>
    <span>
        <a href="/challenges">CHALLENGES</a> /
        <a href="/participant">PARTICIPANT</a> /
        <a href="/">ADMIN</a>
    </span>
</div>

<div class="shell">
    <div class="brand">
        <div>
            <div class="logo">
                BridgeLab<span>.</span>
            </div>
            <div class="tagline">
                BUILD SKILLS / SOLVE PROBLEMS / CREATE IMPACT
            </div>
        </div>
        <div class="stamp">SYSTEM V7.0 / DEMO</div>
    </div>
""" + body + """
<footer>
    BRIDGELAB / INDEPENDENT PROJECT INITIATIVE
    — LOCAL DEVELOPMENT
</footer>
</div>
</body>
</html>
"""

    return render_template_string(
        template,
        csrf=csrf(),
        tracks=TRACKS,
        categories=CATEGORIES,
        statuses=STATUSES,
        **data
    )


def alerts():
    return """
{% if notice %}
    <div class="notice">{{ notice }}</div>
{% endif %}
{% if error %}
    <div class="error">{{ error }}</div>
{% endif %}
"""


# =============================================
# AUTHENTICATION
# =============================================

AUTH_BODY = """
<div class="auth">
    <div class="mono">/ SECURE ACCESS TERMINAL</div>

    <h1 style="font:bold 34px Georgia,serif">
        {{ heading }}
    </h1>

    <p>{{ detail }}</p>
""" + alerts() + """
    <form method="post">
        <input type="hidden" name="_csrf"
               value="{{ csrf }}">

        <label>USERNAME</label>
        <input name="username" maxlength="40"
               autocomplete="username" required>

        {% if registering %}
            <label>AREA OF INTEREST</label>
            <select name="skill">
                {% for t in tracks %}
                    <option>{{ t }}</option>
                {% endfor %}
            </select>
        {% endif %}

        <label>PASSWORD</label>
        <input type="password" name="password"
               minlength="{{ 12 if registering else 1 }}"
               required>

        <button class="btn" type="submit">
            {{ action }} →
        </button>
    </form>

    <p>
        <a href="{{ alternate_url }}">
            {{ alternate }}
        </a>
    </p>
</div>
"""


def auth_screen(
    heading, detail, action, registering=False,
    error=None, alternate_url="/challenges",
    alternate="Back to challenges"
):
    return render(
        AUTH_BODY,
        heading=heading,
        detail=detail,
        action=action,
        registering=registering,
        alternate_url=alternate_url,
        alternate=alternate,
        error=error,
        notice=None
    )


def allowed_login(key):
    now = time.monotonic()
    LOGIN_ATTEMPTS[key] = [
        t for t in LOGIN_ATTEMPTS.get(key, [])
        if now - t < 300
    ]
    return len(LOGIN_ATTEMPTS[key]) < 5


@app.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        check_csrf()

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        key = ("admin", request.remote_addr)

        if not allowed_login(key):
            error = "Too many attempts. Try again later."
        else:
            with get_db() as db:
                row = db.execute(
                    "SELECT * FROM admins WHERE username=?",
                    (username,)
                ).fetchone()

            if row and verify_password(
                row["password_hash"], password
            ):
                LOGIN_ATTEMPTS.pop(key, None)
                start_session(row["id"], "admin")
                return redirect(
                    url_for("admin_dashboard")
                )

            LOGIN_ATTEMPTS.setdefault(
                key, []
            ).append(time.monotonic())

            error = "Invalid username or password."

        return auth_screen(
            "Administrator Login",
            "Private challenge management workspace.",
            "Sign In",
            error=error
        ), 401

    return auth_screen(
        "Administrator Login",
        "Private challenge management workspace.",
        "Sign In"
    )


@app.route("/participant/register", methods=["GET", "POST"])
def participant_register():
    if request.method == "POST":
        check_csrf()

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        skill = request.form.get("skill", "")

        if not valid_handle(username) or skill not in TRACKS:
            error = "Invalid username or area of interest."

        elif not 12 <= len(password) <= 256:
            error = "Password must have 12–256 characters."

        else:
            try:
                with get_db() as db:
                    row = db.execute(
                        """
                        INSERT INTO participant_accounts
                        (username, password_hash, skill)
                        VALUES (?, ?, ?)
                        """,
                        (
                            username,
                            hash_password(password),
                            skill
                        )
                    )
                    uid = row.lastrowid
                    db.commit()

                start_session(uid, "participant")
                return redirect(
                    url_for("participant_dashboard")
                )

            except sqlite3.IntegrityError:
                error = "Username already taken."

        return auth_screen(
            "Join the Lab",
            "Create a fictional local demo account.",
            "Create Account",
            True,
            error,
            "/participant/login",
            "Already registered? Sign in"
        ), 400

    return auth_screen(
        "Join the Lab",
        "Test accounts only. Do not enter real personal information.",
        "Create Account",
        True,
        alternate_url="/participant/login",
        alternate="Already registered? Sign in"
    )


@app.route("/participant/login", methods=["GET", "POST"])
def participant_login():
    if request.method == "POST":
        check_csrf()

        key = ("participant", request.remote_addr)
        username = request.form.get("username", "").strip()

        if not allowed_login(key):
            error = "Too many attempts. Try again later."

        else:
            with get_db() as db:
                row = db.execute(
                    """
                    SELECT * FROM participant_accounts
                    WHERE username=?
                    """,
                    (username,)
                ).fetchone()

            if row and verify_password(
                row["password_hash"],
                request.form.get("password", "")
            ):
                LOGIN_ATTEMPTS.pop(key, None)
                start_session(row["id"], "participant")
                return redirect(
                    url_for("participant_dashboard")
                )

            LOGIN_ATTEMPTS.setdefault(
                key, []
            ).append(time.monotonic())

            error = "Invalid username or password."

        return auth_screen(
            "Participant Login",
            "Your personal project workspace.",
            "Sign In",
            error=error,
            alternate_url="/participant/register",
            alternate="Create an account"
        ), 401

    return auth_screen(
        "Participant Login",
        "Your personal project workspace.",
        "Sign In",
        alternate_url="/participant/register",
        alternate="Create an account"
    )


@app.route("/logout", methods=["POST"])
def logout():
    check_csrf()
    session.clear()
    return redirect(url_for("public_challenges"))


# =============================================
# PUBLIC CHALLENGE DIRECTORY
# =============================================

PUBLIC_BODY = """
<div class="hero" style="margin-top:25px">
    <div class="mono gold">// PROJECT DIRECTORY</div>
    <h1>One problem. Different perspectives.</h1>
    <p>
        Practice solving real-world business challenges
        through data, finance, marketing, or operations.
    </p>
    <a class="btn yellow" href="/participant/register">
        CREATE DEMO ACCOUNT →
    </a>
</div>

<div class="warning">
    LOCAL PROTOTYPE ONLY — not accepting real applicants.
</div>

<div class="heading">
    <h2>Open Challenges</h2>
    <span class="mono">
        {{ challenges|length }} AVAILABLE
    </span>
</div>

{% for c in challenges %}
<article class="challenge">
    <span class="mono">
        PROJECT / {{ '%03d'|format(c.id) }}
    </span>

    <h3>{{ c.title }}</h3>

    <span class="pill">{{ c.track }}</span>
    <span class="pill">DUE {{ c.deadline }}</span>

    <p>{{ c.description }}</p>

    <p>
        <strong>Deliverables:</strong>
        {{ c.deliverables }}
    </p>

    <a href="/participant" class="btn">
        VIEW IN WORKSPACE →
    </a>
</article>
{% else %}
<div class="panel">
    No open challenges right now.
    The pilot is still being prepared.
</div>
{% endfor %}
"""


@app.route("/challenges")
def public_challenges():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT * FROM challenges
            WHERE status='Open' AND deadline>=?
            ORDER BY deadline, id
            """,
            (date.today().isoformat(),)
        ).fetchall()

    return render(PUBLIC_BODY, challenges=rows)


# =============================================
# PARTICIPANT WORKSPACE
# =============================================

PARTICIPANT_BODY = """
<div class="layout">
<nav class="sidebar">
    <div class="mono">/ PARTICIPANT DESK</div>

    <a href="#my-projects">01 My Projects</a>
    <a href="#available">02 New Challenges</a>

    <form method="post" action="/logout">
        <input type="hidden" name="_csrf"
               value="{{ csrf }}">
        <button class="btn yellow">LOG OUT</button>
    </form>
</nav>

<main>
    <div class="hero">
        <div class="mono gold">
            // PARTICIPANT WORKSPACE
        </div>
        <h1>Welcome, {{ account.username }}.</h1>
        <p>
            Choose a specialization, build a solution,
            and upload your work directly.
            No GitHub account required.
        </p>
        <span class="mono gold">
            {{ account.skill }}
        </span>
    </div>

    <div class="warning">
        V7 LOCAL DEMO. Do not enter real participant
        data or invite public users.
    </div>
""" + alerts() + """
    <div class="heading" id="my-projects">
        <h2>My Projects</h2>
        <span class="mono">
            {{ enrollments|length }} ENROLLED
        </span>
    </div>

    {% for e in enrollments %}
    <div class="challenge">
        <span class="mono">
            CHALLENGE / {{ '%03d'|format(e.id) }}
        </span>

        <h3>{{ e.title }}</h3>
        
        {% if e.id == 2 %}
            <a class="btn yellow"
                href="{{ url_for('resource_center.resource_page', challenge_id=e.id) }}">
                OPEN CHALLENGE RESOURCES →
            </a>
        {% endif %}


        <span class="pill">
            {{ e.chosen_track or 'Track not selected' }}
        </span>

        <span class="pill">
            {{ e.review_status or 'Not submitted' }}
        </span>

        <span class="pill">
            DUE {{ e.deadline or 'NOT SET' }}
        </span>

        {% if e.submission_id %}
            <p>
                <strong>
                    Submission #{{ e.submission_id }}
                </strong>:
                {{ e.project_title or 'Legacy submission' }}
            </p>

            <p>{{ e.submission_description or '' }}</p>

            {% for f in e.files %}
            <p>
                <a href="/participant/file/{{ f.id }}">
                    {{ f.original_name }}
                </a>
                ({{ (f.size_bytes / 1024)|round(1) }} KB)
            </p>
            {% endfor %}

            {% if e.project_url %}
            <p>
                <a href="{{ e.project_url }}"
                   rel="noopener noreferrer"
                   target="_blank">
                    Previous GitHub link (V6)
                </a>
            </p>
            {% endif %}

            {% if e.score is not none %}
            <p>
                <strong>Score:</strong>
                {{ e.score }}/100
            </p>

            <p>
                <strong>Feedback:</strong>
                {{ e.feedback }}
            </p>
            {% endif %}
        {% endif %}

        {% if e.can_submit and
              e.review_status not in
              ['Under Review', 'Reviewed'] %}

        <form action="/participant/submit"
              method="post"
              enctype="multipart/form-data">

            <input type="hidden"
                   name="_csrf"
                   value="{{ csrf }}">

            <input type="hidden"
                   name="challenge_id"
                   value="{{ e.id }}">

            <label>PROJECT TITLE</label>
            <input name="project_title"
                   maxlength="120"
                   value="{{ e.project_title or '' }}"
                   required>

            <label>HOW DID YOU APPROACH THE PROBLEM?</label>
            <textarea name="description"
                    maxlength="2500"
                    placeholder="Explain the problem you identified, the tools or methods you used, what you discovered, and the solution you recommend."
                    required>{{ e.submission_description or '' }}</textarea>
            <label>UPLOAD PROJECT FILES</label>

            <input type="file"
                   name="files"
                   multiple
                   accept=".pdf,.docx,.xlsx,.csv,.pptx,.png,.jpg,.jpeg,.py,.java,.sql,.ipynb,.zip,.txt">

            <small>
                Up to 5 files per upload; 10 MB each,
                26 MB total request. Existing uploads
                remain attached when you update.
                At least one file is required for a
                new V7 submission.
            </small>

            <label>OPTIONAL SUPPORTING LINK (HTTPS)</label>

            <input type="url"
                   name="optional_url"
                   maxlength="500"
                   value="{{ e.optional_url or '' }}">

            <button class="btn">
                {{ 'UPDATE SUBMISSION' if e.submission_id
                   else 'SUBMIT PROJECT' }} →
            </button>
        </form>

        {% else %}
        <p class="mono">
            SUBMISSION LOCKED OR CHALLENGE NOT OPEN
        </p>
        {% endif %}
    </div>

    {% else %}
    <div class="panel">
        You have not enrolled in any challenge.
    </div>
    {% endfor %}

    <div class="heading" id="available">
        <h2>Available Challenges</h2>
    </div>

    {% for c in challenges %}
    <div class="challenge">
        <h3>{{ c.title }}</h3>

        <span class="pill">{{ c.track }}</span>
        <span class="pill">DUE {{ c.deadline }}</span>

        <p>{{ c.description }}</p>

        <p>
            <strong>Deliverables:</strong>
            {{ c.deliverables }}
        </p>

        <form action="/participant/enroll"
              method="post">

            <input type="hidden"
                   name="_csrf"
                   value="{{ csrf }}">

            <input type="hidden"
                   name="challenge_id"
                   value="{{ c.id }}">

            <label>CHOOSE YOUR SPECIALIZATION</label>

            <select name="chosen_track" required>
                {% for t in tracks %}
                <option>{{ t }}</option>
                {% endfor %}
            </select>

            <button class="btn yellow">
                ENROLL IN CHALLENGE →
            </button>
        </form>
    </div>

    {% else %}
    <div class="panel">
        No new challenges available.
    </div>
    {% endfor %}
</main>
</div>
"""


@app.route("/participant")
@required_role("participant")
def participant_dashboard():
    uid = session["user_id"]

    with get_db() as db:
        account = db.execute(
            """
            SELECT * FROM participant_accounts
            WHERE id=?
            """,
            (uid,)
        ).fetchone()

        rows = db.execute(
            """
            SELECT
                c.*,
                e.chosen_track,
                s.id AS submission_id,
                s.project_url,
                s.review_status,
                s.project_title,
                s.description AS submission_description,
                s.optional_url,
                r.total_score AS score,
                r.feedback
            FROM enrollments e
            JOIN challenges c
                ON c.id=e.challenge_id
            LEFT JOIN challenge_submissions s
                ON s.challenge_id=c.id
                AND s.participant_id=e.participant_id
            LEFT JOIN submission_reviews r
                ON r.submission_id=s.id
            WHERE e.participant_id=?
            ORDER BY e.id DESC
            """,
            (uid,)
        ).fetchall()

        available = db.execute(
            """
            SELECT * FROM challenges
            WHERE status='Open'
              AND deadline>=?
              AND id NOT IN (
                  SELECT challenge_id FROM enrollments
                  WHERE participant_id=?
              )
            ORDER BY deadline
            """,
            (date.today().isoformat(), uid)
        ).fetchall()

        enrollment_list = []

        for item in rows:
            x = dict(item)
            x["can_submit"] = open_challenge(item)

            if x["submission_id"]:
                x["files"] = db.execute(
                    """
                    SELECT * FROM submission_files
                    WHERE submission_id=?
                    ORDER BY id
                    """,
                    (x["submission_id"],)
                ).fetchall()
            else:
                x["files"] = []

            enrollment_list.append(x)

    return render(
        PARTICIPANT_BODY,
        account=account,
        enrollments=enrollment_list,
        challenges=available,
        notice=request.args.get("notice"),
        error=request.args.get("error")
    )


@app.route("/participant/enroll", methods=["POST"])
@required_role("participant")
def participant_enroll():
    check_csrf()

    try:
        cid = int(request.form.get("challenge_id", ""))
    except ValueError:
        return message(
            "participant_dashboard",
            "Invalid challenge.",
            True
        )

    track = request.form.get("chosen_track", "")

    if track not in TRACKS:
        return message(
            "participant_dashboard",
            "Choose a valid track.",
            True
        )

    with get_db() as db:
        challenge = db.execute(
            "SELECT * FROM challenges WHERE id=?",
            (cid,)
        ).fetchone()

        if not challenge or not open_challenge(challenge):
            return message(
                "participant_dashboard",
                "Challenge is not open.",
                True
            )

        db.execute(
            """
            INSERT OR IGNORE INTO enrollments
            (participant_id, challenge_id, chosen_track)
            VALUES (?, ?, ?)
            """,
            (session["user_id"], cid, track)
        )

        db.commit()

    return message(
        "participant_dashboard",
        "Enrolled successfully."
    )


# =============================================
# PROJECT FILE UPLOADS
# =============================================

@app.route("/participant/submit", methods=["POST"])
@required_role("participant")
def participant_submit():
    check_csrf()

    try:
        cid = int(request.form.get("challenge_id", ""))
    except ValueError:
        return message(
            "participant_dashboard",
            "Invalid challenge.",
            True
        )

    title = request.form.get(
        "project_title", ""
    ).strip()

    description = request.form.get(
        "description", ""
    ).strip()

    optional_url = request.form.get(
        "optional_url", ""
    ).strip()

    incoming = [
        f for f in request.files.getlist("files")
        if f.filename
    ]

    if (
        not 3 <= len(title) <= 120
        or not 20 <= len(description) <= 2500
        or not validated_url(optional_url)
    ):
        return message(
            "participant_dashboard",
            "Provide a valid title (3+), "
            "explanation (20+), and HTTPS link if used.",
            True
        )

    if len(incoming) > MAX_FILES:
        return message(
            "participant_dashboard",
            "Upload at most five files.",
            True
        )

    for f in incoming:
        ext = Path(f.filename).suffix.lower()

        if (
            ext not in ALLOWED
            or not secure_filename(f.filename)
        ):
            return message(
                "participant_dashboard",
                "Unsupported file type or filename.",
                True
            )

    uid = session["user_id"]
    saved = []

    try:
        with get_db() as db:
            enrolled = db.execute(
                """
                SELECT
                    c.*,
                    s.id AS sid,
                    s.review_status
                FROM enrollments e
                JOIN challenges c
                    ON c.id=e.challenge_id
                LEFT JOIN challenge_submissions s
                    ON s.challenge_id=c.id
                    AND s.participant_id=e.participant_id
                WHERE e.participant_id=?
                  AND e.challenge_id=?
                """,
                (uid, cid)
            ).fetchone()

            if (
                not enrolled
                or not open_challenge(enrolled)
                or enrolled["review_status"]
                   in ("Under Review", "Reviewed")
            ):
                return message(
                    "participant_dashboard",
                    "Submission is unavailable or locked.",
                    True
                )

            if enrolled["sid"]:
                existing = db.execute(
                    """
                    SELECT COUNT(*) FROM submission_files
                    WHERE submission_id=?
                    """,
                    (enrolled["sid"],)
                ).fetchone()[0]
            else:
                existing = 0

            if existing + len(incoming) > MAX_FILES:
                return message(
                    "participant_dashboard",
                    "Total attached files cannot exceed five.",
                    True
                )

            if existing == 0 and not incoming:
                return message(
                    "participant_dashboard",
                    "Attach at least one project file.",
                    True
                )

            validated = []

            for f in incoming:
                f.stream.seek(0, 2)
                size = f.stream.tell()
                f.stream.seek(0)

                if size == 0 or size > MAX_FILE:
                    return message(
                        "participant_dashboard",
                        "Each file must be between "
                        "1 byte and 10 MB.",
                        True
                    )

                original = secure_filename(f.filename)[:180]
                stored = (
                    uuid4().hex
                    + Path(original).suffix.lower()
                )

                validated.append(
                    (f, original, stored, size)
                )

            db.execute(
                """
                INSERT INTO challenge_submissions
                (
                    participant_id,
                    challenge_id,
                    project_url,
                    review_status,
                    project_title,
                    description,
                    optional_url
                )
                VALUES (?, ?, ?, 'Submitted', ?, ?, ?)
                ON CONFLICT(participant_id, challenge_id)
                DO UPDATE SET
                    review_status='Submitted',
                    project_title=excluded.project_title,
                    description=excluded.description,
                    optional_url=excluded.optional_url,
                    submitted_at=CURRENT_TIMESTAMP
                """,
                (
                    uid,
                    cid,
                    "",
                    title,
                    description,
                    optional_url
                )
            )

            sid = db.execute(
                """
                SELECT id FROM challenge_submissions
                WHERE participant_id=?
                  AND challenge_id=?
                """,
                (uid, cid)
            ).fetchone()[0]

            for f, original, stored, size in validated:
                target = UPLOADS / stored

                f.save(target)
                saved.append(target)

                db.execute(
                    """
                    INSERT INTO submission_files
                    (
                        submission_id,
                        stored_name,
                        original_name,
                        size_bytes
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        sid,
                        stored,
                        original,
                        size
                    )
                )

            db.commit()

    except (OSError, sqlite3.Error):
        for target in saved:
            target.unlink(missing_ok=True)

        app.logger.exception(
            "Submission storage error"
        )

        return message(
            "participant_dashboard",
            "Upload failed. Please retry.",
            True
        )

    return message(
        "participant_dashboard",
        f"Submission #{sid} saved successfully."
    )


@app.route("/participant/file/<int:file_id>")
@required_role("participant")
def participant_file(file_id):
    with get_db() as db:
        row = db.execute(
            """
            SELECT f.*
            FROM submission_files f
            JOIN challenge_submissions s
                ON s.id=f.submission_id
            WHERE f.id=?
              AND s.participant_id=?
            """,
            (file_id, session["user_id"])
        ).fetchone()

    if not row:
        abort(404)

    return send_file(
        UPLOADS / row["stored_name"],
        as_attachment=True,
        download_name=row["original_name"],
        mimetype="application/octet-stream"
    )


# =============================================
# ADMINISTRATOR WORKSPACE
# =============================================

ADMIN_BODY = """
<div class="layout">
<nav class="sidebar">
    <div class="mono">/ ADMIN WORKSPACE</div>

    <a href="#overview">01 Overview</a>
    <a href="#challenges">02 Challenges</a>
    <a href="#create">03 Create Challenge</a>
    <a href="#submissions">04 Project Reviews</a>
    <a href="#legacy">05 Legacy Demo</a>

    <form method="post" action="/logout">
        <input type="hidden"
               name="_csrf"
               value="{{ csrf }}">
        <button class="btn yellow">LOG OUT</button>
    </form>
</nav>

<main>
    <div class="hero" id="overview">
        <div class="mono gold">
            // AUTHORIZED ADMINISTRATOR
        </div>

        <h1>BridgeLab Control Center.</h1>

        <p>
            Manage projects, tracks, uploads,
            and evaluations.
        </p>

        <span class="mono gold">
            ADMIN: {{ admin_name }}
        </span>
    </div>

    <div class="warning">
        LOCAL V7 DEMO — Not ready for real participant
        applications or live prize awards.
    </div>
""" + alerts() + """
    <div class="stats">
        <div class="stat">
            <span class="mono">CHALLENGES</span>
            <strong>{{ challenges|length }}</strong>
        </div>

        <div class="stat">
            <span class="mono">ACCOUNTS</span>
            <strong>{{ account_count }}</strong>
        </div>

        <div class="stat">
            <span class="mono">SUBMISSIONS</span>
            <strong>{{ submissions|length }}</strong>
        </div>

        <div class="stat">
            <span class="mono">LEGACY SCORES</span>
            <strong>{{ legacy_scores|length }}</strong>
        </div>
    </div>

    <div class="heading" id="challenges">
        <h2>Challenge Catalog</h2>
    </div>

    {% for c in challenges %}
    <div class="challenge">
        <span class="mono">
            CHALLENGE / {{ '%03d'|format(c.id) }}
        </span>

        <h3>{{ c.title }}</h3>

        <span class="pill">{{ c.status }}</span>
        <span class="pill">{{ c.track }}</span>

        <span class="pill">
            USD ${{ '%.2f'|format(c.prize_usd) }}
        </span>

        <span class="pill">
            DUE {{ c.deadline or 'NOT SET' }}
        </span>

        <p>{{ c.description }}</p>

        <p>
            <strong>Deliverables:</strong>
            {{ c.deliverables }}
        </p>

        <a class="btn yellow"
           href="/admin/challenge/{{ c.id }}/edit">
            EDIT CHALLENGE →
        </a>

        {% if c.status != 'Archived' %}
        <form method="post"
              action="/admin/challenge/{{ c.id }}/archive"
              style="display:inline">

            <input type="hidden"
                   name="_csrf"
                   value="{{ csrf }}">

            <button class="btn"
                    onclick="return confirm('Archive this challenge?')">
                ARCHIVE
            </button>
        </form>
        {% endif %}
    </div>
    {% endfor %}

    <div class="heading" id="create">
        <h2>Create a Challenge</h2>
    </div>

    <div class="panel">
        <form action="/admin/challenge/save"
              method="post">

            <input type="hidden"
                   name="_csrf"
                   value="{{ csrf }}">

            <label>TITLE</label>
            <input name="title"
                   maxlength="120"
                   required>

            <label>CHALLENGE CATEGORY</label>
            <select name="track">
                {% for t in categories %}
                <option>{{ t }}</option>
                {% endfor %}
            </select>

            <label>DESCRIPTION</label>
            <textarea name="description" required></textarea>

            <label>DELIVERABLES</label>
            <textarea name="deliverables" required></textarea>

            <div class="grid">
                <div>
                    <label>DEADLINE</label>
                    <input type="date" name="deadline">
                </div>

                <div>
                    <label>PRIZE USD</label>
                    <input type="number"
                           name="prize_usd"
                           min="0"
                           step=".01"
                           value="0"
                           required>
                </div>
            </div>

            <label>STATUS</label>
            <select name="status">
                {% for s in statuses %}
                <option>{{ s }}</option>
                {% endfor %}
            </select>

            <button class="btn">
                CREATE CHALLENGE
            </button>
        </form>
    </div>

    <div class="heading" id="submissions">
        <h2>Challenge Submissions</h2>
    </div>

    <div class="panel scroll">
        <table>
            <tr>
                <th>PARTICIPANT</th>
                <th>CHALLENGE</th>
                <th>TRACK</th>
                <th>STATUS</th>
                <th>SCORE</th>
                <th>ACTION</th>
            </tr>

            {% for s in submissions %}
            <tr>
                <td>{{ s.username }}</td>
                <td>{{ s.title }}</td>
                <td>
                    {{ s.chosen_track or 'Not specified' }}
                </td>
                <td>{{ s.review_status }}</td>
                <td>
                    {{ s.total_score
                       if s.total_score is not none
                       else '—' }}
                </td>
                <td>
                    <a href="/admin/submission/{{ s.id }}">
                        REVIEW →
                    </a>
                </td>
            </tr>

            {% else %}
            <tr>
                <td colspan="6">
                    NO CHALLENGE SUBMISSIONS YET
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="heading" id="legacy">
        <h2>Legacy Demo Records</h2>
    </div>

    <div class="panel scroll">
        <table>
            <tr>
                <th>PARTICIPANT</th>
                <th>SKILL</th>
                <th>SCORE</th>
            </tr>

            {% for p in legacy %}
            <tr>
                <td>{{ p.username }}</td>
                <td>{{ p.skill }}</td>
                <td>
                    {{ p.total_score
                       if p.total_score is not none
                       else '—' }}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div class="heading">
        <h2>Legacy Leaderboard</h2>
    </div>

    <div class="panel scroll">
        <table>
            <tr>
                <th>RANK</th>
                <th>NAME</th>
                <th>SCORE</th>
            </tr>

            {% for s in legacy_scores %}
            <tr>
                <td>#{{ loop.index }}</td>
                <td>{{ s.username }}</td>
                <td>{{ s.total_score }}/100</td>
            </tr>

            {% else %}
            <tr>
                <td colspan="3">
                    NO LEGACY SCORES
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
</main>
</div>
"""


@app.route("/")
@required_role("admin")
def admin_dashboard():
    with get_db() as db:
        admin = db.execute(
            "SELECT username FROM admins WHERE id=?",
            (session["user_id"],)
        ).fetchone()

        challenges = db.execute(
            """
            SELECT * FROM challenges
            ORDER BY id DESC
            """
        ).fetchall()

        count = db.execute(
            "SELECT COUNT(*) FROM participant_accounts"
        ).fetchone()[0]

        submissions = db.execute(
            """
            SELECT
                s.id,
                s.review_status,
                a.username,
                c.title,
                e.chosen_track,
                r.total_score
            FROM challenge_submissions s
            JOIN participant_accounts a
                ON a.id=s.participant_id
            JOIN challenges c
                ON c.id=s.challenge_id
            LEFT JOIN enrollments e
                ON e.participant_id=s.participant_id
                AND e.challenge_id=s.challenge_id
            LEFT JOIN submission_reviews r
                ON r.submission_id=s.id
            ORDER BY s.submitted_at DESC
            """
        ).fetchall()

        legacy = db.execute(
            """
            SELECT p.*, e.total_score
            FROM participants p
            LEFT JOIN evaluations e
                ON e.participant_id=p.id
            ORDER BY p.id
            """
        ).fetchall()

    legacy_scores = sorted(
        [
            p for p in legacy
            if p["total_score"] is not None
        ],
        key=lambda p: -p["total_score"]
    )

    return render(
        ADMIN_BODY,
        admin_name=admin["username"],
        challenges=challenges,
        account_count=count,
        submissions=submissions,
        legacy=legacy,
        legacy_scores=legacy_scores,
        notice=request.args.get("notice"),
        error=request.args.get("error")
    )


# =============================================
# CHALLENGE EDITING AND ARCHIVING
# =============================================

EDITOR_BODY = """
<div class="heading">
    <h2>Edit Challenge {{ challenge.id }}</h2>
</div>

<div class="panel">
    <form action="/admin/challenge/save"
          method="post">

        <input type="hidden"
               name="_csrf"
               value="{{ csrf }}">

        <input type="hidden"
               name="challenge_id"
               value="{{ challenge.id }}">

        <label>TITLE</label>
        <input name="title"
               maxlength="120"
               value="{{ challenge.title }}"
               required>

        <label>CATEGORY</label>
        <select name="track">
            {% for t in categories %}
            <option
                {% if challenge.track == t %}
                selected
                {% endif %}>
                {{ t }}
            </option>
            {% endfor %}
        </select>

        <label>DESCRIPTION</label>
        <textarea name="description"
                  required>{{ challenge.description }}</textarea>

        <label>DELIVERABLES</label>
        <textarea name="deliverables"
                  required>{{ challenge.deliverables }}</textarea>

        <div class="grid">
            <div>
                <label>DEADLINE</label>
                <input type="date"
                       name="deadline"
                       value="{{ challenge.deadline or '' }}">
            </div>

            <div>
                <label>PRIZE USD</label>
                <input type="number"
                       name="prize_usd"
                       min="0"
                       step=".01"
                       value="{{ challenge.prize_usd }}"
                       required>
            </div>
        </div>

        <label>STATUS</label>
        <select name="status">
            {% for s in statuses %}
            <option
                {% if challenge.status == s %}
                selected
                {% endif %}>
                {{ s }}
            </option>
            {% endfor %}
        </select>

        <button class="btn">
            SAVE CHANGES
        </button>

        <a href="/" class="btn yellow">
            BACK TO ADMIN
        </a>
    </form>
</div>
"""


@app.route("/admin/challenge/<int:challenge_id>/edit")
@required_role("admin")
def edit_challenge(challenge_id):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM challenges WHERE id=?",
            (challenge_id,)
        ).fetchone()

    if not row:
        abort(404)

    return render(
        EDITOR_BODY,
        challenge=row
    )


@app.route("/admin/challenge/save", methods=["POST"])
@required_role("admin")
def save_challenge():
    check_csrf()

    title = request.form.get(
        "title", ""
    ).strip()

    category = request.form.get("track", "")

    description = request.form.get(
        "description", ""
    ).strip()

    deliverables = request.form.get(
        "deliverables", ""
    ).strip()

    status = request.form.get("status", "")

    deadline = request.form.get(
        "deadline", ""
    ).strip() or None

    try:
        prize = float(
            request.form.get("prize_usd", "0")
        )

        challenge_id = (
            int(request.form.get("challenge_id"))
            if request.form.get("challenge_id")
            else None
        )

        if deadline:
            date.fromisoformat(deadline)

    except (ValueError, TypeError):
        return message(
            "admin_dashboard",
            "Invalid deadline, prize, or ID.",
            True
        )

    if (
        not 3 <= len(title) <= 120
        or not 10 <= len(description) <= 5000
        or not 5 <= len(deliverables) <= 3000
        or category not in CATEGORIES
        or status not in STATUSES
        or not 0 <= prize <= 100000
    ):
        return message(
            "admin_dashboard",
            "Check challenge fields.",
            True
        )

    if (
        status == "Open"
        and (
            not deadline
            or deadline < date.today().isoformat()
        )
    ):
        return message(
            "admin_dashboard",
            "Opening a challenge requires "
            "a future deadline.",
            True
        )

    with get_db() as db:
        if challenge_id is None:
            db.execute(
                """
                INSERT INTO challenges
                (
                    title,
                    track,
                    description,
                    deliverables,
                    deadline,
                    prize_usd,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    category,
                    description,
                    deliverables,
                    deadline,
                    prize,
                    status
                )
            )

        else:
            cur = db.execute(
                """
                UPDATE challenges
                SET
                    title=?,
                    track=?,
                    description=?,
                    deliverables=?,
                    deadline=?,
                    prize_usd=?,
                    status=?
                WHERE id=?
                """,
                (
                    title,
                    category,
                    description,
                    deliverables,
                    deadline,
                    prize,
                    status,
                    challenge_id
                )
            )

            if cur.rowcount == 0:
                abort(404)

        db.commit()

    return message(
        "admin_dashboard",
        "Challenge saved successfully."
    )


@app.route(
    "/admin/challenge/<int:challenge_id>/archive",
    methods=["POST"]
)
@required_role("admin")
def archive_challenge(challenge_id):
    check_csrf()

    with get_db() as db:
        db.execute(
            """
            UPDATE challenges
            SET status='Closed'
            WHERE id=?
            """,
            (challenge_id,)
        )
        db.commit()

    return message(
        "admin_dashboard",
        "Challenge archived. Its history is preserved."
    )


# =============================================
# SUBMISSION REVIEW SYSTEM
# =============================================

REVIEW_BODY = """
<div class="heading">
    <h2>Review Submission #{{ submission.id }}</h2>
</div>

<div class="hero">
    <div class="mono gold">// PROJECT EVALUATION</div>

    <h1>
        {{ submission.project_title
           or 'Legacy V6 submission' }}
    </h1>

    <p>
        {{ submission.username }} /
        {{ submission.chosen_track or 'Track unspecified' }} /
        {{ submission.title }}
    </p>
</div>
""" + alerts() + """
<div class="panel">
    <h3>Participant Explanation</h3>

    <p style="white-space:pre-wrap">
        {{ submission.description
           or 'No description (V6).' }}
    </p>

    {% if submission.optional_url %}
    <p>
        <a href="{{ submission.optional_url }}"
           target="_blank"
           rel="noopener noreferrer">
            Supporting link
        </a>
    </p>
    {% endif %}

    {% if submission.project_url %}
    <p>
        <a href="{{ submission.project_url }}"
           target="_blank"
           rel="noopener noreferrer">
            Legacy GitHub link
        </a>
    </p>
    {% endif %}

    <h3>Uploaded Files</h3>

    {% for f in files %}
    <p>
        <a href="/admin/file/{{ f.id }}">
            {{ f.original_name }}
        </a>
        — {{ (f.size_bytes / 1024)|round(1) }} KB
    </p>
    {% else %}
    <p>No files uploaded.</p>
    {% endfor %}
</div>

<div class="panel">
    <h3>Review &amp; Score</h3>

    <form method="post"
          action="/admin/submission/{{ submission.id }}/review">

        <input type="hidden"
               name="_csrf"
               value="{{ csrf }}">

        <label>REVIEW STATUS</label>
        <select name="review_status">
            {% for st in
               ['Submitted', 'Under Review', 'Reviewed'] %}
            <option
                {% if submission.review_status == st %}
                selected
                {% endif %}>
                {{ st }}
            </option>
            {% endfor %}
        </select>

        {% for label,key,maximum in rubric %}
        <label>
            {{ label|upper }} / {{ maximum }}
        </label>

        <input type="number"
               name="{{ key }}"
               min="0"
               max="{{ maximum }}"
               value="{{ review[key] if review else '' }}"
               required>
        {% endfor %}

        <label>FEEDBACK</label>
        <textarea name="feedback"
                  maxlength="3000">{{ review.feedback if review else '' }}</textarea>

        <button class="btn">
            SAVE REVIEW
        </button>

        <a href="/" class="btn yellow">
            BACK TO ADMIN
        </a>
    </form>
</div>
"""


@app.route("/admin/submission/<int:submission_id>")
@required_role("admin")
def review_submission(submission_id):
    with get_db() as db:
        sub = db.execute(
            """
            SELECT
                s.*,
                a.username,
                c.title,
                e.chosen_track
            FROM challenge_submissions s
            JOIN participant_accounts a
                ON a.id=s.participant_id
            JOIN challenges c
                ON c.id=s.challenge_id
            LEFT JOIN enrollments e
                ON e.participant_id=s.participant_id
                AND e.challenge_id=s.challenge_id
            WHERE s.id=?
            """,
            (submission_id,)
        ).fetchone()

        if not sub:
            abort(404)

        files = db.execute(
            """
            SELECT * FROM submission_files
            WHERE submission_id=?
            ORDER BY id
            """,
            (submission_id,)
        ).fetchall()

        review = db.execute(
            """
            SELECT * FROM submission_reviews
            WHERE submission_id=?
            """,
            (submission_id,)
        ).fetchone()

    return render(
        REVIEW_BODY,
        submission=sub,
        files=files,
        review=review,
        rubric=RUBRIC,
        notice=request.args.get("notice"),
        error=request.args.get("error")
    )


@app.route("/admin/file/<int:file_id>")
@required_role("admin")
def admin_file(file_id):
    with get_db() as db:
        row = db.execute(
            """
            SELECT * FROM submission_files
            WHERE id=?
            """,
            (file_id,)
        ).fetchone()

    if not row:
        abort(404)

    return send_file(
        UPLOADS / row["stored_name"],
        as_attachment=True,
        download_name=row["original_name"],
        mimetype="application/octet-stream"
    )


@app.route(
    "/admin/submission/<int:submission_id>/review",
    methods=["POST"]
)
@required_role("admin")
def save_review(submission_id):
    check_csrf()

    try:
        numbers = {
            key: int(request.form.get(key, ""))
            for _, key, _ in RUBRIC
        }

    except ValueError:
        return redirect(
            url_for(
                "review_submission",
                submission_id=submission_id,
                error="Scores must be integers."
            )
        )

    if any(
        not 0 <= numbers[key] <= maximum
        for _, key, maximum in RUBRIC
    ):
        return redirect(
            url_for(
                "review_submission",
                submission_id=submission_id,
                error="Score outside allowed range."
            )
        )

    status = request.form.get(
        "review_status", ""
    )

    feedback = request.form.get(
        "feedback", ""
    ).strip()

    if (
        status not in
        ("Submitted", "Under Review", "Reviewed")
        or len(feedback) > 3000
    ):
        abort(400)

    with get_db() as db:
        row = db.execute(
            """
            SELECT id FROM challenge_submissions
            WHERE id=?
            """,
            (submission_id,)
        ).fetchone()

        if not row:
            abort(404)

        db.execute(
            """
            INSERT INTO submission_reviews
            (
                submission_id,
                accuracy,
                solution,
                feasibility,
                communication,
                originality,
                total_score,
                feedback
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(submission_id)
            DO UPDATE SET
                accuracy=excluded.accuracy,
                solution=excluded.solution,
                feasibility=excluded.feasibility,
                communication=excluded.communication,
                originality=excluded.originality,
                total_score=excluded.total_score,
                feedback=excluded.feedback,
                reviewed_at=CURRENT_TIMESTAMP
            """,
            (
                submission_id,
                numbers["accuracy"],
                numbers["solution"],
                numbers["feasibility"],
                numbers["communication"],
                numbers["originality"],
                sum(numbers.values()),
                feedback
            )
        )

        db.execute(
            """
            UPDATE challenge_submissions
            SET review_status=?
            WHERE id=?
            """,
            (status, submission_id)
        )

        db.commit()

    return redirect(
        url_for(
            "review_submission",
            submission_id=submission_id,
            notice="Review saved."
        )
    )


# =============================================
# ERROR HANDLING AND APPLICATION STARTUP
# =============================================

@app.errorhandler(413)
def too_large(_):
    return render(
        """
        <div class="error">
            Upload too large.
            Maximum combined request size is 26 MB.
        </div>

        <a class="btn" href="/participant">
            BACK TO WORKSPACE
        </a>
        """
    ), 413


initialize_database()


if __name__ == "__main__":
    print("=" * 48)
    print(
        "BRIDGELAB V7 — MULTIDISCIPLINARY PROJECT SYSTEM"
    )
    print("Admin: http://127.0.0.1:5001")
    print(
        "Participant: "
        "http://127.0.0.1:5001/participant/login"
    )
    print(
        "Catalog: http://127.0.0.1:5001/challenges"
    )
    print("LOCAL DEMONSTRATION ONLY")
    print("=" * 48)

    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False
    )
