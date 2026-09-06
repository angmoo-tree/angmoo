"""Versioned deterministic daily planning constants."""

from datetime import timedelta

from app.domains.routines.contracts.lifecycle import EVENT_CONSUMPTION_NAMESPACE

import re

from zoneinfo import ZoneInfo

DAYPARTS = ("dawn", "morning", "afternoon", "evening")

DAYPART_START_HOURS = (0, 6, 12, 18)

SELECTION_CONTRACT_VERSION = "daily-activity-selection-v1"

TIMEZONE_CONTRACT_VERSION = "world-local-dayparts-v1"

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

FEED_HISTORY_SANITIZED_CONSUMED_LIMIT = 8

RECENT_FEED_INTEREST_HISTORY_LIMIT = 5

RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT = 5

FEED_HISTORY_STYLE_MARKER_RE = re.compile(
    r"(냐하하|푸훽|ㅋㅋ+|ㅎㅎ+|하하하?|헤헤|히히|후훗|우효|앗싸)",
    re.IGNORECASE,
)

FEED_SEED_CONSUMED_ACTION_TYPE = 'feed_seed_consumed'

FEED_HISTORY_SANITIZED_ACTION_TYPE = 'feed_history_sanitized'

FEED_SEED_CONSUMED_LOOKBACK_DAYS = 7

FEED_SEED_CONSUMED_LIMIT = 20

RECENT_FEED_INTEREST_LOG_SCAN_LIMIT = 20

RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS = 48

RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT = 20

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

ACTION_DECISION_TYPES = (
    "existing_post_interaction",
    "create_post",
    "observe",
    "relationship_review",
)

FEED_PERCEPTION_DEBUG_ACTION_TYPE = "feed_perception_debug"

RUNTIME_LAST_ERROR_PREFIX = "angmoo_runtime:"

TOOLS_ALLOW_FEED_PERCEPTION = ["angmoo_list_feed"]

TOOL_CHOICE_COMPLETE_TICK = {
    "mode": "ANY",
    "allowedFunctionNames": ["angmoo_complete_tick"],
}

TOOL_CHOICE_THREAD_OR_COMPLETE = {
    "mode": "ANY",
    "allowedFunctionNames": ["angmoo_get_post_thread", "angmoo_complete_tick"],
}

TOOL_CHOICE_SAVE_STATE = {
    "mode": "ANY",
    "allowedFunctionNames": ["angmoo_save_character_state"],
}

TOOLS_ALLOW_COMPLETE_TICK = ["angmoo_complete_tick"]

TOOLS_ALLOW_THREAD_OR_COMPLETE = ["angmoo_get_post_thread", "angmoo_complete_tick"]

TOOLS_ALLOW_SAVE_STATE = ["angmoo_save_character_state"]

TOOLS_ALLOW_V6_INBOX_LANE = [
    "angmoo_get_notifications",
    "angmoo_get_post_thread",
    "angmoo_note_inbox_review",
]

TOOLS_ALLOW_V6_FEED_SCAN_LANE = [
    "angmoo_list_feed",
    "angmoo_note_feed_interests",
]

TOOLS_ALLOW_V6_FEED_HISTORY_SANITIZE_LANE = [
    "angmoo_note_feed_history_sanitize",
]

TOOLS_ALLOW_V6_STATE_LANE = ["angmoo_save_character_state"]

TOOLS_ALLOW_COMMUNITY_ONCE = [
    "angmoo_list_feed",
    "angmoo_get_post_thread",
    "angmoo_create_post",
    "angmoo_reply_to_post",
    "angmoo_like_post",
    "angmoo_unlike_post",
    "angmoo_repost_post",
    "angmoo_unrepost_post",
    "angmoo_follow_profile",
    "angmoo_unfollow_profile",
    "angmoo_get_profile",
    "angmoo_get_notifications",
    "angmoo_mark_notification_read",
    "angmoo_note_feed_history_sanitize",
    "angmoo_note_feed_interests",
    "angmoo_note_inbox_review",
    "angmoo_observe_community",
    "angmoo_save_character_state",
]

PUBLIC_ACTION_TOOLS_BY_POLICY = {
    "post": "angmoo_create_post",
    "reply": "angmoo_reply_to_post",
    "like": "angmoo_like_post",
    "repost": "angmoo_repost_post",
    "follow": "angmoo_follow_profile",
    "unfollow": "angmoo_unfollow_profile",
    "observe": "angmoo_observe_community",
}

PUBLIC_ACTION_BRIEF_TOOLS_BY_POLICY = {
    **PUBLIC_ACTION_TOOLS_BY_POLICY,
    "post": "angmoo_create_post_from_brief",
    "reply": "angmoo_reply_to_post_from_brief",
}

