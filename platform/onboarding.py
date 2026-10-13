
"""
BridgeLab V12 — Participant Onboarding

Adds an introduction to the participant workspace.
Does not modify the database.
"""

ONBOARDING_HTML = '''
<section style="
    background:#fffdf8;
    border:1px solid #192640;
    box-shadow:3px 3px 0 #c1c4c9;
    padding:24px;
    margin:22px 0;
">

    <div style="
        font:bold 11px Courier New,monospace;
        color:#3454c8;
    ">
        BRIDGELAB / GETTING STARTED
    </div>

    <h2 style="
        font:bold 28px Georgia,serif;
        margin:14px 0;
    ">
        Your Skills. Your Approach.
    </h2>

    <p style="line-height:1.7;">
        BridgeLab gives you practical business
        challenges to solve through your chosen
        specialization. You do not need a GitHub
        account, and coding is not required
        for every track.
    </p>

    <div style="
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
        gap:14px;
        margin-top:20px;
    ">

        <div style="
            border:1px solid #192640;
            padding:15px;
        ">
            <strong>01 / EXPLORE</strong>
            <p>Choose an available challenge
            and your specialization.</p>
        </div>

        <div style="
            border:1px solid #192640;
            padding:15px;
        ">
            <strong>02 / PREPARE</strong>
            <p>Read the challenge instructions
            and access the provided resources.</p>
        </div>

        <div style="
            border:1px solid #192640;
            padding:15px;
        ">
            <strong>03 / CREATE</strong>
            <p>Develop a solution using tools
            appropriate to your chosen track.</p>
        </div>

        <div style="
            border:1px solid #192640;
            padding:15px;
        ">
            <strong>04 / SUBMIT</strong>
            <p>Upload your files and receive
            feedback after an administrator
            completes the evaluation.</p>
        </div>

    </div>

    <p style="
        margin-top:18px;
        font-size:12px;
        color:#687385;
    ">
        The progress tracker measures completed
        platform milestones, not project quality,
        employment eligibility, or award selection.
    </p>

    <p style="
        margin-top:12px;
        padding:12px;
        background:#fff0c4;
        border:1px solid #d3b765;
        font-size:12px;
    ">
        LOCAL DEMONSTRATION ONLY.
        Do not submit real personal information.
        The program is not yet accepting public applicants.
    </p>

</section>
'''


def install_onboarding(app_core):
    """
    Insert onboarding above My Projects.

    Safe to install only once per application import.
    """

    marker = '''
    <div class="heading" id="my-projects">'''

    if app_core.PARTICIPANT_BODY.count(marker) != 1:
        raise RuntimeError(
            "My Projects section not found "
            "in participant dashboard."
        )

    app_core.PARTICIPANT_BODY = (
        app_core.PARTICIPANT_BODY.replace(
            marker,
            ONBOARDING_HTML + marker,
            1
        )
    )


if __name__ == "__main__":
    assert "Your Skills. Your Approach." in ONBOARDING_HTML
    assert "LOCAL DEMONSTRATION ONLY." in ONBOARDING_HTML

    print("PASS: BridgeLab onboarding template ready.")
