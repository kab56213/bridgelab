
from pathlib import Path
from functools import wraps
from datetime import date, timedelta
from urllib.parse import urlparse
import sqlite3
import secrets
import hmac
import sys
import time

from flask import (
    Flask, request, redirect, url_for,
    render_template_string, session, abort
)

ROOT = Path(__file__).resolve().parent.parent
INSTANCE = ROOT / "instance"
DB_PATH = INSTANCE / "bridgelab.db"
SECRET_PATH = INSTANCE / ".flask_secret"

sys.path.insert(0, str(ROOT))

from auth.security import hash_password, verify_password
from evaluation.scoring_engine import (
    Evaluation, CRITERIA, rank_submissions
)

INSTANCE.mkdir(exist_ok=True)

if not SECRET_PATH.exists():
    SECRET_PATH.write_text(secrets.token_hex(32))

app = Flask(__name__)
app.secret_key = SECRET_PATH.read_text().strip()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    MAX_CONTENT_LENGTH=1024 * 1024
)

TRACKS = [
    "Data Analytics",
    "Software Development",
    "Business Analysis"
]

STATUSES = ["Draft", "Open", "Closed"]

LOGIN_ATTEMPTS = {}
MAX_ATTEMPTS = 5
LOCK_SECONDS = 300


# =============================================
# DATABASE AND MIGRATION
# =============================================

def get_db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
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
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(participant_id)
                REFERENCES participants(id)
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
            evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(participant_id)
                REFERENCES participants(id)
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
        """)

        count = db.execute(
            "SELECT COUNT(*) FROM challenges"
        ).fetchone()[0]

        if count == 0:
            db.execute("""
                INSERT INTO challenges
                (title, track, description, deliverables,
                 deadline, prize_usd, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                "Retail Analytics Challenge 001",
                "Data Analytics",
                "Analyze a synthetic retail dataset and "
                "recommend business improvements.",
                "Cleaned data, analysis, charts, "
                "recommendations, and GitHub repository.",
                None, 100, "Draft"
            ))

        db.commit()


# =============================================
# SECURITY AND UTILITIES
# =============================================

def token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_token():
    supplied = request.form.get("_csrf", "")
    if not hmac.compare_digest(supplied, token()):
        abort(400, "Invalid form token.")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("admin_login"))

        with get_db() as db:
            user = db.execute(
                "SELECT id FROM admins WHERE id = ?",
                (session.get("user_id"),)
            ).fetchone()

        if user is None:
            session.clear()
            return redirect(url_for("admin_login"))

        return fn(*args, **kwargs)
    return wrapper


def participant_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "participant":
            return redirect(url_for("participant_login"))

        with get_db() as db:
            user = db.execute(
                "SELECT id FROM participant_accounts WHERE id = ?",
                (session.get("user_id"),)
            ).fetchone()

        if user is None:
            session.clear()
            return redirect(url_for("participant_login"))

        return fn(*args, **kwargs)
    return wrapper


def login_allowed(key):
    now = time.monotonic()
    recent = [
        t for t in LOGIN_ATTEMPTS.get(key, [])
        if now - t < LOCK_SECONDS
    ]
    LOGIN_ATTEMPTS[key] = recent
    return len(recent) < MAX_ATTEMPTS


def record_failure(key):
    LOGIN_ATTEMPTS.setdefault(key, []).append(
        time.monotonic()
    )


def start_session(user_id, role):
    session.clear()
    session["user_id"] = user_id
    session["role"] = role
    session.permanent = True
    session["_csrf"] = secrets.token_urlsafe(32)


def notify(text, error=False):
    return redirect(url_for(
        "admin_dashboard",
        **{"error" if error else "notice": text}
    ))


def valid_handle(value):
    return (
        3 <= len(value) <= 40
        and all(c.isalnum() or c in "_-" for c in value)
    )


def valid_github(value):
    try:
        u = urlparse(value)
        parts = u.path.strip("/").split("/")
        return (
            u.scheme == "https"
            and u.hostname == "github.com"
            and u.port in (None, 443)
            and not u.username
            and not u.password
            and len(parts) == 2
            and all(parts)
            and len(value) <= 500
        )
    except ValueError:
        return False


