
from pathlib import Path
from urllib.parse import urlparse
import sqlite3
import secrets
import hmac
import sys

from flask import (
    Flask, request, redirect,
    render_template_string, session,
    abort, url_for
)

# ==========================================
# BRIDGELAB V3 - CHALLENGE CONTROL
# LOCAL DEVELOPMENT PROTOTYPE
# ==========================================

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "instance" / "bridgelab.db"

sys.path.insert(0, str(ROOT))

from evaluation.scoring_engine import (
    Evaluation, CRITERIA, rank_submissions
)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

LABELS = {
    "technical_accuracy": "Technical Accuracy",
    "problem_solving": "Problem Solving",
    "presentation": "Presentation",
    "originality": "Originality",
    "documentation": "Documentation"
}


# ==========================================
# DATABASE
# ==========================================

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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

        db.commit()


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)

    return session["_csrf"]


def verify_csrf():
    submitted = request.form.get("_csrf", "")

    if not hmac.compare_digest(submitted, csrf_token()):
        abort(400, "Invalid form token. Refresh the page.")


def flash_redirect(text, error=False):
    return redirect(url_for(
        "dashboard",
        **{"error" if error else "notice": text}
    ))


# ==========================================
# HTML / CSS / JAVASCRIPT
# ==========================================

PAGE = r"""
<!DOCTYPE html>
<html lang="en">

<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>BridgeLab® — Challenge Control V3</title>

<style>

:root {
    --ink: #18243d;
    --blue: #364fc7;
    --blue-light: #e4eaff;
    --cream: #f3efe5;
    --paper: #fffdf8;
    --yellow: #f5d46c;
    --mint: #c7ecd6;
    --muted: #707780;
    --line: #c8c6bf;
    --danger: #aa3737;
}

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    background: var(--cream);
    color: var(--ink);
    font: 13px Arial, sans-serif;
}

a {
    color: inherit;
}

button, input, select {
    font: inherit;
}

button {
    cursor: pointer;
}

button:disabled {
    opacity: .5;
    cursor: not-allowed;
}

.top {
    background: var(--ink);
    color: #d8e0eb;
    display: flex;
    justify-content: space-between;
    gap: 15px;
    padding: 11px 4%;
    font: 11px "Courier New", monospace;
    letter-spacing: .4px;
}

.online {
    color: #a5efbf;
}

.shell {
    max-width: 1480px;
    margin: auto;
    padding: 30px 28px 60px;
}

.masthead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 3px solid var(--ink);
    padding-bottom: 24px;
    gap: 20px;
}

.logo {
    font: bold clamp(36px, 5vw, 60px) Georgia, serif;
    letter-spacing: -4px;
}

.logo span {
    color: var(--blue);
}

.motto {
    margin-top: 8px;
    color: var(--muted);
    font: bold 11px "Courier New", monospace;
    letter-spacing: 1px;
}

.stamp {
    padding: 12px 16px;
    background: var(--yellow);
    border: 1px solid var(--ink);
    box-shadow: 4px 4px 0 var(--ink);
    font: bold 11px "Courier New", monospace;
}

.workspace {
    display: grid;
    grid-template-columns: 232px minmax(0, 1fr);
    gap: 26px;
    margin-top: 27px;
}

.sidebar {
    align-self: start;
    position: sticky;
    top: 20px;
}

.side-panel {
    border: 1px solid var(--ink);
    background: var(--paper);
    box-shadow: 4px 4px 0 var(--ink);
    padding: 18px;
}

.side-title {
    font: bold 11px "Courier New", monospace;
    color: var(--muted);
    margin-bottom: 17px;
}

.nav {
    display: block;
    padding: 14px 10px;
    border-top: 1px dashed var(--line);
    text-decoration: none;
    font-weight: bold;
}

.nav:hover {
    background: var(--blue-light);
    color: var(--blue);
}

.nav span {
    display: inline-block;
    width: 28px;
    color: var(--muted);
    font-family: "Courier New", monospace;
}

.side-note {
    margin-top: 22px;
    border: 1px solid var(--ink);
    background: var(--mint);
    padding: 18px;
}

.side-note strong {
    font: bold 12px "Courier New", monospace;
}

.side-note p {
    line-height: 1.6;
}

main {
    min-width: 0;
}

.hero {
    background: var(--ink);
    color: white;
    padding: 35px;
    border: 1px solid var(--ink);
    position: relative;
    overflow: hidden;
}

.hero::after {
    content: "BL.";
    position: absolute;
    right: 25px;
    bottom: -38px;
    font: bold 170px Georgia, serif;
    opacity: .06;
    pointer-events: none;
}

.eyebrow {
    font: bold 11px "Courier New", monospace;
    color: var(--yellow);
    letter-spacing: 2px;
}

.hero h1 {
    font: bold clamp(29px, 4vw, 46px) Georgia, serif;
    margin: 17px 0;
    letter-spacing: -1px;
    position: relative;
    z-index: 1;
}

.hero p {
    color: #ccd6e4;
    max-width: 580px;
    line-height: 1.8;
    position: relative;
    z-index: 1;
}

.hero-tag {
    display: inline-block;
    margin-top: 15px;
    border: 1px solid #7e90aa;
    padding: 8px 12px;
    font: 11px "Courier New", monospace;
}

.warning {
    margin-top: 15px;
    background: #fff0c5;
    border: 1px solid #cbaa59;
    padding: 13px 16px;
    line-height: 1.6;
}

.alert {
    margin-top: 14px;
    padding: 12px 16px;
    background: var(--mint);
    border: 1px solid #7d9f8a;
}

.alert.error {
    background: #fce4df;
    border-color: #bb7a73;
}

.heading {
    margin: 30px 0 15px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
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
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
}

.stat {
    padding: 22px;
    background: var(--paper);
    border: 1px solid var(--ink);
    box-shadow: 3px 3px 0 #bac0cc;
}

.stat:nth-child(2) {
    background: var(--blue-light);
}

.stat:nth-child(4) {
    background: var(--mint);
}

.stat-label {
    color: var(--muted);
    font: bold 10px "Courier New", monospace;
    letter-spacing: .5px;
}

.stat-value {
    margin-top: 13px;
    font: bold 42px Georgia, serif;
}

.columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
}

.panel {
    background: var(--paper);
    border: 1px solid var(--ink);
    box-shadow: 3px 3px 0 #bac0cc;
    min-width: 0;
}

.panel-head {
    padding: 13px 17px;
    background: #e8e8e3;
    border-bottom: 1px solid var(--ink);
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font: bold 11px "Courier New", monospace;
}

.panel-content {
    padding: 22px;
}

.panel-content p {
    color: var(--muted);
    line-height: 1.7;
    margin-top: 0;
}

label {
    display: block;
    margin: 16px 0 7px;
    font: bold 11px "Courier New", monospace;
}

input, select {
    display: block;
    width: 100%;
    min-width: 0;
    padding: 12px;
    background: #fff;
    border: 1px solid #a0a5ac;
    color: var(--ink);
    border-radius: 0;
}

input:focus, select:focus {
    outline: 2px solid var(--blue);
    outline-offset: 1px;
}

.btn {
    display: inline-block;
    margin-top: 19px;
    background: var(--blue);
    color: #fff;
    border: 1px solid var(--ink);
    padding: 13px 18px;
    box-shadow: 3px 3px 0 var(--ink);
    font: bold 11px "Courier New", monospace;
}

.btn:hover:not(:disabled) {
    transform: translate(1px, 1px);
    box-shadow: 2px 2px 0 var(--ink);
}

.btn-yellow {
    background: var(--yellow);
    color: var(--ink);
}

.table-scroll {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    min-width: 630px;
}

th {
    background: #e8e8e3;
    padding: 15px;
    text-align: left;
    border-bottom: 1px solid var(--ink);
    font: bold 11px "Courier New", monospace;
}

td {
    padding: 15px;
    border-bottom: 1px solid #e1dfd8;
}

tbody tr:hover {
    background: #eef1ff;
}

.mono {
    font: bold 12px "Courier New", monospace;
}

.pill {
    display: inline-block;
    padding: 6px 9px;
    background: var(--mint);
    border: 1px solid #82aa91;
    font: bold 10px "Courier New", monospace;
}

.pill.pending {
    background: #fff0c5;
    border-color: #bda46b;
}

.score-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0,1fr));
    gap: 12px;
    margin-top: 20px;
}

.score-grid label {
    min-height: 44px;
    line-height: 1.5;
}

.score-grid small {
    color: var(--muted);
}

.total-preview {
    margin-top: 23px;
    padding: 16px;
    background: var(--blue-light);
    border: 1px solid var(--ink);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.total-preview strong {
    font: bold 26px Georgia, serif;
}

.rank-one {
    background: #fff5d9;
}

.empty {
    padding: 28px;
    color: var(--muted);
    text-align: center;
    font: 12px "Courier New", monospace;
}

footer {
    display: flex;
    justify-content: space-between;
    border-top: 1px solid var(--ink);
    margin-top: 42px;
    padding-top: 19px;
    gap: 15px;
    color: var(--muted);
    font: 11px "Courier New", monospace;
}

@media(max-width: 1050px) {
    .workspace {
        grid-template-columns: 1fr;
    }

    .sidebar {
        position: static;
    }

    .side-note {
        display: none;
    }

    .side-panel {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
    }

    .side-title {
        width: 100%;
    }

    .nav {
        border: 1px solid var(--line);
    }
}

@media(max-width: 720px) {
    .shell {
        padding: 20px 12px;
    }

    .columns {
        grid-template-columns: 1fr;
    }

    .stats {
        grid-template-columns: repeat(2, 1fr);
    }

    .score-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .stamp {
        display: none;
    }

    .hero {
        padding: 25px;
    }

    .top, footer {
        flex-wrap: wrap;
    }

    .stat-value {
        font-size: 34px;
    }
}

</style>
</head>

<body>

<div class="top">
    <span>BRIDGELAB NETWORK // CHALLENGE CONTROL</span>
    <span class="online">● LOCAL SYSTEM ONLINE</span>
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
            SYSTEM V3.0<br>
            CHALLENGE 001
        </div>
    </div>

    <div class="workspace">

        <aside class="sidebar">

            <nav class="side-panel">
                <div class="side-title">
                    / WORKSPACE DIRECTORY
                </div>

                <a class="nav" href="#overview">
                    <span>01</span> Overview
                </a>

                <a class="nav" href="#registration">
                    <span>02</span> Registration
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
            </nav>

            <div class="side-note">
                <strong>PROJECT FILE / 001</strong>

                <p>
                    Retail Analytics Challenge
                </p>

                <small>
                    Independent technical learning initiative.
                    Pilot in development.
                </small>
            </div>

        </aside>

        <main>

            <section id="overview">

                <div class="hero">

                    <div class="eyebrow">
                        // WELCOME TO THE LAB
                    </div>

                    <h1>
                        Learn by building.<br>
                        Prove it with results.
                    </h1>

                    <p>
                        A project-based technical workspace
                        for managing challenges, submissions,
                        evaluations, and practical skill development.
                    </p>

                    <div class="hero-tag">
                        COHORT 001 / DEVELOPMENT MODE
                    </div>

                </div>

                <div class="warning">
                    <strong>LOCAL DEMO:</strong>
                    Use fictional participant details only.
                    This platform does not have authentication
                    and is not ready for public deployment.
                </div>

                {% if notice %}
                    <div class="alert">{{ notice }}</div>
                {% endif %}

                {% if error %}
                    <div class="alert error">{{ error }}</div>
                {% endif %}

                <div class="heading">
                    <h2>Control overview</h2>
                    <small>01 / LIVE METRICS</small>
                </div>

                <div class="stats">

                    <div class="stat">
                        <div class="stat-label">
                            REGISTERED
                        </div>
                        <div class="stat-value">{{ total }}</div>
                    </div>

                    <div class="stat">
                        <div class="stat-label">
                            SUBMISSIONS
                        </div>
                        <div class="stat-value">{{ submitted }}</div>
                    </div>

                    <div class="stat">
                        <div class="stat-label">
                            PENDING
                        </div>
                        <div class="stat-value">{{ pending }}</div>
                    </div>

                    <div class="stat">
                        <div class="stat-label">
                            EVALUATED
                        </div>
                        <div class="stat-value">{{ evaluated }}</div>
                    </div>

                </div>

            </section>

            <section id="registration">

                <div class="heading">
                    <h2>Participant management</h2>
                    <small>02 / INTAKE SYSTEM</small>
                </div>

                <div class="columns">

                    <div class="panel">
                        <div class="panel-head">
                            <span>+ NEW REGISTRATION</span>
                            <span>FORM 01</span>
                        </div>

                        <div class="panel-content">

                            <p>
                                Register a fictional participant
                                to test BridgeLab's workflow.
                            </p>

                            <form method="post" action="/register">

                                <input type="hidden"
                                       name="_csrf"
                                       value="{{ csrf }}">

                                <label>PARTICIPANT HANDLE</label>

                                <input name="username"
                                       placeholder="Analyst003"
                                       maxlength="40"
                                       required>

                                <label>SKILL TRACK</label>

                                <select name="skill" required>
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

                        <div class="panel-content">

                            <p>
                                Attach a test GitHub repository
                                to an existing participant.
                            </p>

                            <form method="post" action="/submit">

                                <input type="hidden"
                                       name="_csrf"
                                       value="{{ csrf }}">

                                <label>SELECT PARTICIPANT</label>

                                <select name="participant_id" required>

                                    <option value="">
                                        Choose participant
                                    </option>

                                    {% for p in participants %}
                                        <option value="{{ p.id }}">
                                            BL-{{ "%03d"|format(p.id) }}
                                            / {{ p.username }}
                                        </option>
                                    {% endfor %}

                                </select>

                                <label>GITHUB REPOSITORY</label>

                                <input type="url"
                                       name="project_url"
                                       maxlength="500"
                                       placeholder="https://github.com/owner/repo"
                                       required>

                                <button class="btn" type="submit"
                                    {% if total == 0 %}disabled{% endif %}>
                                    ↗ RECORD SUBMISSION
                                </button>

                            </form>

                        </div>
                    </div>

                </div>

            </section>

            <section id="submissions">

                <div class="heading">
                    <h2>Submission register</h2>
                    <small>03 / PARTICIPANT DATABASE</small>
                </div>

                <div class="panel">
                    <div class="panel-head">
                        <span>PROJECT TRACKER</span>
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

                                    <td>
                                        <strong>{{ p.username }}</strong>
                                    </td>

                                    <td>{{ p.skill }}</td>

                                    <td>
                                        {% if p.project_url %}
                                            <span class="pill">
                                                SUBMITTED
                                            </span>
                                        {% else %}
                                            <span class="pill pending">
                                                PENDING
                                            </span>
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
                                                View project ↗
                                            </a>
                                        {% else %}
                                            —
                                        {% endif %}
                                    </td>

                                </tr>

                            {% else %}

                                <tr>
                                    <td colspan="6" class="empty">
                                        NO RECORDS FOUND
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
                    <small>04 / SCORING ENGINE</small>
                </div>

                <div class="panel">

                    <div class="panel-head">
                        <span>TECHNICAL ASSESSMENT</span>
                        <span>MAX 100 PTS</span>
                    </div>

                    <div class="panel-content">

                        <p>
                            Evaluate submitted projects using
                            the structured BridgeLab rubric.
                            All rankings are provisional.
                        </p>

                        <form method="post" action="/score">

                            <input type="hidden"
                                   name="_csrf"
                                   value="{{ csrf }}">

                            <label>SELECT SUBMITTED PROJECT</label>

                            <select name="participant_id" required>

                                <option value="">
                                    Choose submitted project
                                </option>

                                {% for p in participants %}
                                    {% if p.project_url %}
                                        <option value="{{ p.id }}">
                                            BL-{{ "%03d"|format(p.id) }}
                                            / {{ p.username }}
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

                                    <input type="number"
                                           class="score-input"
                                           name="{{ key }}"
                                           min="0"
                                           max="{{ maximum }}"
                                           step="1"
                                           value="0"
                                           required>
                                </div>

                            {% endfor %}

                            </div>

                            <div class="total-preview">
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
                    <small>05 / PROVISIONAL RESULTS</small>
                </div>

                <div class="panel">

                    <div class="panel-head">
                        <span>PROJECT RANKINGS</span>
                        <span>REVIEW REQUIRED</span>
                    </div>

                    <div class="table-scroll">
                        <table>

                            <thead>
                                <tr>
                                    <th>POSITION</th>
                                    <th>PARTICIPANT</th>
                                    <th>TRACK</th>
                                    <th>TOTAL SCORE</th>
                                    <th>STATUS</th>
                                </tr>
                            </thead>

                            <tbody>

                            {% for entry in leaderboard %}

                                <tr {% if loop.first %}class="rank-one"{% endif %}>

                                    <td class="mono">
                                        #{{ loop.index }}
                                    </td>

                                    <td>
                                        <strong>{{ entry.username }}</strong>
                                    </td>

                                    <td>{{ entry.skill }}</td>

                                    <td class="mono">
                                        {{ entry.total_score }}/100
                                    </td>

                                    <td>
                                        <span class="pill">
                                            PROVISIONAL
                                        </span>
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
                <span>
                    BRIDGELAB / INDEPENDENT TECHNICAL INITIATIVE
                </span>

                <span>
                    SYSTEM V3.0 / LOCAL DEVELOPMENT
                </span>
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

        document.getElementById("score-total").textContent =
            total + " / 100";
    });
});
</script>

</body>
</html>
"""


