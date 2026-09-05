"""Versioned deterministic daily planning constants."""
from datetime import timedelta

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

OPENING_LEASE = timedelta(seconds=120)

MAX_PARTICIPANT_OPENING_ATTEMPTS = 2

MAX_JOINT_OPENING_ATTEMPTS = 4

ACTIVE_JOINT_STATUSES = {"scheduled", "ready", "active"}

DEFAULT_MAX_COMMENTS_PER_DAY = 30
DEFAULT_MAX_POSTS_PER_DAY = 10

MAX_COMMENTS_PER_DAY = 60
MAX_POSTS_PER_DAY = 30

HIDDEN_ACTIVITY_ACTION_TYPES = (
    "state_save_suppressed",
    "feed_perception_debug",
    "feed_viewed",
    "feed_interests_noted",
    "feed_seed_consumed",
    "inbox_notifications_provided",
    "inbox_reviewed",
    "observation_note_saved",
    "complete_tick_rejected",
)

STATE_SAVE_DEDUPE_WINDOW = timedelta(seconds=90)


PUBLIC_ACTION_TYPES = {
    "comment": ("commented", "replied"),
    "reply": ("commented", "replied"),
    "post": ("post_created",),
    "quote": ("quoted",),
    "like": ("liked",),
    "repost": ("reposted",),
    "follow": ("followed",),
    "unfollow": ("unfollowed",),
}



POLICY_ACTION_NAMES = (
    "post",
    "reply",
    "quote",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)



TENDENCY_PUBLIC_ACTION_NAMES = ("post", "reply", "like", "repost", "follow", "unfollow")



POLICY_SESSION_MARKER = ":resident-tick:"



MANUAL_POLICY_SESSION_MARKER = ":resident-manual:"


ACTIVE_RUN_STATUSES = {"running"}
