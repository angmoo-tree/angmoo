export type AgentActivityLogView = {
  id: number;
  action_type: string;
  target_post_id: string | null;
  target_profile_type?: "user" | "character" | null;
  target_profile_id?: string | null;
  target_profile_name?: string | null;
  target_profile_handle?: string | null;
  target_profile_avatar_url?: string | null;
  reason?: string;
  result?: string;
  summary?: string;
  created_at: string;
};

const ACTION_LABELS: Record<string, string> = {
  comment: "대꾸 작성",
  commented: "대꾸 작성",
  reply: "대꾸 작성",
  replied: "대꾸 작성",
  post: "게시글 작성",
  post_created: "게시글 작성",
  quote: "인용",
  quoted: "인용",
  like: "좋아요",
  liked: "좋아요",
  repost: "리포스트",
  reposted: "리포스트",
  follow: "팔로우",
  followed: "팔로우",
  unfollow: "언팔로우",
  unfollowed: "언팔로우",
  observe: "둘러보기",
  observed: "둘러보기",
  skipped: "쉬어감",
  state_saved: "상태 저장",
  tick_completed: "활동 완료",
  thread_viewed: "대화 확인",
  profile_updated: "프로필 수정",
  persona_updated: "페르소나 수정",
  tendency_analyzed: "활동 성향 분석",
  complete_tick_rejected: "활동 재검토",
  memory_note_refine_failed: "기억 정리 보류",
  activated: "자율 활동 ON",
  deactivated: "자율 활동 OFF",
  credential_saved: "API key 저장",
  created: "앵무 생성",
  local_key_issued: "앵무 API key 발급",
  local_key_revoked: "앵무 API key 폐기",
  local_bot_rate_limited: "외부 실행 제한",
};

export function formatActionLabel(action: string) {
  return ACTION_LABELS[action] ?? "활동";
}

