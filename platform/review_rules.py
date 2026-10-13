
"""
BridgeLab V11 — Secure Review Validation
Local demonstration only.
"""

from flask import request, session, redirect, url_for, current_app
from functools import wraps

MIN_FEEDBACK_LENGTH = 30

RUBRIC_LIMITS = {
    "accuracy": 30,
    "solution": 30,
    "feasibility": 20,
    "communication": 10,
    "originality": 10,
}

VALID_STATUSES = {
    "Submitted",
    "Under Review",
    "Reviewed",
}


def validate_review_form(form):
    status = form.get("review_status", "")

    if status not in VALID_STATUSES:
        return "Choose a valid review status."

    feedback = form.get("feedback", "").strip()

    if len(feedback) > 3000:
        return "Feedback cannot exceed 3000 characters."

    for category, maximum in RUBRIC_LIMITS.items():
        try:
            score = int(form.get(category, ""))
        except (ValueError, TypeError):
            return f"Enter a valid score for {category}."

        if not 0 <= score <= maximum:
            return (
                f"The {category} score must be "
                f"between 0 and {maximum}."
            )

    if status == "Reviewed" and len(feedback) < MIN_FEEDBACK_LENGTH:
        return (
            "A completed review requires at least "
            "30 characters of written feedback."
        )

    return None


def install_review_validation(app):
    """
    Add validation to the existing review endpoint.

    Keep the original administrator authentication,
    CSRF protection, and database-saving logic.
    """

    if app.extensions.get("bridgelab_review_validation"):
        return

    from app_core import check_csrf

    @app.before_request
    def validate_admin_review_request():
        if (
            request.endpoint != "save_review"
            or request.method != "POST"
        ):
            return None

        # Unauthenticated users are handled by the
        # application's existing protected endpoint.
        if session.get("role") != "admin":
            return None

        # Verify the existing CSRF token first.
        check_csrf()

        error = validate_review_form(request.form)

        if error is None:
            return None

        submission_id = request.view_args.get(
            "submission_id"
        )

        return redirect(
            url_for(
                "review_submission",
                submission_id=submission_id,
                error=error
            )
        )

    app.extensions["bridgelab_review_validation"] = True


if __name__ == "__main__":
    example = {
        "review_status": "Reviewed",
        "accuracy": "24",
        "solution": "25",
        "feasibility": "17",
        "communication": "9",
        "originality": "8",
        "feedback": (
            "The project presents practical recommendations "
            "supported by clear evidence and analysis."
        ),
    }

    assert validate_review_form(example) is None
    print("PASS: Valid evaluation accepted.")

    example["feedback"] = ""
    assert validate_review_form(example) is not None
    print("PASS: Missing feedback rejected.")

    example["review_status"] = "Under Review"
    assert validate_review_form(example) is None
    print("PASS: In-progress review accepted.")
