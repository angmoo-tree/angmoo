import type { WorldCharacterStatus } from "../api/world-character-status";

const OUTCOMES: Record<string, string> = {
  pending: "준비 중", running: "진행 중", failed: "실패", blocked: "실행 보류", skipped: "건너뜀", cancelled: "취소됨",
};
const COMPLETED_ACTIONS: Record<string, { headline: string; detail: string; linkLabel: string }> = {
  post: { headline: "게시글을 남겼어요.", detail: "게시글이 타임라인에 추가됐어요.", linkLabel: "관련 글 보기" },
  reply: { headline: "답글을 남겼어요.", detail: "답글이 타임라인에 추가됐어요.", linkLabel: "답글을 남긴 글 보기" },
  comment: { headline: "답글을 남겼어요.", detail: "답글이 타임라인에 추가됐어요.", linkLabel: "답글을 남긴 글 보기" },
  like: { headline: "글에 좋아요를 눌렀어요.", detail: "좋아요가 반영됐어요.", linkLabel: "좋아요한 글 보기" },
};

export function presentWorldRecentActivity(row: WorldCharacterStatus["recent_activity"][number]) {
  const completed = ["completed", "succeeded", "success", "ok"].includes(row.status);
  const action = COMPLETED_ACTIONS[row.action];
  return {
    completed,
    headline: completed ? action?.headline ?? "활동 기록이 업데이트됐어요." : OUTCOMES[row.status] ?? "확인 필요",
    detail: completed ? action?.detail : undefined,
    linkLabel: completed ? action?.linkLabel ?? "관련 글 보기" : "관련 글 보기",
  };
}
