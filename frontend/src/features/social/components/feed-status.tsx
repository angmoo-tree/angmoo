import type { FeedStatus } from "@/features/social/api/feed-status";

const readinessLabels = { ready: "Feed 실행 준비됨", blocked: "Feed 준비 확인 필요", disabled: "자율활동 꺼짐", unsupported: "이전 Feed 모드" };
const reasons: Record<string, string> = {
  approved_setup_required: "승인된 프로필·일과가 필요합니다.",
  approved_setup_invalid: "World 설정 또는 승인된 프로필·일과의 연결을 확인해 주세요.",
  world_scope_not_ready: "World와 캐릭터의 소속·활동 상태를 확인해 주세요.",
  world_character_not_ready: "활동 가능한 World 캐릭터가 필요합니다.",
  world_community_profile_invalid: "승인된 프로필의 내용을 확인해 주세요.",
  imported_locked: "가져온 World의 자율활동 승인이 필요합니다.",
  autonomy_disabled: "자율활동이 꺼져 있습니다.",
};
const outcomes: Record<string, string> = {
  no_candidate: "조건에 맞는 새 글 없음", model_abstained: "글을 읽고 반응하지 않음",
  planner_failed: "Feed 판단 중 오류", writer_failed: "댓글 작성 중 오류",
  public_action_failed: "선택한 행동 게시 실패", observation_failed: "관찰 기록 처리 오류",
  duplicate_cycle: "이미 처리한 활동", approved_setup_required: "프로필·일과 미준비로 실행하지 못함",
  approved_setup_invalid: "승인 연결 확인이 필요해 실행하지 못함",
  world_community_profile_stale: "이전 준비 검사에서 차단됨",
  ACTION_SUCCEEDED: "선택한 행동 완료", ACTION_REUSED: "완료된 행동 재사용",
};

export function FeedStatusPanel({ status }: { status?: FeedStatus | null }) {
  if (!status) return <p className="text-sm text-text-secondary">Feed 실행 상태 기록을 확인할 수 없습니다.</p>;
  const attempt = status.last_attempt;
  return <section className="space-y-2 rounded-2xl border border-border-default bg-surface p-4" aria-label="Feed 실행 상태">
    <h4 className="font-bold text-text-strong">현재 준비 상태 · {readinessLabels[status.readiness.state]}</h4>
    {status.readiness.reason_code && <p className="text-sm text-text-secondary">{reasons[status.readiness.reason_code] ?? "실행 조건을 확인해 주세요."}</p>}
    {status.readiness.persona_changed && <p className="text-sm text-text-secondary">기존 승인 프로필·일과로 활동을 계속합니다. 변경된 페르소나를 반영하려면 원할 때 새 결과를 생성할 수 있습니다.</p>}
    <h4 className="pt-2 font-bold text-text-strong">마지막 Feed 실행</h4>
    {attempt ? <div className="space-y-1 text-sm text-text-secondary">
      <p>{new Date(attempt.occurred_at).toLocaleString("ko-KR")} · {outcomes[attempt.result] ?? "실행 결과 확인"}</p>
      <p>후보 {attempt.candidate_count === null ? "미확인" : `${attempt.candidate_count}개`} · 전달 {attempt.delivered_count === null ? "확인되지 않음" : `${attempt.delivered_count}개`}</p>
      {(attempt.delivery_state === "uncertain" || attempt.delivery_state === "dispatched") && <p>전달 완료 여부가 불확실합니다. 완료된 전달 이력과 구분합니다.</p>}
      <p>현재 준비 상태와 과거 실행 결과는 다를 수 있습니다.</p>
    </div> : <p className="text-sm text-text-secondary">최근 실행의 Feed 결과 기록이 없습니다. 후보가 없었다는 의미는 아닙니다.</p>}
  </section>;
}