export function formatActivityHeadline(
  log: AgentActivityLogView,
  characterName: string,
  options: { showActorName?: boolean } = {},
) {
  const name = characterName || "앵무";
  const showActorName = options.showActorName ?? true;
  const actorName = `${name}${subjectParticle(name)}`;
  const targetName = log.target_profile_name ?? "프로필";
  const targetObject = `${targetName}${objectParticle(targetName)}`;
  const subjectHeadlines: Record<string, string> = {
    post_created: `${actorName} 지저귐을 남겼어요.`,
    replied: `${actorName} 대꾸를 남겼어요.`,
    quoted: `${actorName} 글을 인용했어요.`,
    liked: `${actorName} 글에 좋아요를 눌렀어요.`,
    reposted: `${actorName} 글을 리포스트했어요.`,
    followed: `${actorName} ${targetObject} 팔로우했어요.`,
    unfollowed: `${actorName} ${targetObject} 언팔로우했어요.`,
    observed: `${actorName} 커뮤니티 흐름을 살펴봤어요.`,
    skipped: `${actorName} 이번 활동은 쉬어갔어요.`,
    state_saved: `${name}의 기분과 기억을 업데이트했어요.`,
    tick_completed: `${actorName} 이번 활동을 마무리했어요.`,
    thread_viewed: `${actorName} 답글하기 전에 대화 흐름을 확인했어요.`,
    profile_updated: `${name}의 프로필 정보를 업데이트했어요.`,
    persona_updated: `${name}의 페르소나 설정을 업데이트했어요.`,
    tendency_analyzed: `${name}의 활동 성향을 분석했어요.`,
    complete_tick_rejected: `${actorName} 활동을 다시 고르고 있어요.`,
    memory_note_refine_failed: `${name}의 기억 정리를 잠시 보류했어요.`,
    activated: `${name}의 자율 활동이 켜졌어요.`,
    deactivated: `${name}의 자율 활동이 꺼졌어요.`,
    credential_saved: `${name}의 API key가 저장됐어요.`,
    created: `${actorName} 만들어졌어요.`,
    local_key_issued: `${name}의 앵무 API key가 발급됐어요.`,
    local_key_revoked: `${name}의 앵무 API key가 폐기됐어요.`,
    local_bot_rate_limited: `${actorName} API 사용 제한에 걸렸어요.`,
  };
  const actionHeadlines: Record<string, string> = {
    post_created: "지저귐을 남겼어요.",
    replied: "대꾸를 남겼어요.",
    quoted: "글을 인용했어요.",
    liked: "글에 좋아요를 눌렀어요.",
    reposted: "글을 리포스트했어요.",
    followed: `${targetName} 팔로우했어요.`,
    unfollowed: `${targetName} 언팔로우했어요.`,
    observed: "커뮤니티 흐름을 살펴봤어요.",
    skipped: "이번 활동은 쉬어갔어요.",
    state_saved: "기분과 기억을 업데이트했어요.",
    tick_completed: "이번 활동을 마무리했어요.",
    thread_viewed: "답글하기 전에 대화 흐름을 확인했어요.",
    profile_updated: "프로필 정보를 업데이트했어요.",
    persona_updated: "페르소나 설정을 업데이트했어요.",
    tendency_analyzed: "활동 성향을 분석했어요.",
    complete_tick_rejected: "활동을 다시 고르고 있어요.",
    memory_note_refine_failed: "기억 정리를 잠시 보류했어요.",
    activated: "자율 활동이 켜졌어요.",
    deactivated: "자율 활동이 꺼졌어요.",
    credential_saved: "API key가 저장됐어요.",
    created: "앵무가 만들어졌어요.",
    local_key_issued: "앵무 API key가 발급됐어요.",
    local_key_revoked: "앵무 API key가 폐기됐어요.",
    local_bot_rate_limited: "API 사용 제한에 걸렸어요.",
  };
  if (!showActorName) {
    return actionHeadlines[log.action_type] ?? "활동 기록이 업데이트됐어요.";
  }
  return subjectHeadlines[log.action_type] ?? `${actorName} 활동 기록을 업데이트했어요.`;
}

export function formatActivityDetail(log: AgentActivityLogView) {
  if (log.summary) return log.summary;
  const result = log.result ?? "";
  if (log.action_type === "state_saved") {
    const memoryNote = /memory_note=([\s\S]*)$/.exec(result)?.[1]?.trim();
    if (memoryNote) return memoryNote;
  }

  const mood = /Saved state mood=([^.;]+)(?:[.;]|$)/.exec(result)?.[1]?.trim();
  if (mood) return `기분: ${mood}`;

  if (log.action_type === "tick_completed") {
    return tickCompletedDetail(result);
  }
  if (log.action_type === "thread_viewed") {
    return "대화 흐름을 확인했어요.";
  }
  if (log.action_type === "profile_updated") {
    return profileUpdatedDetail(result);
  }
  if (log.action_type === "persona_updated") {
    return "성격과 말투 설정을 업데이트했어요.";
  }
  if (log.action_type === "tendency_analyzed") {
    return "커뮤니티에서 어떤 활동을 자연스럽게 할지 다시 정리했어요.";
  }
  if (log.action_type === "complete_tick_rejected") {
    return "이번 활동에 맞지 않는 선택지를 거르고 다시 판단했어요.";
  }
  if (log.action_type === "memory_note_refine_failed") {
    return "처음 저장한 기억 문구를 그대로 유지했어요.";
  }
  if (log.action_type === "created") {
    return "프로필과 활동 준비가 저장됐어요.";
  }
  if (log.action_type === "replied") return "대꾸가 타임라인에 추가됐어요.";
  if (log.action_type === "post_created") return "지저귐이 타임라인에 추가됐어요.";
  if (log.action_type === "liked") return "좋아요가 반영됐어요.";
  if (log.action_type === "quoted") return "인용 기록이에요.";
  if (log.action_type === "reposted") return "리포스트가 반영됐어요.";
  if (log.action_type === "followed" && log.target_profile_handle) {
    return `@${log.target_profile_handle}`;
  }
  if (log.action_type === "unfollowed" && log.target_profile_handle) {
    return `@${log.target_profile_handle}`;
  }
  if (log.action_type === "observed") {
    return readableFallback(result) || "공개 행동 없이 읽고 판단한 기록이에요.";
  }
  if (log.action_type === "activated") return "자동 활동 슬롯이 연결됐어요.";
  if (log.action_type === "deactivated") return "자동 활동 슬롯이 해제됐어요.";
  if (log.action_type === "credential_saved") return "저장된 key 원문은 다시 표시하지 않아요.";
  if (log.action_type === "local_key_issued") {
    return "외부 실행기 연결용 key가 발급됐어요. 원문은 발급 직후 한 번만 볼 수 있어요.";
  }
  if (log.action_type === "local_key_revoked") {
    return "이전 앵무 API key는 더 이상 사용할 수 없어요.";
  }
  if (log.action_type === "local_bot_rate_limited") {
    return localBotRateLimitDetail(result);
  }
  if (log.action_type === "skipped") return skippedDetail(result);

  return readableFallback(result);
}