# ==========================================
# DASHBOARD ROUTE
# ==========================================

@app.route("/")
def dashboard():

    with get_db() as db:

        participants = db.execute("""
            SELECT
                p.id,
                p.username,
                p.skill,
                s.project_url,
                e.total_score

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
                p.username,
                p.skill,
                e.technical_accuracy,
                e.problem_solving,
                e.presentation,
                e.originality,
                e.documentation

            FROM evaluations e

            JOIN participants p
                ON p.id = e.participant_id

            JOIN submissions s
                ON p.id = s.participant_id
        """).fetchall()

    evaluations = []

    for row in reviewed:
        scores = {
            key: row[key]
            for key in CRITERIA
        }

        evaluations.append(
            Evaluation(
                participant_id=row["participant_id"],
                **scores
            )
        )

    rankings = rank_submissions(evaluations)

    people = {
        person["id"]: person
        for person in participants
    }

    leaderboard = []

    for entry in rankings:

        person = people[entry["participant_id"]]

        leaderboard.append({
            **entry,
            "username": person["username"],
            "skill": person["skill"]
        })

    submitted = sum(
        1 for p in participants
        if p["project_url"]
    )

    evaluated = sum(
        1 for p in participants
        if p["total_score"] is not None
    )

    return render_template_string(
        PAGE,
        participants=participants,
        total=len(participants),
        submitted=submitted,
        pending=len(participants) - submitted,
        evaluated=evaluated,
        leaderboard=leaderboard,
        criteria=CRITERIA,
        labels=LABELS,
        csrf=csrf_token(),
        notice=request.args.get("notice", ""),
        error=request.args.get("error", "")
    )


