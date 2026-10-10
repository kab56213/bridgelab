
from pathlib import Path
from functools import wraps
from urllib.parse import urlparse
from datetime import timedelta
import sqlite3
import secrets
import hmac
import sys
import time

from flask import (
    Flask, request, redirect, render_template_string,
    session, abort, url_for
)

# ================================================
# BRIDGELAB V4 - CHALLENGE CONTROL
# ADMINISTRATOR AUTHENTICATION + PROJECT MANAGEMENT
# LOCAL DEVELOPMENT VERSION
# ================================================

ROOT = Path(__file__).resolve().parent.parent
INSTANCE_DIR = ROOT / "instance"
DB_PATH = INSTANCE_DIR / "bridgelab.db"
SECRET_PATH = INSTANCE_DIR / ".flask_secret"

sys.path.insert(0, str(ROOT))

from auth.security import verify_password
from evaluation.scoring_engine import (
    Evaluation, CRITERIA, rank_submissions
)

INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

# Persistent local session secret
if not SECRET_PATH.exists():
    SECRET_PATH.write_text(
        secrets.token_hex(32), encoding="utf-8"
    )

app = Flask(__name__)
app.secret_key = SECRET_PATH.read_text(
    encoding="utf-8"
).strip()

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    MAX_CONTENT_LENGTH=1024 * 1024
)

LABELS = {
    "technical_accuracy": "Technical Accuracy",
    "problem_solving": "Problem Solving",
    "presentation": "Presentation",
    "originality": "Originality",
    "documentation": "Documentation"
}

# Local prototype login throttle
LOGIN_ATTEMPTS = {}
MAX_ATTEMPTS = 5
LOCK_SECONDS = 300


# ================================================
# DATABASE
# ================================================

