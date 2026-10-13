
"""
BridgeLab V10
Participant Progress Tracker

Preserves the existing BridgeLab application.

Features:
- Project file management
- Live challenge progress
- Resource access tracking
- Submission tracking
- Evaluation tracking

Local demonstration only.
"""

import app_core

from flask import session
from progress_tracker import get_progress, initialize_progress


# =============================================
# USE EXISTING BRIDGELAB APPLICATION
# =============================================

app = app_core.app


# =============================================
# INITIALIZE PROGRESS TRACKING
# =============================================

initialize_progress()


# =============================================
# V9 — ORIGINAL PARTICIPANT FILE LIST
# =============================================

old_file_list = '''            {% for f in e.files %}
            <p>
                <a href="/participant/file/{{ f.id }}">
                    {{ f.original_name }}
                </a>
                ({{ (f.size_bytes / 1024)|round(1) }} KB)
            </p>
            {% endfor %}'''


# =============================================
# V9 — UPDATED FILE MANAGEMENT
# =============================================

new_file_list = '''            {% for f in e.files %}

            <div style="
                border-bottom:1px solid #c4c5c3;
                padding:12px 0;
            ">

                <a href="/participant/file/{{ f.id }}">
                    {{ f.original_name }}
                </a>

                <span style="
                    margin-left:8px;
                    color:#687385;
                ">
                    ({{ (f.size_bytes / 1024)|round(1) }} KB)
                </span>

                {% if e.can_submit
                      and e.review_status not in
                      ['Under Review', 'Reviewed']
                      and e.files|length > 1 %}

                <form method="post"
                      action="{{ url_for(
                          'file_manager.remove_file',
                          file_id=f.id
                      ) }}"
                      onsubmit="return confirm(
                          'Remove this file from your submission?'
                      )">

                    <input type="hidden"
                           name="_csrf"
                           value="{{ csrf }}">

                    <button class="btn"
                            type="submit">
                        REMOVE FILE
                    </button>

                </form>

                {% endif %}

            </div>

            {% endfor %}'''


# =============================================
# APPLY V9 FILE MANAGEMENT
# =============================================

if app_core.PARTICIPANT_BODY.count(old_file_list) != 1:
    raise RuntimeError(
        "Original participant file list not found. "
        "Check platform/app_core.py."
    )

app_core.PARTICIPANT_BODY = (
    app_core.PARTICIPANT_BODY.replace(
        old_file_list,
        new_file_list,
        1
    )
)


# =============================================
# V10 — PROJECT PROGRESS CALCULATIONS
# =============================================

def participant_progress(challenge_id):
    """
    Return progress only for the authenticated
    participant's own challenge enrollment.
    """

    if session.get("role") != "participant":
        return None

    participant_id = session.get("user_id")

    if not isinstance(participant_id, int):
        return None

    return get_progress(
        participant_id,
        challenge_id
    )


@app.context_processor
def inject_progress_tracker():
    """
    Make progress_for() available inside
    BridgeLab Jinja templates.
    """

    return {
        "progress_for": participant_progress
    }


# =============================================
# V10 — PROGRESS TRACKER DESIGN
# =============================================

progress_template = '''

        {% set progress = progress_for(e.id) %}

        {% if progress %}

        <div style="
            background:#fffdf8;
            border:1px solid #192640;
            padding:20px;
            margin:20px 0;
            box-shadow:3px 3px 0 #c1c4c9;
        ">

            <div style="
                display:flex;
                align-items:center;
                justify-content:space-between;
                gap:15px;
                flex-wrap:wrap;
            ">

                <div>
                    <div style="
                        font:bold 10px Courier New,monospace;
                        color:#687385;
                    ">
                        BRIDGELAB / PROJECT STATUS
                    </div>

                    <h4 style="
                        font: bold 22px Georgia,serif;
                        margin:9px 0;
                    ">
                        Your Project Progress
                    </h4>
                </div>

                <div style="
                    font:bold 32px Georgia,serif;
                    color:#3454c8;
                ">
                    {{ progress.percent }}%
                </div>

            </div>

            <p style="
                color:#687385;
                font-size:13px;
                margin:10px 0;
            ">
                {{ progress.completed }}
                of
                {{ progress.total }}
                milestones completed
            </p>

            <div style="
                width:100%;
                height:13px;
                background:#e4e4df;
                border:1px solid #192640;
                margin:15px 0 22px;
            ">

                <div style="
                    width:{{ progress.percent }}%;
                    height:100%;
                    background:#3454c8;
                "></div>

            </div>

            <div>

                {% for stage in progress.stages %}

                <div style="
                    display:flex;
                    align-items:flex-start;
                    gap:12px;
                    padding:12px 0;
                    border-bottom:1px dashed #c4c5c3;
                ">

                    {% if stage.complete %}

                    <div style="
                        background:#c9edda;
                        border:1px solid #192640;
                        min-width:26px;
                        height:26px;
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        font-weight:bold;
                    ">
                        ✓
                    </div>

                    {% else %}

                    <div style="
                        background:#f4f0e7;
                        border:1px solid #192640;
                        min-width:26px;
                        height:26px;
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        font-weight:bold;
                    ">
                        ○
                    </div>

                    {% endif %}

                    <div style="flex:1;">

                        <div style="
                            font-weight:bold;
                            margin-bottom:5px;
                        ">
                            {{ stage.label }}
                        </div>

                        <div style="
                            font:11px Courier New,monospace;
                            color:#687385;
                        ">

                            {% if stage.complete %}
                                COMPLETED
                            {% else %}
                                NOT YET COMPLETED
                            {% endif %}

                        </div>

                    </div>

                </div>

                {% endfor %}

            </div>

            {% if progress.percent == 100 %}

            <div style="
                background:#c9edda;
                border:1px solid #93a89e;
                padding:13px;
                margin-top:19px;
                font-weight:bold;
            ">
                All project milestones completed.
            </div>

            {% else %}

            <div style="
                background:#fff0c4;
                border:1px solid #d3b765;
                padding:13px;
                margin-top:19px;
                font-size:13px;
            ">
                Continue working through your remaining
                project milestones.
            </div>

            {% endif %}

        </div>

        {% endif %}

'''


# =============================================
# INSERT TRACKER INTO MY PROJECTS
# =============================================

challenge_title = '        <h3>{{ e.title }}</h3>'

if app_core.PARTICIPANT_BODY.count(challenge_title) != 1:
    raise RuntimeError(
        "Participant challenge title not found. "
        "Check platform/app_core.py."
    )

app_core.PARTICIPANT_BODY = (
    app_core.PARTICIPANT_BODY.replace(
        challenge_title,
        challenge_title + progress_template,
        1
    )
)


# =============================================
# START BRIDGELAB V10
# =============================================

if __name__ == "__main__":

    print("=" * 48)

    print(
        "BRIDGELAB V10 — PROJECT PROGRESS TRACKER"
    )

    print(
        "Admin: http://127.0.0.1:5001"
    )

    print(
        "Participant: "
        "http://127.0.0.1:5001/participant/login"
    )

    print(
        "Resources: "
        "http://127.0.0.1:5001/resources/2"
    )

    print("LOCAL DEMONSTRATION ONLY")

    print("=" * 48)

    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False
    )
