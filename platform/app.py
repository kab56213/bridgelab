
"""
BridgeLab V9
Participant File Management

Preserves the existing BridgeLab application while
adding file removal controls to the participant dashboard.
"""

import app_core

app = app_core.app


# =============================================
# PARTICIPANT FILE LIST — ORIGINAL
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
# PARTICIPANT FILE LIST — UPDATED
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
# APPLY PARTICIPANT DASHBOARD UPGRADE
# =============================================

if app_core.PARTICIPANT_BODY.count(old_file_list) != 1:
    raise RuntimeError(
        "Participant file list not found in app_core.py. "
        "Check that app_core.py contains the original "
        "working BridgeLab application."
    )

app_core.PARTICIPANT_BODY = (
    app_core.PARTICIPANT_BODY.replace(
        old_file_list,
        new_file_list,
        1
    )
)


# =============================================
# START BRIDGELAB
# =============================================

if __name__ == "__main__":

    print("=" * 48)

    print(
        "BRIDGELAB V9 — FILE MANAGEMENT"
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