def get_db():
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize_database():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                skill TEXT NOT NULL,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id INTEGER NOT NULL UNIQUE,
                project_url TEXT NOT NULL,
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (participant_id)
                    REFERENCES participants(id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id INTEGER NOT NULL UNIQUE,
                technical_accuracy INTEGER NOT NULL,
                problem_solving INTEGER NOT NULL,
                presentation INTEGER NOT NULL,
                originality INTEGER NOT NULL,
                documentation INTEGER NOT NULL,
                total_score INTEGER NOT NULL,
                evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (participant_id)
                    REFERENCES participants(id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()


# ================================================
# SECURITY
# ================================================

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def verify_csrf():
    received = request.form.get("_csrf", "")
    if not hmac.compare_digest(received, csrf_token()):
        abort(400, "Invalid security token.")


def admin_required(function):
    @wraps(function)
    def protected(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))

        with get_db() as db:
            admin = db.execute(
                "SELECT id FROM admins WHERE id = ?",
                (session["admin_id"],)
            ).fetchone()

        if not admin:
            session.clear()
            return redirect(url_for("login"))

        return function(*args, **kwargs)
    return protected


def notify(text, error=False):
    return redirect(url_for(
        "dashboard",
        **{"error" if error else "notice": text}
    ))


# ================================================
# SHARED RETRO DESIGN
# ================================================

STYLES = """
:root {
    --navy: #18243d;
    --blue: #364fc7;
    --cream: #f3efe5;
    --paper: #fffdf8;
    --yellow: #f5d46c;
    --mint: #c7ecd6;
    --line: #c7c6be;
    --muted: #717883;
}

* { box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
    margin: 0;
    background: var(--cream);
    color: var(--navy);
    font-family: Arial, sans-serif;
    font-size: 13px;
}

a { color: inherit; }
button, input, select { font: inherit; }

input, select {
    width: 100%;
    padding: 12px;
    border: 1px solid #9da3ad;
    background: white;
    color: var(--navy);
    border-radius: 0;
}

input:focus, select:focus {
    outline: 2px solid var(--blue);
}

label {
    display: block;
    margin: 15px 0 7px;
    font: bold 11px "Courier New", monospace;
}

button { cursor: pointer; }
button:disabled { opacity: .45; cursor: not-allowed; }

.btn {
    background: var(--blue);
    border: 1px solid var(--navy);
    color: white;
    padding: 13px 19px;
    margin-top: 19px;
    font: bold 11px "Courier New", monospace;
    box-shadow: 3px 3px 0 var(--navy);
}

.btn:hover:not(:disabled) {
    transform: translate(1px, 1px);
    box-shadow: 2px 2px 0 var(--navy);
}

.btn-yellow {
    background: var(--yellow);
    color: var(--navy);
}

.topbar {
    background: var(--navy);
    color: white;
    padding: 12px 4%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    font: 11px "Courier New", monospace;
}

.shell {
    max-width: 1460px;
    padding: 30px 24px;
    margin: auto;
}

.masthead {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    border-bottom: 3px solid var(--navy);
    padding-bottom: 23px;
}

.logo {
    font: bold clamp(35px, 5vw, 59px) Georgia, serif;
    letter-spacing: -3px;
}

.logo span { color: var(--blue); }

.motto {
    font: bold 11px "Courier New", monospace;
    color: var(--muted);
    margin-top: 6px;
    letter-spacing: 1px;
}

.stamp {
    background: var(--yellow);
    padding: 12px 15px;
    border: 1px solid var(--navy);
    box-shadow: 4px 4px 0 var(--navy);
    font: bold 11px "Courier New", monospace;
}

.workspace {
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr);
    gap: 25px;
    margin-top: 25px;
}

.sidebar { align-self: start; }

.sidebox, .panel {
    background: var(--paper);
    border: 1px solid var(--navy);
    box-shadow: 3px 3px 0 #b8bec8;
}

.sidebox { padding: 17px; }

.nav {
    display: block;
    text-decoration: none;
    font-weight: bold;
    padding: 13px 9px;
    border-top: 1px dashed var(--line);
}

.nav:hover {
    background: #e4eaff;
    color: var(--blue);
}

.nav span {
    font-family: "Courier New", monospace;
    color: var(--muted);
    margin-right: 9px;
}

.side-note {
    background: var(--mint);
    border: 1px solid var(--navy);
    margin-top: 20px;
    padding: 16px;
    line-height: 1.7;
}

.mono {
    font: bold 11px "Courier New", monospace;
}

.hero {
    background: var(--navy);
    color: white;
    padding: 37px;
    position: relative;
    overflow: hidden;
}

.hero:after {
    content: "BL.";
    position: absolute;
    right: 25px;
    bottom: -45px;
    font: bold 160px Georgia, serif;
    opacity: .06;
    pointer-events: none;
}

.hero h1 {
    font: bold clamp(28px, 4vw, 44px) Georgia, serif;
    margin: 15px 0;
}

.hero p {
    color: #d3dbea;
    line-height: 1.8;
    max-width: 550px;
}

.eyebrow {
    color: var(--yellow);
    font: bold 11px "Courier New", monospace;
    letter-spacing: 2px;
}

.notice {
    background: #fff0c5;
    border: 1px solid #baa15d;
    padding: 14px;
    margin-top: 15px;
    line-height: 1.6;
}

.success {
    background: var(--mint);
    border: 1px solid #7b9c85;
    padding: 13px;
    margin-top: 14px;
}

.error {
    background: #ffe4df;
    border: 1px solid #bd7a72;
    padding: 13px;
    margin-top: 14px;
}

.heading {
    margin: 29px 0 15px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
}

.heading h2 {
    font: bold 24px Georgia, serif;
    margin: 0;
}

.heading small {
    font: 11px "Courier New", monospace;
    color: var(--muted);
}

.stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0,1fr));
    gap: 13px;
}

.stat {
    background: var(--paper);
    border: 1px solid var(--navy);
    padding: 20px;
    box-shadow: 3px 3px 0 #b8bec8;
}

.stat:nth-child(2) { background: #e4eaff; }
.stat:nth-child(4) { background: var(--mint); }

.stat .label {
    font: bold 10px "Courier New", monospace;
    color: var(--muted);
}

.stat .value {
    font: bold 40px Georgia, serif;
    margin-top: 10px;
}

.columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
}

.panel-head {
    background: #e9e8e2;
    border-bottom: 1px solid var(--navy);
    padding: 14px 17px;
    display: flex;
    justify-content: space-between;
    font: bold 11px "Courier New", monospace;
    gap: 10px;
}

.panel-body { padding: 20px; }

.panel-body p {
    color: var(--muted);
    line-height: 1.7;
}

.table-scroll { overflow-x: auto; }

table {
    width: 100%;
    min-width: 610px;
    border-collapse: collapse;
}

th {
    background: #e9e8e2;
    text-align: left;
    padding: 14px;
    font: bold 11px "Courier New", monospace;
    border-bottom: 1px solid var(--navy);
}

td {
    padding: 14px;
    border-bottom: 1px solid #deddd7;
}

.pill {
    display: inline-block;
    padding: 6px 9px;
    background: var(--mint);
    border: 1px solid #86a68c;
    font: bold 10px "Courier New", monospace;
}

.pending { background: #fff0c5; }

.score-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0,1fr));
    gap: 12px;
}

.score-grid small { color: var(--muted); }

.score-total {
    background: #e4eaff;
    border: 1px solid var(--navy);
    margin-top: 22px;
    padding: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.score-total strong {
    font: bold 27px Georgia, serif;
}

.empty {
    padding: 25px;
    text-align: center;
    color: var(--muted);
}

footer {
    margin-top: 40px;
    border-top: 1px solid var(--navy);
    padding-top: 20px;
    font: 11px "Courier New", monospace;
    color: var(--muted);
}

.logout-form { margin: 0; }
.logout-btn {
    background: transparent;
    color: white;
    border: 1px solid #8895af;
    padding: 8px 12px;
    font: bold 11px "Courier New", monospace;
}

@media(max-width: 950px) {
    .workspace { grid-template-columns: 1fr; }
    .columns { grid-template-columns: 1fr; }
    .score-grid { grid-template-columns: repeat(2, 1fr); }
}

@media(max-width: 650px) {
    .shell { padding: 18px 12px; }
    .stats { grid-template-columns: repeat(2,1fr); }
    .stat .value { font-size: 32px; }
    .stamp { display: none; }
    .hero { padding: 25px; }
    .topbar { flex-wrap: wrap; }
}
"""


# ================================================
# ADMINISTRATOR LOGIN PAGE
# ================================================

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BridgeLab — Administrator Access</title>
<style>
""" + STYLES + """
body {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 20px;
}

.login-box {
    width: 100%;
    max-width: 450px;
    background: var(--paper);
    border: 2px solid var(--navy);
    box-shadow: 8px 8px 0 var(--navy);
    padding: 35px;
}

.login-code {
    background: var(--navy);
    color: var(--yellow);
    display: inline-block;
    padding: 8px 12px;
    font: bold 11px "Courier New", monospace;
    margin-bottom: 20px;
}

.login-title {
    font: bold 35px Georgia, serif;
    margin: 22px 0 8px;
}

.login-subtitle {
    color: var(--muted);
    line-height: 1.7;
}

.login-box .btn { width: 100%; }

.login-footer {
    margin-top: 30px;
    font: 11px "Courier New", monospace;
    color: var(--muted);
}
</style>
</head>
<body>
<div class="login-box">
    <div class="login-code">
        BRIDGELAB SYSTEM / ACCESS GATE
    </div>

    <div class="logo">BridgeLab<span>.</span></div>

    <div class="login-title">
        Welcome back.
    </div>

    <p class="login-subtitle">
        Authorized administrator access to the
        BridgeLab Challenge Control workspace.
    </p>

    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}

    <form method="post">
        <input type="hidden"
               name="_csrf"
               value="{{ csrf }}">

        <label>ADMIN USERNAME</label>
        <input name="username"
               autocomplete="username"
               required>

        <label>PASSWORD</label>
        <input name="password"
               type="password"
               autocomplete="current-password"
               required>

        <button class="btn" type="submit">
            → ACCESS WORKSPACE
        </button>
    </form>

    <div class="login-footer">
        V4.0 / PRIVATE ADMIN PORTAL / LOCAL DEVELOPMENT
    </div>
