"""Versioned deterministic daily planning constants."""

DAYPARTS = ("dawn", "morning", "afternoon", "evening")
DAYPART_START_HOURS = (0, 6, 12, 18)
SELECTION_CONTRACT_VERSION = "daily-activity-selection-v1"
TIMEZONE_CONTRACT_VERSION = "world-local-dayparts-v1"
from app.domains.routines.contracts.lifecycle import EVENT_CONSUMPTION_NAMESPACE
RECENT_EXACT_DAYS = 3
USAGE_WINDOW_DAYS = 7
INITIAL_STATE = {
    "mood": "neutral",
    "mood_intensity": 0,
    "energy": 50,
    "social_energy": 50,
    "action_note": "",
}

BEAT_TRIGGER_KINDS = frozenset({"scheduled", "comment_influenced", "joint_activity"})
TERMINAL_ITEM_STATUSES = frozenset({"completed", "skipped", "interrupted", "cancelled"})

JOINT_SCHEDULING_DAYPARTS = frozenset({"dawn", "morning", "afternoon", "evening"})
JOINT_SCHEDULING_TERMINAL_ITEM_STATUSES = frozenset(
    {"active", "completed", "skipped", "interrupted", "cancelled"}
)
