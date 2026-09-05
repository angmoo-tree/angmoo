"""Versioned deterministic daily planning constants."""
import re
from datetime import timedelta
from zoneinfo import ZoneInfo

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


LAST_ERROR_MAX_LENGTH = 2000

SLOT_STATUS_EMPTY = "empty"

SLOT_STATUS_IDLE = "idle"

SLOT_STATUS_BUSY = "busy"

SLOT_STATUS_ASSIGNED_IDLE = "assigned_idle"

SLOT_STATUS_RUNNING = "running"

SLOT_STATUS_COOLDOWN = "cooldown"

SLOT_STATUS_UNHEALTHY = "unhealthy"

FREE_SLOT_STATUSES = {SLOT_STATUS_EMPTY, SLOT_STATUS_IDLE}

DUE_SLOT_STATUSES = {SLOT_STATUS_ASSIGNED_IDLE, SLOT_STATUS_COOLDOWN}

ORPHANED_RESIDENT_RUN_ERROR = "resident_run_orphaned_after_expired_lease"

TEMPORARY_MANUAL_SLOT_RELEASED_ERROR = (
    "temporary_manual_slot_released_after_interruption"
)


MODEL_OVERLOADED_RETRY_MINUTES = 10
MODEL_OVERLOADED_REPEATED_RETRY_MINUTES = 30
MODEL_OVERLOADED_REPEAT_WINDOW = timedelta(hours=2)


GENERIC_OBSERVATION_RESULT = "커뮤니티 흐름을 둘러봤어요."


OBSERVATION_NOTE_ACTION_TYPE = "observation_note_saved"


PUBLIC_ACTION_CLAIM_PATTERNS = (
    re.compile(r"좋아요[^\n.!?。]*?(눌|누르|남겼|했|했다|표시)", re.IGNORECASE),
    re.compile(r"(댓글|답글|대댓글)[^\n.!?。]*?(달|남겼|작성|썼|했|했다)", re.IGNORECASE),
    re.compile(r"(글|게시물|포스트)[^\n.!?。]*?(작성|올렸|남겼|썼|발행|게시)", re.IGNORECASE),
    re.compile(r"(팔로우|리포스트|공유)[^\n.!?。]*?(했|했다|눌|남겼)", re.IGNORECASE),
    re.compile(r"(메시지|응원)[^\n.!?。]*?(남겼|전했|달았|보냈)", re.IGNORECASE),
    re.compile(r"\b(liked|replied|commented|posted|followed|reposted)\b", re.IGNORECASE),
)


V6_OBSERVATION_CONTEXT_TYPES = (
    "inbox_reviewed",
    "feed_viewed",
    "feed_interests_noted",
)


V6_STATE_PUBLIC_ACTION_LEDGER_TYPES = (
    "post_created",
    "replied",
    "liked",
    "reposted",
    "followed",
    "unfollowed",
)


APP_TIMEZONE = ZoneInfo("Asia/Seoul")


DEFAULT_ACTIVITY_ACTIONS = ("post", "reply", "like", "repost", "follow", "unfollow", "observe")


GEMINI_FREE_POLICY_ID = "gemini_free"


KOREAN_WEEKDAYS = (
    "월요일",
    "화요일",
    "수요일",
    "목요일",
    "금요일",
    "토요일",
    "일요일",
)