</div>
</body>
</html>
"""


# ================================================
# ADMINISTRATOR DASHBOARD
# ================================================

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BridgeLab — Challenge Control V4</title>
<style>
""" + STYLES + """
</style>
</head>

<body>

<div class="topbar">
    <span>BRIDGELAB NETWORK // CHALLENGE CONTROL</span>

    <form class="logout-form" action="/logout" method="post">
        <input type="hidden" name="_csrf" value="{{ csrf }}">
        <span style="margin-right:12px">
            ADMIN: {{ admin_username }}
        </span>
        <button class="logout-btn" type="submit">
            LOG OUT ↗
        </button>
    </form>
</div>

<div class="shell">

    <div class="masthead">
        <div>
            <div class="logo">BridgeLab<span>.</span></div>
            <div class="motto">
                BUILD SKILLS / SOLVE PROBLEMS / CREATE IMPACT
            </div>
        </div>
        <div class="stamp">
            SYSTEM V4.0<br>
            ADMIN ACCESS
        </div>
    </div>

    <div class="workspace">

        <aside class="sidebar">
            <div class="sidebox">
                <div class="mono" style="margin-bottom:15px">
                    / WORKSPACE DIRECTORY
                </div>

                <a class="nav" href="#overview">
                    <span>01</span> Overview
                </a>
                <a class="nav" href="#participants">
                    <span>02</span> Participants
                </a>
                <a class="nav" href="#submissions">
                    <span>03</span> Submissions
                </a>
                <a class="nav" href="#evaluation">
                    <span>04</span> Evaluation
                </a>
                <a class="nav" href="#leaderboard">
                    <span>05</span> Leaderboard
                </a>
            </div>

            <div class="side-note">
                <strong>PROJECT FILE / 001</strong>
                <p>Retail Analytics Challenge</p>
                <small>Independent technical initiative.</small>
            </div>
        </aside>

        <main>

            <section id="overview">
                <div class="hero">
                    <div class="eyebrow">
                        // AUTHORIZED CONTROL WORKSPACE
                    </div>

                    <h1>
                        Build something that matters.
                    </h1>

                    <p>
                        Monitor participant progress, manage
                        technical submissions, evaluate projects,
                        and coordinate meaningful challenges.
                    </p>

                    <div class="mono" style="color:#f5d46c">
                        SESSION ACTIVE / ADMINISTRATOR
                    </div>
                </div>

                <div class="notice">
                    <strong>LOCAL DEMO:</strong>
                    Use fictional participant records only.
                    Further security work is required before
                    a public launch.
                </div>

                {% if notice %}
                    <div class="success">{{ notice }}</div>
                {% endif %}

                {% if error %}
                    <div class="error">{{ error }}</div>
                {% endif %}

                <div class="heading">
                    <h2>Control overview</h2>
                    <small>01 / METRICS</small>
                </div>

                <div class="stats">
                    <div class="stat">
                        <div class="label">REGISTERED</div>
                        <div class="value">{{ total }}</div>
                    </div>

                    <div class="stat">
                        <div class="label">SUBMISSIONS</div>
                        <div class="value">{{ submitted }}</div>
                    </div>

                    <div class="stat">
                        <div class="label">PENDING</div>
                        <div class="value">{{ pending }}</div>
                    </div>

                    <div class="stat">
                        <div class="label">EVALUATED</div>
                        <div class="value">{{ evaluated }}</div>
                    </div>
                </div>
            </section>

            <section id="participants">

                <div class="heading">
                    <h2>Participant management</h2>
                    <small>02 / INTAKE</small>
                </div>

                <div class="columns">

                    <div class="panel">
                        <div class="panel-head">
                            <span>+ NEW REGISTRATION</span>
                            <span>FORM 01</span>
                        </div>

                        <div class="panel-body">
                            <p>
                                Create a fictional participant record
                                for testing the platform.
                            </p>

                            <form action="/register" method="post">
                                <input type="hidden"
                                       name="_csrf"
                                       value="{{ csrf }}">

                                <label>PARTICIPANT HANDLE</label>
                                <input name="username"
                                       maxlength="40"
                                       required>

                                <label>SKILL TRACK</label>
                                <select name="skill">
                                    <option>Data Analytics</option>
                                    <option>Software Development</option>
                                    <option>Business Analysis</option>
                                </select>

                                <button class="btn" type="submit">
                                    + ADD PARTICIPANT
                                </button>
                            </form>
                        </div>
                    </div>

                    <div class="panel">
                        <div class="panel-head">
                            <span>↗ PROJECT SUBMISSION</span>
                            <span>FORM 02</span>
                        </div>

                        <div class="panel-body">
                            <p>
                                Record a GitHub project URL
                                for a demonstration participant.
                            </p>

                            <form action="/submit" method="post">
                                <input type="hidden"
                                       name="_csrf"
                                       value="{{ csrf }}">

                                <label>PARTICIPANT</label>
                                <select name="participant_id" required>
                                    <option value="">Choose participant</option>
                                    {% for p in participants %}
                                    <option value="{{ p.id }}">
                                        BL-{{ "%03d"|format(p.id) }}
                                        / {{ p.username }}
                                    </option>
                                    {% endfor %}
                                </select>

                                <label>GITHUB REPOSITORY URL</label>
                                <input type="url" name="project_url"
                                       maxlength="500"
                                       required
                                       placeholder="https://github.com/owner/repo">

                                <button class="btn" type="submit"
                                    {% if not participants %}disabled{% endif %}>
                                    ↗ SAVE SUBMISSION
                                </button>
                            </form>
                        </div>
                    </div>

                </div>
            </section>

            <section id="submissions">

                <div class="heading">
                    <h2>Submission register</h2>
                    <small>03 / RECORDS</small>
                </div>

                <div class="panel">
                    <div class="panel-head">
                        <span>PARTICIPANT DATABASE</span>
                        <span>{{ total }} RECORDS</span>
                    </div>

                    <div class="table-scroll">
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>PARTICIPANT</th>
                                    <th>TRACK</th>
                                    <th>STATUS</th>
                                    <th>SCORE</th>
                                    <th>PROJECT</th>
                                </tr>
                            </thead>

                            <tbody>
                                {% for p in participants %}
                                <tr>
                                    <td class="mono">
                                        BL-{{ "%03d"|format(p.id) }}
                                    </td>
                                    <td>{{ p.username }}</td>
                                    <td>{{ p.skill }}</td>
                                    <td>
                                        {% if p.project_url %}
                                            <span class="pill">SUBMITTED</span>
                                        {% else %}
                                            <span class="pill pending">PENDING</span>
                                        {% endif %}
                                    </td>
                                    <td class="mono">
                                        {% if p.total_score is not none %}
                                            {{ p.total_score }}/100
                                        {% else %}
                                            —
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if p.project_url %}
                                        <a href="{{ p.project_url }}"
                                           target="_blank"
                                           rel="noopener noreferrer">
                                            View ↗
                                        </a>
                                        {% else %}
                                        —
                                        {% endif %}
                                    </td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="6" class="empty">
                                        NO PARTICIPANTS YET
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            <section id="evaluation">

                <div class="heading">
                    <h2>Evaluation desk</h2>
                    <small>04 / SCORING</small>
                </div>

                <div class="panel">
                    <div class="panel-head">
                        <span>TECHNICAL ASSESSMENT</span>
                        <span>100 POINTS MAXIMUM</span>
                    </div>

                    <div class="panel-body">
                        <p>
                            Apply the BridgeLab scoring rubric
                            to a submitted demonstration project.
                        </p>

                        <form action="/score" method="post">
                            <input type="hidden"
                                   name="_csrf"
                                   value="{{ csrf }}">

                            <label>SELECT SUBMITTED PROJECT</label>

                            <select name="participant_id" required>
                                <option value="">Choose participant</option>
                                {% for p in participants %}
                                    {% if p.project_url %}
                                    <option value="{{ p.id }}">
                                        {{ p.username }}
                                    </option>
                                    {% endif %}
                                {% endfor %}
                            </select>

                            <div class="score-grid">
                                {% for key, maximum in criteria.items() %}
                                <div>
                                    <label>
                                        {{ labels[key] }}
                                        <br>
                                        <small>MAX {{ maximum }}</small>
                                    </label>

                                    <input class="score-input"
                                           name="{{ key }}"
                                           type="number"
                                           min="0"
                                           max="{{ maximum }}"
                                           value="0"
                                           step="1"
                                           required>
                                </div>
                                {% endfor %}
                            </div>

                            <div class="score-total">
                                <span class="mono">
                                    LIVE SCORE PREVIEW
                                </span>
                                <strong id="score-total">
                                    0 / 100
                                </strong>
                            </div>

                            <button class="btn btn-yellow"
                                    type="submit"
                                    {% if submitted == 0 %}disabled{% endif %}>
                                ✓ SAVE EVALUATION
                            </button>
                        </form>
                    </div>
                </div>
            </section>

            <section id="leaderboard">

                <div class="heading">
                    <h2>Challenge leaderboard</h2>
                    <small>05 / PROVISIONAL</small>
                </div>

                <div class="panel">
                    <div class="panel-head">
                        <span>PROJECT RANKINGS</span>
                        <span>HUMAN REVIEW REQUIRED</span>
                    </div>

                    <div class="table-scroll">
                        <table>
                            <thead>
                                <tr>
                                    <th>RANK</th>
                                    <th>PARTICIPANT</th>
                                    <th>TRACK</th>
                                    <th>SCORE</th>
                                    <th>STATUS</th>
                                </tr>
                            </thead>

                            <tbody>
                                {% for entry in leaderboard %}
                                <tr>
                                    <td class="mono">#{{ loop.index }}</td>
                                    <td>{{ entry.username }}</td>
                                    <td>{{ entry.skill }}</td>
                                    <td class="mono">
                                        {{ entry.total_score }}/100
                                    </td>
                                    <td>
                                        <span class="pill">PROVISIONAL</span>
                                    </td>
                                </tr>
                                {% else %}
                                <tr>
                                    <td colspan="5" class="empty">
                                        NO EVALUATIONS YET
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            <footer>
                BRIDGELAB / INDEPENDENT TECHNICAL INITIATIVE
                / V4 ADMIN CONTROL
            </footer>

        </main>
    </div>
</div>

<script>
document.querySelectorAll(".score-input").forEach(input => {
    input.addEventListener("input", () => {
        let total = 0;

        document.querySelectorAll(".score-input")
            .forEach(field => {
                total += Number(field.value) || 0;
            });

        document.getElementById("score-total")
            .textContent = total + " / 100";
    });
});
</script>

</body>
</html>
"""


