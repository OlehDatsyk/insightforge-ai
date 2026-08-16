"""
Regression test for ResearchSession.add_progress() on a freshly-constructed,
not-yet-flushed ORM object (see tests/test_api.py for the full-stack version
of this same regression).
"""
from models import ResearchSession


def test_add_progress_on_unflushed_session_does_not_raise():
    session = ResearchSession(
        research_question="Test question for regression coverage",
        mode="quick",
        status="pending",
        current_stage="pending",
        max_sources=4,
        max_tasks=3,
    )
    # Before this fix, session.progress_log was None here (the SQLAlchemy
    # column default only applies at INSERT time), and add_progress() would
    # raise TypeError: Value after * must be an iterable, not NoneType.
    session.add_progress("Research session created", stage="pending")

    assert session.progress_log == [
        {
            "message": "Research session created",
            "stage": "pending",
            "timestamp": session.progress_log[0]["timestamp"],
        }
    ]

    session.add_progress("Second event", stage="planning")
    assert len(session.progress_log) == 2
    assert session.progress_log[1]["message"] == "Second event"
