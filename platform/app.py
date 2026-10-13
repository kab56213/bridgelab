
"""
BridgeLab V12 — Participant Onboarding

Includes:
- V9 file management
- V10 project progress tracking
- V11 review validation and score privacy
- V12 participant onboarding

LOCAL DEMONSTRATION ONLY.
"""

from functools import wraps

from flask import session, request, redirect, url_for

import app_core
from progress_tracker import get_progress, initialize_progress
from review_rules import validate_review_form
from onboarding import install_onboarding


app = app_core.app
initialize_progress()


# =============================================
# V9 — FILE MANAGEMENT
# =============================================

old_file_list = '''            {% for f in e.files %}
            <p>
                <a href="/participant/file/{{ f.id }}">
                    {{ f.original_name }}
                </a>
                ({{ (f.size_bytes / 1024)|round(1) }} KB)
            </p>
            {% endfor %}'''

new_file_list = '''            {% for f in e.files %}
            <div style="
                padding:12px 0;
                border-bottom:1px solid #c4c5c3;
            ">
                <a href="/participant/file/{{ f.id }}">
                    {{ f.original_name }}
                </a>
                <span style="color:#687385">
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
                    <button class="btn" type="submit">
                        REMOVE FILE
                    </button>
                </form>
                {% endif %}
            </div>
            {% endfor %}'''

if app_core.PARTICIPANT_BODY.count(old_file_list) != 1:
    raise RuntimeError(
        "V9 file list marker not found in app_core.py."
    )

app_core.PARTICIPANT_BODY = (
    app_core.PARTICIPANT_BODY.replace(
        old_file_list, new_file_list, 1
    )
)


# =============================================
# V10 — LIVE PROJECT PROGRESS
# =============================================

def participant_progress(challenge_id):
    if session.get("role") != "participant":
        return None

    participant_id = session.get("user_id")

    if not isinstance(participant_id, int):
        return None

    return get_progress(participant_id, challenge_id)


@app.context_processor
def inject_progress_tracker():
    return {"progress_for": participant_progress}


progress_template = '''
        {% set progress = progress_for(e.id) %}
        {% if progress %}
        <section style="
            background:#fffdf8;
            border:1px solid #192640;
            padding:20px;
            margin:20px 0;
            box-shadow:3px 3px 0 #c1c4c9;
        ">
            <div style="
                display:flex;
                justify-content:space-between;
                align-items:center;
                flex-wrap:wrap;
                gap:12px;
            ">
                <div>
                    <div style="
                        font:bold 10px 'Courier New',monospace;
                        color:#687385;
                    ">
                        BRIDGELAB / PROJECT STATUS
                    </div>
                    <h4 style="
                        font:bold 22px Georgia,serif;
                        margin:8px 0;
                    ">
                        Your Project Progress
                    </h4>
                </div>
                <strong style="
                    font:bold 32px Georgia,serif;
                    color:#3454c8;
                ">
                    {{ progress.percent }}%
                </strong>
            </div>

            <p style="color:#687385">
                {{ progress.completed }} of
                {{ progress.total }} milestones completed
            </p>

            <div style="
                height:13px;
                background:#e4e4df;
                border:1px solid #192640;
                margin:15px 0 22px;
            ">
                <div style="
                    background:#3454c8;
                    width:{{ progress.percent }}%;
                    height:100%;
                "></div>
            </div>

            {% for stage in progress.stages %}
            <div style="
                display:flex;
                gap:12px;
                align-items:center;
                padding:12px 0;
                border-bottom:1px dashed #c4c5c3;
            ">
                {% if stage.complete %}
                <span style="
                    background:#c9edda;
                    border:1px solid #192640;
                    padding:6px;
                ">✓</span>
                {% else %}
                <span style="
                    background:#f4f0e7;
                    border:1px solid #192640;
                    padding:6px;
                ">○</span>
                {% endif %}

                <div>
                    <strong>{{ stage.label }}</strong>
                    <div style="
                        font:11px 'Courier New',monospace;
                        color:#687385;
                        margin-top:5px;
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

            {% if progress.percent == 100 %}
            <div style="
                background:#c9edda;
                padding:13px;
                margin-top:19px;
            ">
                All tracked project milestones completed.
            </div>
            {% else %}
            <div style="
                background:#fff0c4;
                padding:13px;
                margin-top:19px;
            ">
                Continue working through your remaining
                project milestones.
            </div>
            {% endif %}

            <p style="
                color:#687385;
                font-size:11px;
                margin-top:14px;
            ">
                Progress tracks platform milestones,
                not project quality or prize eligibility.
            </p>
        </section>
        {% endif %}
'''

challenge_title = '        <h3>{{ e.title }}</h3>'

if app_core.PARTICIPANT_BODY.count(challenge_title) != 1:
    raise RuntimeError(
        "V10 challenge heading marker not found."
    )

app_core.PARTICIPANT_BODY = (
    app_core.PARTICIPANT_BODY.replace(
        challenge_title,
        challenge_title + progress_template,
        1
    )
)


# =============================================
# V11 — REVIEW PRIVACY AND VALIDATION
# =============================================

old_score_condition = "{% if e.score is not none %}"

new_score_condition = (
    "{% if e.review_status == 'Reviewed' "
    "and e.score is not none %}"
)

if app_core.PARTICIPANT_BODY.count(
    old_score_condition
) != 1:
    raise RuntimeError(
        "V11 score condition marker not found."
    )

app_core.PARTICIPANT_BODY = (
    app_core.PARTICIPANT_BODY.replace(
        old_score_condition,
        new_score_condition,
        1
    )
)


old_feedback_label = "<label>FEEDBACK</label>"

new_feedback_label = '''
<label>FEEDBACK</label>
<p style="
    background:#fff0c4;
    border:1px solid #d3b765;
    padding:12px;
    line-height:1.6;
">
    A completed review requires at least
    30 characters of written feedback.
    Unfinished scores remain private.
</p>
'''

if app_core.REVIEW_BODY.count(old_feedback_label) != 1:
    raise RuntimeError(
        "V11 feedback label marker not found."
    )

app_core.REVIEW_BODY = (
    app_core.REVIEW_BODY.replace(
        old_feedback_label,
        new_feedback_label,
        1
    )
)


original_save_review = app.view_functions.get("save_review")

if original_save_review is None:
    raise RuntimeError(
        "Review-saving endpoint not found."
    )


@wraps(original_save_review)
def validated_save_review(*args, **kwargs):
    if session.get("role") != "admin":
        return original_save_review(*args, **kwargs)

    admin_id = session.get("user_id")

    if not isinstance(admin_id, int):
        return original_save_review(*args, **kwargs)

    with app_core.get_db() as db:
        admin = db.execute(
            "SELECT id FROM admins WHERE id=?",
            (admin_id,)
        ).fetchone()

    if admin is None:
        return original_save_review(*args, **kwargs)

    app_core.check_csrf()

    error = validate_review_form(request.form)

    if error:
        submission_id = kwargs.get("submission_id")

        if submission_id is None and args:
            submission_id = args[0]

        return redirect(
            url_for(
                "review_submission",
                submission_id=submission_id,
                error=error
            )
        )

    return original_save_review(*args, **kwargs)


app.view_functions["save_review"] = validated_save_review


# =============================================
# V12 — PARTICIPANT ONBOARDING
# =============================================

install_onboarding(app_core)


# =============================================
# START BRIDGELAB V12
# =============================================

if __name__ == "__main__":
    print("=" * 48)
    print("BRIDGELAB V12 — PARTICIPANT ONBOARDING")
    print("Admin: http://127.0.0.1:5001")
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