# ================================================
# ADMINISTRATOR LOGIN
# ================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("admin_id"):
        return redirect(url_for("dashboard"))

    error = None

    if request.method == "POST":
        verify_csrf()

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        client_key = request.remote_addr or "local"
        now = time.monotonic()

        attempts = [
            attempt for attempt in
            LOGIN_ATTEMPTS.get(client_key, [])
            if now - attempt < LOCK_SECONDS
        ]

        if len(attempts) >= MAX_ATTEMPTS:
            error = "Too many attempts. Try again later."

        else:
            with get_db() as db:
                admin = db.execute("""
                    SELECT id, username, password_hash
                    FROM admins
                    WHERE username = ?
                """, (username,)).fetchone()

            if admin and verify_password(
                admin["password_hash"], password
            ):
                LOGIN_ATTEMPTS.pop(client_key, None)
                session.clear()
                session["admin_id"] = admin["id"]
                session.permanent = True
                session["_csrf"] = secrets.token_urlsafe(32)

                return redirect(url_for("dashboard"))

            attempts.append(now)
            LOGIN_ATTEMPTS[client_key] = attempts
            error = "Invalid username or password."

    return render_template_string(
        LOGIN_PAGE,
        csrf=csrf_token(),
        error=error
    ), 401 if error else 200


