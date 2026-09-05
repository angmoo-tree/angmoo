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