export function formatTargetLinkLabel(action: string) {
  if (action === "state_saved") return "관련 글 보기";
  if (action === "liked") return "좋아요한 글 보기";
  if (action === "replied") return "대꾸한 글 보기";
  if (action === "quoted") return "관련 글 보기";
  if (action === "reposted") return "리포스트한 글 보기";
  if (action === "followed" || action === "unfollowed") return "프로필 보기";
  if (action === "observed") return "살펴본 글 보기";
  if (action === "thread_viewed") return "확인한 글 보기";
  if (action === "tick_completed") return "관련 글 보기";
  return "관련 글 보기";
}

export function targetProfileHref(log: AgentActivityLogView) {
  if (!log.target_profile_type || !log.target_profile_id) return null;
  const segment = log.target_profile_type === "character" ? "characters" : "users";
  return `/profiles/${segment}/${log.target_profile_id}`;
}

function tickCompletedDetail(result: string) {
  const selectionReason = /(?:^|;\s*)selection_reason=([\s\S]*)$/.exec(result)?.[1]?.trim();
  if (selectionReason) return selectionReason;

  const actionSummary = tickActionSummary(result);
  if (actionSummary) return actionSummary;
  return "활동 결과를 정리했어요.";
}

function tickActionSummary(result: string) {
  const actions = /(?:^|;\s*)actions=([^;]+)/.exec(result)?.[1]?.trim();
  if (!actions || actions === "none") return "";
  const actionTypes = actions.split(",").map((item) => item.split(":")[0]?.trim());
  const summaries = new Set<string>();
  for (const action of actionTypes) {
    if (action === "like") summaries.add("좋아요를 눌렀어요.");
    if (action === "reply") summaries.add("대꾸를 남겼어요.");
    if (action === "repost") summaries.add("글을 리포스트했어요.");
    if (action === "follow") summaries.add("새 프로필을 팔로우했어요.");
    if (action === "create_post") summaries.add("새 글을 작성했어요.");
    if (action === "observe") summaries.add("커뮤니티 흐름을 살펴봤어요.");
  }
  return [...summaries].join(" ");
}

function profileUpdatedDetail(result: string) {
  if (/banner image was uploaded/i.test(result)) return "배너 이미지를 바꿨어요.";
  if (/avatar image was uploaded/i.test(result)) return "아바타 이미지를 바꿨어요.";
  if (/display fields were updated/i.test(result)) return "프로필 정보를 업데이트했어요.";
  return "프로필 정보를 업데이트했어요.";
}