# ================================================
# ADMINISTRATOR LOGOUT
# ================================================

@app.route("/logout", methods=["POST"])
@admin_required
def logout():
    verify_csrf()
    session.clear()
    return redirect(url_for("login"))


# ================================================
# PROTECTED ADMIN DASHBOARD
# ================================================

@app.route("/")
@admin_required
def dashboard():

    with get_db() as db:

        participants = db.execute("""
            SELECT
                p.id, p.username, p.skill,
                s.project_url, e.total_score
            FROM participants p
            LEFT JOIN submissions s
                ON p.id = s.participant_id
            LEFT JOIN evaluations e
                ON p.id = e.participant_id
            ORDER BY p.id DESC
        """).fetchall()

        reviewed = db.execute("""
            SELECT
                p.id AS participant_id,
                p.username, p.skill,
                e.technical_accuracy,
                e.problem_solving,
                e.presentation,
                e.originality,
                e.documentation
            FROM evaluations e
            JOIN participants p
                ON e.participant_id = p.id
            JOIN submissions s
                ON s.participant_id = p.id
        """).fetchall()

        admin = db.execute("""
            SELECT username FROM admins WHERE id = ?
        """, (session["admin_id"],)).fetchone()

    evaluations = [
        Evaluation(
            participant_id=row["participant_id"],
            **{key: row[key] for key in CRITERIA}
        )
        for row in reviewed
    ]

    ranked = rank_submissions(evaluations)
    people = {p["id"]: p for p in participants}

    leaderboard = [
        {
            **entry,
            "username": people[entry["participant_id"]]["username"],
            "skill": people[entry["participant_id"]]["skill"]
        }
        for entry in ranked
    ]

    submitted = sum(
        bool(p["project_url"]) for p in participants
    )

    evaluated = sum(
        p["total_score"] is not None
        for p in participants
    )

    return render_template_string(
        DASHBOARD_PAGE,
        admin_username=admin["username"],
        csrf=csrf_token(),
        participants=participants,
        total=len(participants),
        submitted=submitted,
        pending=len(participants) - submitted,
        evaluated=evaluated,
        leaderboard=leaderboard,
        criteria=CRITERIA,
        labels=LABELS,
        notice=request.args.get("notice", ""),
        error=request.args.get("error", "")
    )


