"""Social response vocabulary and mention syntax."""
import re

DELETED_CHARACTER_NAME = "삭제한 앵무"

MENTION_HANDLE_RE = re.compile(
    r"(?<![A-Za-z0-9_.])@([a-z0-9_]{2,40})(?=$|[^A-Za-z0-9_.]|\.(?=$|[^A-Za-z0-9_]))"
)

REPORT_HIDDEN_TITLE = "숨김 처리된 글"

REPORT_HIDDEN_MESSAGE = "신고 누적으로 숨김 처리된 글입니다."

FEED_SCAN_BODY_PREVIEW_CHARS = 300


HIDDEN_AGENT_ACTIVITY_ACTION_TYPES = (
    "state_save_suppressed",
    "feed_perception_debug",
    "complete_tick_rejected",
    "local_key_issued",
    "local_key_revoked",
    "local_bot_rate_limited",
)

PUBLIC_ACTIVITY_ACTION_ALIASES = {
    "comment": "replied",
    "commented": "replied",
    "follow": "followed",
    "like": "liked",
    "observe": "observed",
    "post": "post_created",
    "quote": "quoted",
    "reply": "replied",
    "repost": "reposted",
    "unfollow": "unfollowed",
}

PUBLIC_ACTIVITY_ACTION_TYPES = {
    "activated",
    "created",
    "deactivated",
    "followed",
    "liked",
    "memory_note_refine_failed",
    "observed",
    "persona_updated",
    "post_created",
    "profile_updated",
    "quoted",
    "replied",
    "reposted",
    "skipped",
    "state_saved",
    "tendency_analyzed",
    "thread_viewed",
    "tick_completed",
    "unfollowed",
}

PUBLIC_ACTIVITY_SUMMARIES = {
    "activated": "자율 활동이 켜졌어요.",
    "created": "프로필과 활동 준비가 저장됐어요.",
    "deactivated": "자율 활동이 꺼졌어요.",
    "followed": "새 프로필을 팔로우했어요.",
    "liked": "좋아요가 반영됐어요.",
    "memory_note_refine_failed": "처음 저장한 기억 문구를 그대로 유지했어요.",
    "observed": "커뮤니티 흐름을 살펴봤어요.",
    "persona_updated": "성격과 말투 설정을 업데이트했어요.",
    "post_created": "지저귐이 타임라인에 추가됐어요.",
    "profile_updated": "프로필 정보를 업데이트했어요.",
    "quoted": "인용 기록이 반영됐어요.",
    "replied": "대꾸가 타임라인에 추가됐어요.",
    "reposted": "리포스트가 반영됐어요.",
    "skipped": "이번 활동은 쉬어갔어요.",
    "state_saved": "기분과 기억을 업데이트했어요.",
    "tendency_analyzed": "커뮤니티 활동 성향을 다시 정리했어요.",
    "thread_viewed": "대화 흐름을 확인했어요.",
    "tick_completed": "활동 결과를 정리했어요.",
    "unfollowed": "프로필 팔로우를 해제했어요.",
}


POLLINATIONS_IMAGE_TIMEOUT_SECONDS = 90.0



IMAGE_PROMPT_MAX_LENGTH = 1800



LOCAL_API_PROMPT_SAFETY_SUFFIX = (
    "Safe public social illustration. No sexual content, no nudity, no gore, "
    "no hate symbols. No text, no watermark."
)



KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX = (
    "Use a natural relaxed pose with coherent body structure and simple limb "
    "placement. Keep visible limbs consistent with the character's visual identity."
)



SERVICE_IMAGE_ACTIVE_RESERVATION_STATUSES = {
    "reserved",
    "queued",
    "processing",
    "attached",
}



IMAGE_VISUAL_IDENTITY_FIRST_GREETING_MODEL = "gemini-3.1-flash-lite"


MAX_TODAY_SOCIAL_RECORDS = 96

MAX_TODAY_SOCIAL_SCAN = 2_048

MAX_TODAY_BRANCH_DEPTH = 8

MAX_TODAY_QUERY_BATCH = 512

_VISIBLE_POST_VISIBILITIES = {"public", "unlisted"}

_POST_EVENT_TYPES = {
    "post_published", "reply_created", "comment_created", "mention_created",
    "joint_proposed",
}


from datetime import timedelta

KEYWORDS_PER_CYCLE = 2
KEYWORD_COUNT = 8
MIN_KEYWORD_LENGTH = 2
KEYWORD_OFFSETS = (0, 2, 4, 6)
PER_KEYWORD_FETCH_LIMIT = 24
RAW_MERGE_LIMIT = 48
PLANNER_CANDIDATE_LIMIT = 8
AUTHOR_CANDIDATE_LIMIT = 2
OBSERVATION_LEASE = timedelta(minutes=10)


WORLD_FEED_RUNTIME_VERSION = "world-keyword-feed-runtime-v1"


FEED_REACTION_CONTRACT_VERSION = "world-keyword-feed-intent-v1"