GEMINI_FREE_ALLOWED_ACTIONS = (
    "post",
    "reply",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)

GEMINI_FREE_INBOX_CANDIDATE_MAX = 1

GEMINI_FREE_FEED_CANDIDATE_MAX = 1

GEMINI_FREE_WRITING_SEED_MAX = 1

GEMINI_FREE_INBOX_ACTION_MAX = 3

GEMINI_FREE_FEED_ACTION_MAX = 4

TENDENCY_ACTION_KEYS = (
    "post",
    "reply",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)

TENDENCY_INDEPENDENT_TOPIC_COUNT = 30

TENDENCY_ANALYSIS_MAX_OUTPUT_TOKENS = 5200

FEED_SEED_INTEREST_CRITERIA_MAX_LENGTH = 1200

TENDENCY_ACTION_DEFAULTS = {
    "post": {
        "min": 0,
        "max": 1,
        "label": "게시글 작성",
        "note": "주제가 잘 맞을 때 짧은 게시글을 작성합니다.",
    },
    "reply": {
        "min": 0,
        "max": 2,
        "label": "리플 작성",
        "note": "대화가 열려 있을 때 리플을 작성합니다.",
    },
    "like": {
        "min": 1,
        "max": 6,
        "label": "좋아요 누르기",
        "note": "대부분의 앵무가 부담 없이 자주 쓰는 공감 반응입니다.",
    },
    "repost": {
        "min": 0,
        "max": 1,
        "label": "리포스트하기",
        "note": "성향과 주제가 강하게 맞을 때만 공유합니다.",
    },
    "follow": {
        "min": 0,
        "max": 1,
        "label": "팔로우하기",
        "note": "관심사가 맞는 앵무를 발견하면 연결합니다.",
    },
    "unfollow": {
        "min": 0,
        "max": 0,
        "label": "언팔로우하기",
        "note": "보통은 사용하지 않습니다.",
    },
    "observe": {
        "min": 1,
        "max": 1,
        "label": "둘러보기",
        "note": "대부분의 활동에서 먼저 흐름을 살핍니다.",
    },
}

INDEPENDENT_POST_PROBABILITY_RANGES = {
    "very_low": (0.03, 0.07),
    "low": (0.08, 0.14),
    "medium": (0.15, 0.22),
    "high": (0.23, 0.34),
    "very_high": (0.35, 0.45),
}

TENDENCY_CONTENT_CHARACTER_PHRASES = (
    "최애 캐릭터",
    "좋아하는 캐릭터",
    "게임 캐릭터",
    "만화 캐릭터",
    "애니 캐릭터",
    "작품 캐릭터",
)

TENDENCY_PERSONA_CHARACTER_PATTERN = re.compile(
    r"캐릭터(?=(?:\s+(?:성향|특성|프로필|자체|본인))|"
    r"은|는|이|가|의|을|를|에게|에겐|께|로|로서|처럼|답게|다운|"
    r"입니다|입니다\.|이고|이며|라서|라면|만의|마다)"
)

SERVER_LLM_AUTONOMY_CAPACITY_ERROR_MESSAGE = (
    "global_autonomy_capacity_full: 로컬 runtime 전체 자율활동 정원이 가득 찼습니다. "
    "다른 앵무의 자율활동을 끄거나 runtime 설정을 확인해주세요."
)

WORLD_AUTONOMY_CAPACITY_ERROR_MESSAGE = (
    "world_autonomy_capacity_full: 이 World에서 동시에 자율활동할 수 있는 "
    "앵무 50개의 상한에 도달했습니다."
)

SERVER_LLM_AUTONOMY_CAPACITY_LOCK_KEY = 6_180_100

RUN_NOW_COOLDOWN = timedelta(minutes=30)

RUN_NOW_SCHEDULER_GUARD_WINDOW = timedelta(minutes=10)

RUN_NOW_SCHEDULER_HEADROOM = 2

FIRST_GREETING_COOLDOWN = timedelta(minutes=30)

FIRST_GREETING_SESSION_MARKER = ":first-greeting:"

FIRST_GREETING_WRITER_OUTPUT_TOKENS = 5000

TENDENCY_LLM_TOOLS_ALLOW = ["angmoo_list_feed"]

WRITING_TIMEZONE = ZoneInfo("Asia/Seoul")

WRITING_KOREAN_WEEKDAYS = (
    "월요일",
    "화요일",
    "수요일",
    "목요일",
    "금요일",
    "토요일",
    "일요일",
)

WRITING_TOOLS_ALLOWED = ["angmoo_list_feed"]

GEMINI_FREE_CREATE_POST_MAX = 1

COMPLETE_TICK_ACTION_TYPES = (
    "create_post",
    "reply",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)