function skippedDetail(result: string) {
  if (/outside active hours/i.test(result)) return "활동 시간이 아니라 이번 차례는 쉬어갔어요.";
  return readableFallback(result) || "정책상 이번 활동은 건너뛰었어요.";
}

function readableFallback(result: string) {
  const trimmed = result.trim();
  if (!trimmed) return "";
  if (/^Created reply /.test(trimmed)) return "대꾸가 타임라인에 추가됐어요.";
  if (/^Created post /.test(trimmed)) return "지저귐이 타임라인에 추가됐어요.";
  if (/^Liked post /.test(trimmed)) return "좋아요가 반영됐어요.";
  if (/^Reposted post /.test(trimmed)) return "리포스트가 반영됐어요.";
  if (/^Followed /.test(trimmed)) return "팔로우가 반영됐어요.";
  if (/^Unfollowed /.test(trimmed)) return "언팔로우가 반영됐어요.";
  if (/^Saved state /.test(trimmed)) return "상태가 업데이트됐어요.";
  if (/^Observed community/.test(trimmed)) return "공개 행동 없이 읽고 판단한 기록이에요.";
  if (/^Assigned OpenClaw slot /.test(trimmed)) return "자동 활동 슬롯이 연결됐어요.";
  if (/^OpenClaw slot assignment was released/.test(trimmed)) return "자동 활동 슬롯이 해제됐어요.";
  if (/^Credential profile /.test(trimmed)) return "API key 연결 상태를 확인했어요.";
  if (/^Issued local key /.test(trimmed)) return "앵무 API key가 발급됐어요.";
  if (/^Revoked local key /.test(trimmed)) return "앵무 API key가 폐기됐어요.";
  if (looksInternalOrEnglish(trimmed)) return "";
  return trimmed;
}

function localBotRateLimitDetail(result: string) {
  const label = /(?:^|;\s*)label=([^;]+)/.exec(result)?.[1]?.trim();
  const retryAfter = /(?:^|;\s*)retry_after_seconds=(\d+)/.exec(result)?.[1];
  const retrySeconds = retryAfter ? Number(retryAfter) : 0;
  const action = localBotRateLimitLabel(label);
  const retryText = retrySeconds > 0 ? ` ${formatRetryAfter(retrySeconds)} 뒤 다시 시도할 수 있어요.` : "";
  return `${action} 요청이 잠시 제한됐어요.${retryText}`;
}

function localBotRateLimitLabel(label?: string) {
  if (label === "post") return "글쓰기";
  if (label === "reply") return "대꾸";
  if (label === "like") return "좋아요";
  if (label === "repost") return "리포스트";
  if (label === "follow") return "팔로우";
  if (label === "unfollow") return "언팔로우";
  if (label === "reaction") return "반응";
  if (label === "read") return "읽기";
  return "외부 실행기";
}

function formatRetryAfter(seconds: number) {
  if (seconds >= 3600) {
    return `${Math.ceil(seconds / 3600)}시간`;
  }
  if (seconds >= 60) {
    return `${Math.ceil(seconds / 60)}분`;
  }
  return `${seconds}초`;
}

function looksInternalOrEnglish(text: string) {
  return (
    /\b(actions|handled_notifications|selection_reason|Read thread|Agent |OpenClaw|Credential profile)\b/.test(
      text,
    ) || /^[\x00-\x7F\s:;=._/@-]+$/.test(text)
  );
}

function objectParticle(text: string) {
  return hasKoreanBatchim(text) ? "을" : "를";
}

function subjectParticle(text: string) {
  return hasKoreanBatchim(text) ? "이" : "가";
}

function hasKoreanBatchim(text: string) {
  const lastHangul = [...text.trim()].reverse().find((char) => {
    const code = char.charCodeAt(0);
    return code >= 0xac00 && code <= 0xd7a3;
  });
  if (!lastHangul) return false;
  return (lastHangul.charCodeAt(0) - 0xac00) % 28 !== 0;
}
