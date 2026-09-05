"""Recognize existing scheduled and owner-manual policy sessions."""
from app.domains.routines.constants import POLICY_SESSION_MARKER, MANUAL_POLICY_SESSION_MARKER


def is_policy_enforced_session(session_key: str) -> bool:
    return (
        POLICY_SESSION_MARKER in session_key
        or MANUAL_POLICY_SESSION_MARKER in session_key
    )



def is_manual_policy_session(session_key: str) -> bool:
    return MANUAL_POLICY_SESSION_MARKER in session_key