# ================================================
# PROTECTED REGISTRATION
# ================================================

@app.route("/register", methods=["POST"])
@admin_required
def register():
    verify_csrf()

    username = request.form.get(
        "username", ""
    ).strip()

    skill = request.form.get("skill", "")

    allowed = {
        "Data Analytics",
        "Software Development",
        "Business Analysis"
    }

    if not (
        1 <= len(username) <= 40
        and all(
            c.isalnum() or c in "_-"
            for c in username
        )
    ):
        return notify("Invalid participant handle.", True)

    if skill not in allowed:
        return notify("Invalid skill track.", True)

    try:
        with get_db() as db:
            db.execute("""
                INSERT INTO participants (username, skill)
                VALUES (?, ?)
            """, (username, skill))
            db.commit()

    except sqlite3.IntegrityError:
        return notify("Participant already exists.", True)

    return notify("Participant registered successfully.")


# ================================================
# PROTECTED PROJECT SUBMISSIONS
# ================================================

@app.route("/submit", methods=["POST"])
@admin_required
def submit():
    verify_csrf()

    try:
        participant_id = int(
            request.form.get("participant_id", "")
        )
    except ValueError:
        return notify("Invalid participant.", True)

    project_url = request.form.get(
        "project_url", ""
    ).strip()

    parsed = urlparse(project_url)
    parts = parsed.path.strip("/").split("/")

    valid = (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and not parsed.username
        and not parsed.password
        and parsed.port in (None, 443)
        and len(parts) >= 2
        and all(parts[:2])
        and len(project_url) <= 500
    )

    if not valid:
        return notify(
            "Enter a valid GitHub project URL.", True
        )

    with get_db() as db:
        participant = db.execute(
            "SELECT id FROM participants WHERE id = ?",
            (participant_id,)
        ).fetchone()

        if not participant:
            return notify("Participant not found.", True)

        previous = db.execute("""
            SELECT project_url FROM submissions
            WHERE participant_id = ?
        """, (participant_id,)).fetchone()

        db.execute("""
            INSERT INTO submissions
                (participant_id, project_url)
            VALUES (?, ?)
            ON CONFLICT(participant_id)
            DO UPDATE SET
                project_url = excluded.project_url,
                submitted_at = CURRENT_TIMESTAMP
        """, (participant_id, project_url))

        if (
            previous
            and previous["project_url"] != project_url
        ):
            db.execute("""
                DELETE FROM evaluations
                WHERE participant_id = ?
            """, (participant_id,))

        db.commit()

    return notify("Project submission recorded.")


