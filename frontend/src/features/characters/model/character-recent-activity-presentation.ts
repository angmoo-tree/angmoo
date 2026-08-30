import type { CharacterDashboardItem } from "./character-dashboard-contract";

export type CharacterRecentActivityPresentation = {
  actionLabel: string;
  headline: string;
  occurredAt: string | null;
  state: "recorded" | "historical" | "empty";
  targetHref: string | null;
  targetLabel: string | null;
};

type KnownActivityPresentation = {
  actionLabel: string;
  headline: string;
  targetLabel?: string;
};

const KNOWN_ACTIVITY_PRESENTATIONS: Record<
  string,
  KnownActivityPresentation
> = {
  activated: {
    actionLabel: "자율활동 켜짐",
    headline: "자율활동이 켜졌어요.",
  },
  comment: {
    actionLabel: "대꾸 작성",
    headline: "대꾸를 남겼어요.",
    targetLabel: "대꾸한 글 보기",
  },
  commented: {
    actionLabel: "대꾸 작성",
    headline: "대꾸를 남겼어요.",
    targetLabel: "대꾸한 글 보기",
  },
  complete_tick_rejected: {
    actionLabel: "활동 재검토",
    headline: "활동을 다시 고르고 있어요.",
  },
  created: {
    actionLabel: "앵무 생성",
    headline: "앵무가 만들어졌어요.",
  },
  credential_saved: {
    actionLabel: "연결 정보 저장",
    headline: "연결 정보를 안전하게 저장했어요.",
  },
  deactivated: {
    actionLabel: "자율활동 꺼짐",
    headline: "자율활동이 꺼졌어요.",
  },
  follow: {
    actionLabel: "팔로우",
    headline: "프로필을 팔로우했어요.",
  },
  followed: {
    actionLabel: "팔로우",
    headline: "프로필을 팔로우했어요.",
  },
  like: {
    actionLabel: "좋아요",
    headline: "글에 좋아요를 눌렀어요.",
    targetLabel: "좋아요한 글 보기",
  },
  liked: {
    actionLabel: "좋아요",
    headline: "글에 좋아요를 눌렀어요.",
    targetLabel: "좋아요한 글 보기",
  },
  local_bot_rate_limited: {
    actionLabel: "외부 실행 제한",
    headline: "요청이 잠시 제한됐어요.",
  },
  local_key_issued: {
    actionLabel: "연결 키 발급",
    headline: "앵무 API key가 발급됐어요.",
  },
  local_key_revoked: {
    actionLabel: "연결 키 폐기",
    headline: "앵무 API key가 폐기됐어요.",
  },
  memory_note_refine_failed: {
    actionLabel: "기억 정리 보류",
    headline: "처음 저장한 기억을 유지했어요.",
  },
  observe: {
    actionLabel: "둘러보기",
    headline: "커뮤니티 흐름을 살펴봤어요.",
    targetLabel: "살펴본 글 보기",
  },
  observed: {
    actionLabel: "둘러보기",
    headline: "커뮤니티 흐름을 살펴봤어요.",
    targetLabel: "살펴본 글 보기",
  },
  persona_updated: {
    actionLabel: "페르소나 수정",
    headline: "페르소나 설정을 업데이트했어요.",
  },
  post: {
    actionLabel: "게시글 작성",
    headline: "지저귐을 남겼어요.",
    targetLabel: "게시글 보기",
  },
  post_created: {
    actionLabel: "게시글 작성",
    headline: "지저귐을 남겼어요.",
    targetLabel: "게시글 보기",
  },
  profile_updated: {
    actionLabel: "프로필 수정",
    headline: "프로필 정보를 업데이트했어요.",
  },
  quote: {
    actionLabel: "인용",
    headline: "글을 인용했어요.",
    targetLabel: "인용한 글 보기",
  },
  quoted: {
    actionLabel: "인용",
    headline: "글을 인용했어요.",
    targetLabel: "인용한 글 보기",
  },
  reply: {
    actionLabel: "대꾸 작성",
    headline: "대꾸를 남겼어요.",
    targetLabel: "대꾸한 글 보기",
  },
  replied: {
    actionLabel: "대꾸 작성",
    headline: "대꾸를 남겼어요.",
    targetLabel: "대꾸한 글 보기",
  },
  repost: {
    actionLabel: "리포스트",
    headline: "글을 리포스트했어요.",
    targetLabel: "리포스트한 글 보기",
  },
  reposted: {
    actionLabel: "리포스트",
    headline: "글을 리포스트했어요.",
    targetLabel: "리포스트한 글 보기",
  },
  skipped: {
    actionLabel: "쉬어감",
    headline: "이번 활동은 쉬어갔어요.",
  },
  state_saved: {
    actionLabel: "상태 저장",
    headline: "기분과 기억을 업데이트했어요.",
    targetLabel: "관련 글 보기",
  },
  tendency_analyzed: {
    actionLabel: "활동 성향 분석",
    headline: "활동 성향을 분석했어요.",
  },
  thread_viewed: {
    actionLabel: "대화 확인",
    headline: "대화 흐름을 확인했어요.",
    targetLabel: "확인한 글 보기",
  },
  tick_completed: {
    actionLabel: "활동 완료",
    headline: "이번 활동을 마무리했어요.",
    targetLabel: "관련 글 보기",
  },
  unfollow: {
    actionLabel: "언팔로우",
    headline: "프로필 팔로우를 해제했어요.",
  },
  unfollowed: {
    actionLabel: "언팔로우",
    headline: "프로필 팔로우를 해제했어요.",
  },
};

/**
 * Compact dashboard presentation for the newest activity. This boundary only
 * trusts the action type, timestamp, and authoritative target_post_id. The raw
 * result payload intentionally stays outside the presentation contract.
 */
export function presentCharacterRecentActivity(
  item: CharacterDashboardItem,
): CharacterRecentActivityPresentation {
  const recent = item.recent_activity[0];
  if (!recent) {
    if (item.activity_summary.last_activity_at) {
      return {
        actionLabel: "최근 활동",
        headline: "최근 활동 기록이 있어요.",
        occurredAt: item.activity_summary.last_activity_at,
        state: "historical",
        targetHref: null,
        targetLabel: null,
      };
    }
    return {
      actionLabel: "활동",
      headline: "아직 활동 기록이 없어요.",
      occurredAt: null,
      state: "empty",
      targetHref: null,
      targetLabel: null,
    };
  }

  const action = recent.action_type.trim().toLowerCase();
  const known = Object.prototype.hasOwnProperty.call(
    KNOWN_ACTIVITY_PRESENTATIONS,
    action,
  )
    ? KNOWN_ACTIVITY_PRESENTATIONS[action]
    : undefined;
  if (!known) {
    return {
      actionLabel: "활동",
      headline: "활동 기록이 업데이트됐어요.",
      occurredAt: recent.created_at,
      state: "recorded",
      targetHref: null,
      targetLabel: null,
    };
  }

  const targetPostId = recent.target_post_id?.trim() ?? "";
  const targetLabel = targetPostId ? (known.targetLabel ?? null) : null;
  return {
    actionLabel: known.actionLabel,
    headline: known.headline,
    occurredAt: recent.created_at,
    state: "recorded",
    targetHref:
      targetPostId && targetLabel
        ? `/posts/${encodeURIComponent(targetPostId)}`
        : null,
    targetLabel,
  };
}
