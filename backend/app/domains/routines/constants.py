"""Versioned deterministic daily planning constants."""

DAYPARTS = ("dawn", "morning", "afternoon", "evening")
DAYPART_START_HOURS = (0, 6, 12, 18)
SELECTION_CONTRACT_VERSION = "daily-activity-selection-v1"
TIMEZONE_CONTRACT_VERSION = "world-local-dayparts-v1"
EVENT_CONSUMPTION_NAMESPACE = "next_activity_beat"
RECENT_EXACT_DAYS = 3
USAGE_WINDOW_DAYS = 7
INITIAL_STATE = {
    "mood": "neutral",
    "mood_intensity": 0,
    "energy": 50,
    "social_energy": 50,
    "action_note": "",
}