def is_open(challenge):
    return (
        challenge["status"] == "Open"
        and challenge["deadline"] is not None
        and challenge["deadline"] >= date.today().isoformat()
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
    --muted:#687385;
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body {
    margin:0;
    background:var(--cream);
    color:var(--navy);
    font:14px Arial,sans-serif;
}
a { color:var(--blue); }
input,select,textarea,button { font:inherit; }
input,select,textarea {
    width:100%;
    padding:12px;
    background:white;
    border:1px solid #a0a6ae;
    border-radius:0;
}
textarea { min-height:100px; }
label {
    display:block;
    margin:15px 0 7px;
    font:bold 11px "Courier New",monospace;
}
button { cursor:pointer; }
button:disabled { opacity:.5; cursor:not-allowed; }
.top {
    background:var(--navy);
    color:white;
    padding:12px 4%;
    display:flex;
    justify-content:space-between;
    flex-wrap:wrap;
    gap:12px;
    font:11px "Courier New",monospace;
}
.top a { color:white; }
.shell {
    max-width:1480px;
    margin:auto;
    padding:30px 24px 65px;
}
.brand {
    display:flex;
    align-items:center;
    justify-content:space-between;
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
    font:11px "Courier New",monospace;
    margin-top:7px;
    color:var(--muted);
}
.stamp {
    background:var(--yellow);
    border:1px solid var(--navy);
    padding:12px;
    box-shadow:4px 4px 0 var(--navy);
    font:bold 11px "Courier New",monospace;
}
.layout {
    display:grid;
    grid-template-columns:225px minmax(0,1fr);
    gap:26px;
    margin-top:25px;
}
.sidebar {
    background:var(--paper);
    border:1px solid var(--navy);
    padding:18px;
    height:fit-content;
    box-shadow:4px 4px 0 var(--navy);
}
.sidebar a {
    display:block;
    padding:13px 7px;
    border-top:1px dashed var(--line);
    text-decoration:none;
    font-weight:bold;
}
.sidebar a:hover { background:#e5eaff; }
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
    max-width:620px;
    line-height:1.8;
    color:#d3ddea;
}
.mono {
    font:bold 11px "Courier New",monospace;
}
.gold { color:var(--yellow); }
.heading {
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin:30px 0 15px;
    gap:10px;
}
.heading h2 {
    font:bold 24px Georgia,serif;
    margin:0;
}
.panel,.challenge,.stat {
    background:var(--paper);
    border:1px solid var(--navy);
    box-shadow:3px 3px 0 #c1c4c9;
}
.panel-head {
    padding:13px 18px;
    border-bottom:1px solid var(--navy);
    background:#e8e8e3;
    font:bold 11px "Courier New",monospace;
}
.panel-body { padding:20px; }
.columns {
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:18px;
}
.stats {
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:13px;
}
.stat { padding:20px; }
.stat:nth-child(2) { background:#e5eaff; }
.stat:nth-child(4) { background:var(--mint); }
.stat strong {
    display:block;
    font:bold 39px Georgia,serif;
    margin-top:12px;
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
    font:bold 10px "Courier New",monospace;
}
.pill.Draft { background:#e5e5ee; }
.pill.Closed { background:#f6deda; }
.btn {
    display:inline-block;
    background:var(--blue);
    color:white;
    border:1px solid var(--navy);
    padding:13px 18px;
    margin-top:18px;
    text-decoration:none;
    font:bold 11px "Courier New",monospace;
    box-shadow:3px 3px 0 var(--navy);
}
.btn-yellow {
    background:var(--yellow);
    color:var(--navy);
}
.notice {
    background:var(--mint);
    border:1px solid #789b82;
    padding:14px;
    margin:16px 0;
}
.warning {
    background:#fff0c4;
    border:1px solid #ba9b53;
    padding:14px;
    margin:16px 0;
}
.error {
    background:#ffe2df;
    border:1px solid #be7c71;
    padding:14px;
    margin:16px 0;
}
.table-scroll { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th,td {
    padding:13px;
    border-bottom:1px solid var(--line);
    text-align:left;
}
th {
    background:#e8e8e3;
    font:bold 11px "Courier New",monospace;
}
.score-grid {
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:12px;
}
footer {
    margin-top:45px;
    padding-top:20px;
    border-top:1px solid var(--navy);
    color:var(--muted);
    font:11px "Courier New",monospace;
}
.authbox {
    max-width:470px;
    margin:55px auto;
    background:var(--paper);
    border:2px solid var(--navy);
    padding:33px;
    box-shadow:7px 7px 0 var(--navy);
}
@media(max-width:950px) {
    .layout { grid-template-columns:1fr; }
    .columns { grid-template-columns:1fr; }
    .score-grid { grid-template-columns:repeat(2,1fr); }
}
@media(max-width:650px) {
    .shell { padding:18px 12px; }
    .stats { grid-template-columns:repeat(2,1fr); }
    .stat strong { font-size:30px; }
    .stamp { display:none; }
    .hero { padding:23px; }
}
"""


def page(content, title="Challenge Control"):
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>BridgeLab — ' + title + '</title>'
        '<style>' + CSS + '</style></head><body>'
        + content + '</body></html>'
    )


HEADER = """
<div class="top">
    <span>BRIDGELAB NETWORK // PROJECT SYSTEM</span>
    <span>
        <a href="/challenges">CHALLENGES</a> /
        <a href="/participant/login">PARTICIPANT</a> /
        <a href="/login">ADMIN</a>
    </span>
</div>
<div class="shell">
    <div class="brand">
        <div>
            <div class="logo">BridgeLab<span>.</span></div>
            <div class="tagline">
                BUILD SKILLS / SOLVE PROBLEMS / CREATE IMPACT
            </div>
        </div>
        <div class="stamp">SYSTEM V6.0 / DEMO</div>
    </div>
"""

FOOTER = """
<footer>
    BRIDGELAB / INDEPENDENT PROJECT INITIATIVE
    — LOCAL DEVELOPMENT
</footer></div>
"""


# =============================================
# AUTHENTICATION PAGES
# =============================================

AUTH_TEMPLATE = page(
    HEADER + """
    <div class="authbox">
        <div class="mono">/ SECURE ACCESS TERMINAL</div>
        <h1 style="font: bold 34px Georgia,serif">
            {{ title }}
        </h1>
        <p>{{ description }}</p>

        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

        <form method="post">
            <input type="hidden" name="_csrf" value="{{ csrf }}">

            <label>USERNAME</label>
            <input name="username" maxlength="40"
                   autocomplete="username" required>

            {% if register %}
                <label>SKILL TRACK</label>
                <select name="skill">
                    {% for track in tracks %}
                    <option>{{ track }}</option>
                    {% endfor %}
                </select>
            {% endif %}

            <label>PASSWORD</label>
            <input type="password" name="password"
                   minlength="{{ 12 if register else 1 }}"
                   autocomplete="{{ 'new-password' if register else 'current-password' }}"
                   required>

            <button class="btn" type="submit">
                {{ button_text }} →
            </button>
        </form>

        <p style="margin-top:25px">
            <a href="{{ alternate_url }}">{{ alternate_text }}</a>
        </p>
    </div>
    """ + FOOTER,
    "Account Access"
)


def render_auth(title, description, button, register=False,
                error=None, alternate_url="/challenges",
                alternate_text="Back to challenges"):
    return render_template_string(
        AUTH_TEMPLATE,
        title=title,
        description=description,
        button_text=button,
        register=register,
        tracks=TRACKS,
        csrf=token(),
        error=error,
        alternate_url=alternate_url,
        alternate_text=alternate_text
    )


@app.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        check_token()

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        key = ("admin", request.remote_addr)

        if not login_allowed(key):
            error = "Too many attempts. Try again later."
        else:
            with get_db() as db:
                account = db.execute(
                    "SELECT * FROM admins WHERE username = ?",
                    (username,)
                ).fetchone()

            if account and verify_password(
                account["password_hash"], password
            ):
                LOGIN_ATTEMPTS.pop(key, None)
                start_session(account["id"], "admin")
                return redirect(url_for("admin_dashboard"))

            record_failure(key)
            error = "Invalid username or password."

        return render_auth(
            "Administrator Login",
            "Private challenge management workspace.",
            "Access Admin Dashboard",
            error=error
        ), 401

    return render_auth(
        "Administrator Login",
        "Private challenge management workspace.",
        "Access Admin Dashboard"
    )


@app.route("/participant/register", methods=["GET", "POST"])
def participant_register():
    if request.method == "POST":
        check_token()

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        skill = request.form.get("skill", "")

        if not valid_handle(username) or skill not in TRACKS:
            error = "Invalid username or skill track."
        elif len(password) < 12 or len(password) > 256:
            error = "Use a password between 12 and 256 characters."
        else:
            try:
                with get_db() as db:
                    cursor = db.execute("""
                        INSERT INTO participant_accounts
                            (username, password_hash, skill)
                        VALUES (?, ?, ?)
                    """, (
                        username,
                        hash_password(password),
                        skill
                    ))
                    db.commit()
                    new_id = cursor.lastrowid

                start_session(new_id, "participant")
                return redirect(url_for("participant_dashboard"))

            except sqlite3.IntegrityError:
                error = "This username is already taken."

        return render_auth(
            "Join the Lab",
            "Create a fictional demonstration account.",
            "Create Account",
            register=True,
            error=error,
            alternate_url="/participant/login",
            alternate_text="Already have an account? Sign in"
        ), 400

    return render_auth(
        "Join the Lab",
        "Local test accounts only. Do not enter real personal information.",
        "Create Account",
        register=True,
        alternate_url="/participant/login",
        alternate_text="Already have an account? Sign in"
    )


@app.route("/participant/login", methods=["GET", "POST"])
def participant_login():
    if request.method == "POST":
        check_token()

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        key = ("participant", request.remote_addr)

        if not login_allowed(key):
            error = "Too many attempts. Try again later."
        else:
            with get_db() as db:
                account = db.execute("""
                    SELECT * FROM participant_accounts
                    WHERE username = ?
                """, (username,)).fetchone()

            if account and verify_password(
                account["password_hash"], password
            ):
                LOGIN_ATTEMPTS.pop(key, None)
                start_session(account["id"], "participant")
                return redirect(url_for("participant_dashboard"))

            record_failure(key)
            error = "Invalid username or password."

        return render_auth(
            "Participant Login",
            "Access your personal project workspace.",
            "Sign In",
            error=error,
            alternate_url="/participant/register",
            alternate_text="Create a demo account"
        ), 401

    return render_auth(
        "Participant Login",
        "Access your personal project workspace.",
        "Sign In",
        alternate_url="/participant/register",
        alternate_text="Create a demo account"
    )


@app.route("/logout", methods=["POST"])
def logout():
    check_token()
    session.clear()
    return redirect(url_for("public_challenges"))


# =============================================
# PUBLIC CHALLENGES
# =============================================

PUBLIC_TEMPLATE = page(
    HEADER + """
    <div class="hero" style="margin-top:25px">
        <div class="mono gold">// PROJECT DIRECTORY</div>
        <h1>Build. Learn. Prove.</h1>
        <p>
            Explore technical challenges designed around
            practical problem-solving and portfolio development.
        </p>
        <a class="btn btn-yellow" href="/participant/register">
            CREATE PARTICIPANT ACCOUNT →
        </a>
    </div>

    <div class="warning">
        LOCAL PROTOTYPE — Demo challenges and accounts only.
        Not open for real applications.
    </div>

    <div class="heading">
        <h2>Open Challenges</h2>
        <span class="mono">{{ challenges|length }} AVAILABLE</span>
    </div>

    {% for c in challenges %}
    <article class="challenge">
        <div class="mono">
            PROJECT / {{ "%03d"|format(c.id) }}
        </div>
        <h3>{{ c.title }}</h3>
        <span class="pill">{{ c.track }}</span>
        <span class="pill">USD ${{ "%.2f"|format(c.prize_usd) }}</span>
        <span class="pill">DUE {{ c.deadline }}</span>
        <p>{{ c.description }}</p>
        <p><strong>Deliverables:</strong> {{ c.deliverables }}</p>
        <a class="btn" href="/participant">
            VIEW IN WORKSPACE →
        </a>
    </article>
    {% else %}
        <div class="panel">
            <div class="panel-body">
                No Open challenges are available yet.
                The first challenge is still being prepared.
            </div>
        </div>
    {% endfor %}
    """ + FOOTER,
    "Challenge Directory"
)


@app.route("/challenges")
def public_challenges():
    with get_db() as db:
        challenges = db.execute("""
            SELECT * FROM challenges
            WHERE status = 'Open'
              AND deadline >= ?
            ORDER BY deadline, id
        """, (date.today().isoformat(),)).fetchall()

    return render_template_string(
        PUBLIC_TEMPLATE, challenges=challenges
    )


# =============================================
# PARTICIPANT DASHBOARD
# =============================================

PARTICIPANT_TEMPLATE = page(
    HEADER + """
    <div class="layout">
        <nav class="sidebar">
            <div class="mono">/ PARTICIPANT DESK</div>
            <a href="#overview">01 Overview</a>
            <a href="#my-projects">02 My Projects</a>
            <a href="#available">03 Challenges</a>
            <form method="post" action="/logout">
                <input type="hidden" name="_csrf" value="{{ csrf }}">
                <button class="btn btn-yellow">LOG OUT</button>
            </form>
        </nav>

        <main>
            <div class="hero" id="overview">
                <div class="mono gold">
                    // PARTICIPANT WORKSPACE
                </div>
                <h1>Welcome, {{ account.username }}.</h1>
                <p>
                    Explore challenges, enroll in projects,
                    and track your submitted work.
                </p>
                <span class="mono gold">{{ account.skill }}</span>
            </div>

            <div class="warning">
                Test environment. All accounts and projects
                must use fictional information.
            </div>

            {% if notice %}
                <div class="notice">{{ notice }}</div>
            {% endif %}
            {% if error %}
                <div class="error">{{ error }}</div>
            {% endif %}

            <div class="heading" id="my-projects">
                <h2>My Projects</h2>
                <span class="mono">{{ enrollments|length }} ENROLLED</span>
            </div>

            {% for e in enrollments %}
                <div class="challenge">
                    <span class="mono">
                        CHALLENGE {{ "%03d"|format(e.id) }}
                    </span>
                    <h3>{{ e.title }}</h3>
                    <span class="pill">{{ e.status }}</span>
                    <span class="pill">
                        DUE {{ e.deadline or "NOT SET" }}
                    </span>
                    <span class="pill">
                        {{ e.review_status or "Not Submitted" }}
                    </span>

                    {% if e.project_url %}
                    <p>
                        <a href="{{ e.project_url }}"
                           target="_blank"
                           rel="noopener noreferrer">
                            View submitted project ↗
                        </a>
                    </p>
                    {% endif %}

                    {% if e.can_submit and e.review_status != "Under Review" %}
                    <form method="post" action="/participant/submit">
                        <input type="hidden"
                               name="_csrf" value="{{ csrf }}">
                        <input type="hidden"
                               name="challenge_id" value="{{ e.id }}">
                        <label>GITHUB REPOSITORY URL</label>
                        <input name="project_url" type="url"
                               placeholder="https://github.com/owner/repo"
                               value="{{ e.project_url or '' }}"
                               required>
                        <button class="btn">
                            SAVE PROJECT SUBMISSION
                        </button>
                    </form>
                    {% else %}
                    <p class="mono">
                        SUBMISSION CURRENTLY UNAVAILABLE
                    </p>
                    {% endif %}
                </div>
            {% else %}
                <div class="panel">
                    <div class="panel-body">
                        You have not enrolled in a challenge.
                    </div>
                </div>
            {% endfor %}

            <div class="heading" id="available">
                <h2>Available Challenges</h2>
                <span class="mono">OPEN PROJECTS</span>
            </div>

            {% for c in challenges %}
                <div class="challenge">
                    <h3>{{ c.title }}</h3>
                    <span class="pill">{{ c.track }}</span>
                    <span class="pill">
                        DUE {{ c.deadline }}
                    </span>
                    <p>{{ c.description }}</p>
                    <p>
                        <strong>Deliverables:</strong>
                        {{ c.deliverables }}
                    </p>
                    <form method="post" action="/participant/enroll">
                        <input type="hidden"
                               name="_csrf" value="{{ csrf }}">
                        <input type="hidden"
                               name="challenge_id" value="{{ c.id }}">
                        <button class="btn btn-yellow">
                            ENROLL IN CHALLENGE →
                        </button>
                    </form>
                </div>
            {% else %}
                <div class="panel">
                    <div class="panel-body">
                        No new challenges available.
                    </div>
                </div>
            {% endfor %}
        </main>
    </div>
    """ + FOOTER,
    "Participant Workspace"
)


@app.route("/participant")
@participant_required
def participant_dashboard():
    participant_id = session["user_id"]

    with get_db() as db:
        account = db.execute("""
            SELECT * FROM participant_accounts WHERE id = ?
        """, (participant_id,)).fetchone()

        rows = db.execute("""
            SELECT c.*, s.project_url, s.review_status
            FROM enrollments e
            JOIN challenges c ON e.challenge_id = c.id
            LEFT JOIN challenge_submissions s
                ON s.challenge_id = c.id
                AND s.participant_id = e.participant_id
            WHERE e.participant_id = ?
            ORDER BY e.id DESC
        """, (participant_id,)).fetchall()

        available = db.execute("""
            SELECT * FROM challenges
            WHERE status = 'Open' AND deadline >= ?
            AND id NOT IN (
                SELECT challenge_id FROM enrollments
                WHERE participant_id = ?
            )
            ORDER BY deadline
        """, (
            date.today().isoformat(),
            participant_id
        )).fetchall()

    enrollments = []

    for row in rows:
        item = dict(row)
        item["can_submit"] = is_open(row)
        enrollments.append(item)

    return render_template_string(
        PARTICIPANT_TEMPLATE,
        account=account,
        enrollments=enrollments,
        challenges=available,
        csrf=token(),
        notice=request.args.get("notice"),
        error=request.args.get("error")
    )


def participant_message(text, error=False):
    return redirect(url_for(
        "participant_dashboard",
        **{"error" if error else "notice": text}
    ))


@app.route("/participant/enroll", methods=["POST"])
@participant_required
def participant_enroll():
    check_token()

    try:
        challenge_id = int(request.form.get("challenge_id", ""))
    except ValueError:
        return participant_message("Invalid challenge.", True)

    with get_db() as db:
        challenge = db.execute(
            "SELECT * FROM challenges WHERE id = ?",
            (challenge_id,)
        ).fetchone()

        if challenge is None or not is_open(challenge):
            return participant_message(
                "Challenge is not open for enrollment.", True
            )

        db.execute("""
            INSERT OR IGNORE INTO enrollments
            (participant_id, challenge_id)
            VALUES (?, ?)
        """, (session["user_id"], challenge_id))
        db.commit()

    return participant_message("Enrolled successfully.")


@app.route("/participant/submit", methods=["POST"])
@participant_required
def participant_submit():
    check_token()

    try:
        challenge_id = int(request.form.get("challenge_id", ""))
    except ValueError:
        return participant_message("Invalid challenge.", True)

    project_url = request.form.get("project_url", "").strip()

    if not valid_github(project_url):
        return participant_message(
            "Enter a valid GitHub repository URL.", True
        )

    with get_db() as db:
        enrolled = db.execute("""
            SELECT c.*, s.review_status
            FROM enrollments e
            JOIN challenges c ON c.id = e.challenge_id
            LEFT JOIN challenge_submissions s
                ON s.challenge_id = c.id
                AND s.participant_id = e.participant_id
            WHERE e.participant_id = ? AND e.challenge_id = ?
        """, (session["user_id"], challenge_id)).fetchone()

        if enrolled is None or not is_open(enrolled):
            return participant_message(
                "Challenge is closed or enrollment is missing.",
                True
            )

        if enrolled["review_status"] == "Under Review":
            return participant_message(
                "Submission is locked for review.", True
            )

        db.execute("""
            INSERT INTO challenge_submissions
                (participant_id, challenge_id, project_url)
            VALUES (?, ?, ?)
            ON CONFLICT(participant_id, challenge_id)
            DO UPDATE SET
                project_url = excluded.project_url,
                review_status = 'Submitted',
                submitted_at = CURRENT_TIMESTAMP
        """, (
            session["user_id"], challenge_id, project_url
        ))
        db.commit()

    return participant_message("Project saved successfully.")


# =============================================
# ADMIN DASHBOARD
# =============================================

ADMIN_TEMPLATE = page(
    HEADER + """
    <div class="layout">
        <nav class="sidebar">
            <div class="mono">/ ADMIN WORKSPACE</div>
            <a href="#overview">01 Overview</a>
            <a href="#challenges">02 Challenges</a>
            <a href="#editor">03 Challenge Editor</a>
            <a href="#participants">04 Legacy Demo</a>
            <a href="#submissions">05 New Submissions</a>
            <a href="#leaderboard">06 Legacy Leaderboard</a>
            <form action="/logout" method="post">
                <input type="hidden"
                       name="_csrf" value="{{ csrf }}">
                <button class="btn btn-yellow">LOG OUT</button>
            </form>
        </nav>

        <main>
            <div class="hero" id="overview">
                <div class="mono gold">
                    // AUTHORIZED ADMINISTRATOR
                </div>
                <h1>BridgeLab Control Center.</h1>
                <p>
                    Manage challenges, monitor participants,
                    and oversee the project lifecycle.
                </p>
                <span class="mono gold">
                    ADMIN: {{ admin_name }}
                </span>
            </div>

            <div class="warning">
                V6 LOCAL DEMO: Do not invite real participants.
                Authentication and workflows require more testing.
            </div>

            {% if notice %}
                <div class="notice">{{ notice }}</div>
            {% endif %}
            {% if error %}
                <div class="error">{{ error }}</div>
            {% endif %}

            <div class="heading">
                <h2>Control Overview</h2>
                <span class="mono">LIVE DATABASE</span>
            </div>

            <div class="stats">
                <div class="stat">
                    <span class="mono">CHALLENGES</span>
                    <strong>{{ challenges|length }}</strong>
                </div>
                <div class="stat">
                    <span class="mono">NEW ACCOUNTS</span>
                    <strong>{{ account_count }}</strong>
                </div>
                <div class="stat">
                    <span class="mono">NEW SUBMISSIONS</span>
                    <strong>{{ new_submissions|length }}</strong>
                </div>
                <div class="stat">
                    <span class="mono">LEGACY SCORES</span>
                    <strong>{{ legacy_scores|length }}</strong>
                </div>
            </div>

            <div class="heading" id="challenges">
                <h2>Challenge Catalog</h2>
                <span class="mono">PROJECT LIBRARY</span>
            </div>

            {% for c in challenges %}
            <article class="challenge">
                <div class="mono">
                    CHALLENGE / {{ "%03d"|format(c.id) }}
                </div>
                <h3>{{ c.title }}</h3>
                <span class="pill {{ c.status }}">{{ c.status }}</span>
                <span class="pill">{{ c.track }}</span>
                <span class="pill">
                    ${{ "%.2f"|format(c.prize_usd) }} USD
                </span>
                <span class="pill">
                    DUE {{ c.deadline or "NOT SET" }}
                </span>
                <p>{{ c.description }}</p>
                <p><strong>Deliverables:</strong>
                    {{ c.deliverables }}</p>
                <a class="btn btn-yellow"
                   href="/admin/challenge/{{ c.id }}/edit">
                    EDIT CHALLENGE →
                </a>
            </article>
            {% endfor %}

            <div class="heading" id="editor">
                <h2>Create a Challenge</h2>
                <span class="mono">NEW PROJECT</span>
            </div>

            <div class="panel">
                <div class="panel-head">CHALLENGE CONFIGURATION</div>
                <div class="panel-body">
                    <form method="post" action="/admin/challenge/save">
                        <input type="hidden" name="_csrf"
                               value="{{ csrf }}">
                        <label>TITLE</label>
                        <input name="title" maxlength="120" required>

                        <label>SKILL TRACK</label>
                        <select name="track">
                            {% for track in tracks %}
                            <option>{{ track }}</option>
                            {% endfor %}
                        </select>

                        <label>DESCRIPTION</label>
                        <textarea name="description" required></textarea>

                        <label>DELIVERABLES</label>
                        <textarea name="deliverables" required></textarea>

                        <div class="columns">
                            <div>
                                <label>DEADLINE</label>
                                <input type="date" name="deadline">
                            </div>
                            <div>
                                <label>PRIZE USD</label>
                                <input name="prize_usd" type="number"
                                       min="0" step=".01" value="0">
                            </div>
                        </div>

                        <label>STATUS</label>
                        <select name="status">
                            {% for status in statuses %}
                            <option>{{ status }}</option>
                            {% endfor %}
                        </select>

                        <button class="btn">CREATE CHALLENGE</button>
                    </form>
                </div>
            </div>

            <div class="heading" id="participants">
                <h2>Legacy Demo Records</h2>
                <span class="mono">PRESERVED FROM V5</span>
            </div>

            <div class="panel table-scroll">
                <table>
                    <tr>
                        <th>PARTICIPANT</th>
                        <th>SKILL</th>
                        <th>PROJECT</th>
                        <th>SCORE</th>
                    </tr>
                    {% for p in legacy %}
                    <tr>
                        <td>{{ p.username }}</td>
                        <td>{{ p.skill }}</td>
                        <td>
                            {% if p.project_url %}
                            <a href="{{ p.project_url }}"
                               target="_blank"
                               rel="noopener noreferrer">VIEW ↗</a>
                            {% else %}PENDING{% endif %}
                        </td>
                        <td>
                            {{ p.total_score if p.total_score is not none else "—" }}
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div class="heading" id="submissions">
                <h2>Challenge Submissions</h2>
                <span class="mono">V6 WORKFLOW</span>
            </div>

            <div class="panel table-scroll">
                <table>
                    <tr>
                        <th>PARTICIPANT</th>
                        <th>CHALLENGE</th>
                        <th>PROJECT</th>
                        <th>STATUS</th>
                    </tr>
                    {% for s in new_submissions %}
                    <tr>
                        <td>{{ s.username }}</td>
                        <td>{{ s.title }}</td>
                        <td>
                            <a href="{{ s.project_url }}"
                               target="_blank"
                               rel="noopener noreferrer">VIEW ↗</a>
                        </td>
                        <td>{{ s.review_status }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="4">
                        NO CHALLENGE-LINKED SUBMISSIONS YET
                    </td></tr>
                    {% endfor %}
                </table>
            </div>

            <div class="heading" id="leaderboard">
                <h2>Legacy Leaderboard</h2>
                <span class="mono">DEMO SCORES</span>
            </div>
            <div class="panel table-scroll">
                <table>
                    <tr>
                        <th>RANK</th>
                        <th>PARTICIPANT</th>
                        <th>SCORE</th>
                    </tr>
                    {% for s in legacy_scores %}
                    <tr>
                        <td>#{{ loop.index }}</td>
                        <td>{{ s.username }}</td>
                        <td>{{ s.total_score }}/100</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="3">NO DEMO SCORES</td></tr>
                    {% endfor %}
                </table>
            </div>
        </main>
    </div>
    """ + FOOTER,
    "Admin Control V6"
)


@app.route("/")
@admin_required
def admin_dashboard():
    with get_db() as db:
        admin = db.execute(
            "SELECT username FROM admins WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

        challenges = db.execute(
            "SELECT * FROM challenges ORDER BY id DESC"
        ).fetchall()

        account_count = db.execute(
            "SELECT COUNT(*) FROM participant_accounts"
        ).fetchone()[0]

        new_submissions = db.execute("""
            SELECT a.username, c.title,
                   s.project_url, s.review_status
            FROM challenge_submissions s
            JOIN participant_accounts a ON a.id = s.participant_id
            JOIN challenges c ON c.id = s.challenge_id
            ORDER BY s.submitted_at DESC
        """).fetchall()

        legacy = db.execute("""
            SELECT p.*, s.project_url, e.total_score
            FROM participants p
            LEFT JOIN submissions s ON s.participant_id = p.id
            LEFT JOIN evaluations e ON e.participant_id = p.id
            ORDER BY p.id
        """).fetchall()

    legacy_scores = sorted(
        [p for p in legacy if p["total_score"] is not None],
        key=lambda p: (-p["total_score"], p["id"])
    )

    return render_template_string(
        ADMIN_TEMPLATE,
        admin_name=admin["username"],
        challenges=challenges,
        account_count=account_count,
        new_submissions=new_submissions,
        legacy=legacy,
        legacy_scores=legacy_scores,
        tracks=TRACKS,
        statuses=STATUSES,
        csrf=token(),
        notice=request.args.get("notice"),
        error=request.args.get("error")
    )


# =============================================
# CHALLENGE CREATION AND EDITING
# =============================================

EDIT_TEMPLATE = page(
    HEADER + """
    <div class="heading">
        <h2>Edit Challenge</h2>
        <span class="mono">PROJECT / {{ challenge.id }}</span>
    </div>

    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}

    <div class="panel">
        <div class="panel-body">
            <form action="/admin/challenge/save" method="post">
                <input type="hidden" name="_csrf" value="{{ csrf }}">
                <input type="hidden" name="challenge_id"
                       value="{{ challenge.id }}">

                <label>TITLE</label>
                <input name="title" value="{{ challenge.title }}"
                       required>

                <label>SKILL TRACK</label>
                <select name="track">
                    {% for t in tracks %}
                    <option {% if t == challenge.track %}selected{% endif %}>
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

                <label>DEADLINE</label>
                <input type="date" name="deadline"
                       value="{{ challenge.deadline or '' }}">

                <label>PRIZE USD</label>
                <input type="number" name="prize_usd"
                       min="0" step=".01"
                       value="{{ challenge.prize_usd }}" required>

                <label>STATUS</label>
                <select name="status">
                    {% for s in statuses %}
                    <option {% if s == challenge.status %}selected{% endif %}>
                        {{ s }}
                    </option>
                    {% endfor %}
                </select>

                <button class="btn">SAVE CHANGES</button>
                <a class="btn btn-yellow" href="/">BACK TO ADMIN</a>
            </form>
        </div>
    </div>
    """ + FOOTER,
    "Edit Challenge"
)


@app.route("/admin/challenge/<int:challenge_id>/edit")
@admin_required
def edit_challenge(challenge_id):
    with get_db() as db:
        challenge = db.execute(
            "SELECT * FROM challenges WHERE id = ?",
            (challenge_id,)
        ).fetchone()

    if challenge is None:
        abort(404)

    return render_template_string(
        EDIT_TEMPLATE,
        challenge=challenge,
        tracks=TRACKS,
        statuses=STATUSES,
        csrf=token(),
        error=request.args.get("error")
    )


@app.route("/admin/challenge/save", methods=["POST"])
@admin_required
def save_challenge():
    check_token()

    raw_id = request.form.get("challenge_id", "").strip()

    try:
        challenge_id = int(raw_id) if raw_id else None
        title = request.form.get("title", "").strip()
        track = request.form.get("track", "")
        status = request.form.get("status", "")
        description = request.form.get("description", "").strip()
        deliverables = request.form.get("deliverables", "").strip()
        deadline = request.form.get("deadline", "").strip()
        prize = float(request.form.get("prize_usd", "0"))

        if not (
            1 <= len(title) <= 120
            and track in TRACKS
            and status in STATUSES
            and 1 <= len(description) <= 3000
            and 1 <= len(deliverables) <= 3000
            and 0 <= prize <= 100000
            and prize == prize
        ):
            raise ValueError("Invalid challenge fields.")

        if deadline:
            date.fromisoformat(deadline)

        if status == "Open":
            if not deadline or deadline <= date.today().isoformat():
                raise ValueError("An Open challenge needs a future deadline.")

    except (ValueError, OverflowError) as exc:
        return notify(str(exc), True)

    with get_db() as db:
        if challenge_id is None:
            db.execute("""
                INSERT INTO challenges
                (title, track, description, deliverables,
                 deadline, prize_usd, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                title, track, description, deliverables,
                deadline or None, prize, status
            ))
        else:
            row = db.execute(
                "SELECT id FROM challenges WHERE id = ?",
                (challenge_id,)
            ).fetchone()

            if row is None:
                return notify("Challenge not found.", True)

            db.execute("""
                UPDATE challenges SET
                    title=?, track=?, description=?,
                    deliverables=?, deadline=?,
                    prize_usd=?, status=?
                WHERE id=?
            """, (
                title, track, description, deliverables,
                deadline or None, prize, status,
                challenge_id
            ))

        db.commit()

    return notify("Challenge saved successfully.")


# =============================================
# RUN BRIDGELAB V6
# =============================================

if __name__ == "__main__":
    initialize_database()

    print("=" * 48)
    print("BRIDGELAB V6 — PARTICIPANT WORKSPACE")
    print("=" * 48)
    print("Admin: http://127.0.0.1:5001")
    print("Participant: http://127.0.0.1:5001/participant/login")
    print("Catalog: http://127.0.0.1:5001/challenges")
    print("LOCAL DEMONSTRATION ONLY")
    print("=" * 48)

    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False
    )