# ================================================
# PROTECTED EVALUATION
# ================================================

@app.route("/score", methods=["POST"])
@admin_required
def score():
    verify_csrf()

    try:
        participant_id = int(
            request.form.get("participant_id", "")
        )

        scores = {
            key: int(request.form.get(key, ""))
            for key in CRITERIA
        }

        evaluation = Evaluation(
            participant_id=participant_id,
            **scores
        )

        total = evaluation.calculate_total()

    except (ValueError, TypeError):
        return notify("Invalid evaluation scores.", True)

    with get_db() as db:

        submission = db.execute("""
            SELECT id FROM submissions
            WHERE participant_id = ?
        """, (participant_id,)).fetchone()

        if not submission:
            return notify(
                "Only submitted projects may be evaluated.",
                True
            )

        db.execute("""
            INSERT INTO evaluations (
                participant_id, technical_accuracy,
                problem_solving, presentation,
                originality, documentation,
                total_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(participant_id)
            DO UPDATE SET
                technical_accuracy=excluded.technical_accuracy,
                problem_solving=excluded.problem_solving,
                presentation=excluded.presentation,
                originality=excluded.originality,
                documentation=excluded.documentation,
                total_score=excluded.total_score,
                evaluated_at=CURRENT_TIMESTAMP
        """, (
            participant_id,
            scores["technical_accuracy"],
            scores["problem_solving"],
            scores["presentation"],
            scores["originality"],
            scores["documentation"],
            total
        ))

        db.commit()

    return notify(f"Evaluation saved: {total}/100.")


# ================================================
# APPLICATION START
# ================================================

if __name__ == "__main__":
    initialize_database()

    print("=" * 48)
    print("BRIDGELAB CHALLENGE CONTROL V4")
    print("=" * 48)
    print("Administrator login enabled")
    print("Website: http://127.0.0.1:5001")
    print("Environment: LOCAL DEVELOPMENT")
    print("=" * 48)

    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False
    )