# ==========================================
# REGISTER PARTICIPANT
# ==========================================

@app.route("/register", methods=["POST"])
def register():

    verify_csrf()

    username = request.form.get(
        "username", ""
    ).strip()

    skill = request.form.get("skill", "")

    allowed_skills = {
        "Data Analytics",
        "Software Development",
        "Business Analysis"
    }

    if not (
        1 <= len(username) <= 40
        and all(
            char.isalnum() or char in "_-"
            for char in username
        )
    ):
        return flash_redirect(
            "Invalid participant username.", True
        )

    if skill not in allowed_skills:
        return flash_redirect(
            "Invalid skill selection.", True
        )

    try:
        with get_db() as db:
            db.execute("""
                INSERT INTO participants
                (username, skill)
                VALUES (?, ?)
            """, (username, skill))

            db.commit()

    except sqlite3.IntegrityError:
        return flash_redirect(
            "Username already exists.", True
        )

    return flash_redirect(
        "Participant registered successfully."
    )


# ==========================================
# SUBMIT PROJECT
# ==========================================

@app.route("/submit", methods=["POST"])
def submit():

    verify_csrf()

    try:
        participant_id = int(
            request.form.get("participant_id", "")
        )
    except ValueError:
        return flash_redirect(
            "Invalid participant.", True
        )

    project_url = request.form.get(
        "project_url", ""
    ).strip()

    parsed = urlparse(project_url)
    path_parts = parsed.path.strip("/").split("/")

    valid_url = (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and not parsed.username
        and not parsed.password
        and len(path_parts) >= 2
        and all(path_parts[:2])
        and len(project_url) <= 500
    )

    if not valid_url:
        return flash_redirect(
            "Enter a valid GitHub repository URL.",
            True
        )

    with get_db() as db:

        participant = db.execute("""
            SELECT id
            FROM participants
            WHERE id = ?
        """, (participant_id,)).fetchone()

        if participant is None:
            return flash_redirect(
                "Participant not found.", True
            )

        previous = db.execute("""
            SELECT project_url
            FROM submissions
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
            previous is not None
            and previous["project_url"] != project_url
        ):
            db.execute("""
                DELETE FROM evaluations
                WHERE participant_id = ?
            """, (participant_id,))

        db.commit()

    return flash_redirect(
        "Project submission recorded successfully."
    )


# ==========================================
# EVALUATE PROJECT
# ==========================================

@app.route("/score", methods=["POST"])
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
        return flash_redirect(
            "Invalid score. Check rubric limits.",
            True
        )

    with get_db() as db:

        submission = db.execute("""
            SELECT id
            FROM submissions
            WHERE participant_id = ?
        """, (participant_id,)).fetchone()

        if submission is None:
            return flash_redirect(
                "Only submitted projects can be scored.",
                True
            )

        db.execute("""
            INSERT INTO evaluations (
                participant_id,
                technical_accuracy,
                problem_solving,
                presentation,
                originality,
                documentation,
                total_score
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(participant_id)
            DO UPDATE SET
                technical_accuracy =
                    excluded.technical_accuracy,
                problem_solving =
                    excluded.problem_solving,
                presentation =
                    excluded.presentation,
                originality =
                    excluded.originality,
                documentation =
                    excluded.documentation,
                total_score =
                    excluded.total_score,
                evaluated_at =
                    CURRENT_TIMESTAMP
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

    return flash_redirect(
        f"Evaluation saved successfully: {total}/100."
    )


# ==========================================
# START BRIDGELAB V3
# ==========================================

if __name__ == "__main__":

    initialize_database()

    print()
    print("=" * 50)
    print("BRIDGELAB CHALLENGE CONTROL V3")
    print("=" * 50)
    print("Website: http://127.0.0.1:5001")
    print("Status: LOCAL DEVELOPMENT")
    print("Database: SQLite")
    print("Authentication: NOT ENABLED")
    print("=" * 50)
    print()

    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False
    )
