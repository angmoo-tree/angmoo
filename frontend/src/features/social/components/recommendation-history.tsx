import type { DeliveryPost, RecommendationDelivery } from "@/features/social/api/recommendation-topics";

const lanes = { latest: "최신글", interest: "관심사", relation: "관계", explore: "탐색" };
const actions = { comment: "댓글", like: "좋아요", repost: "리포스트", follow: "팔로우" };

function resultLabel(post: DeliveryPost) {
  const action = post.selected_action ? actions[post.selected_action] : null;
  if (action) {
    if (post.result_state === "succeeded") return post.selected_action === "comment" ? "댓글 작성 완료" : `${action} 완료`;
    if (post.result_state === "selected") return `${action} 선택 · 실행 결과 확인 불가`;
    if (post.result_state === "pending") return `${action} 처리 중`;
    if (post.result_state === "failed") return `${action} 처리 실패`;
  }
  if (post.result_state === "no_action") return "읽고 지나감";
  if (post.result_state === "not_selected") return "반응 대상으로 선택하지 않음";
  if (post.result_state === "not_performed") return "반응하지 않음";
  return "전달됨 · 반응 결과 확인 불가";
}

function recordedTime(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "기록 시각 확인 불가";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

// LOCAL: one history presentation for Next and static, using existing tokens.
export function RecommendationHistory({ deliveries, loading = false, error }: {
  deliveries?: RecommendationDelivery[]; loading?: boolean; error?: string;
}) {
  return <div className="space-y-2 border-t border-border-default pt-4" aria-label="최근 전달된 Feed">
    <h4 className="font-semibold text-text-strong">최근 전달된 Feed</h4>
    <p className="text-xs text-text-secondary">최근 전달 완료 최대 5회의 기록입니다. 회차마다 최대 20개가 전달되며, 반응하지 않은 글도 다음 Feed에서 제외됩니다.</p>
    {error ? <p role="alert" className="text-sm text-text-secondary">{error}</p>
      : loading ? <p role="status" className="text-sm text-text-secondary">전달 이력 확인 중</p>
      : !Array.isArray(deliveries) ? <p role="status" className="text-sm text-text-secondary">전달 이력을 확인할 수 없습니다. 앱과 서버 버전을 확인한 뒤 다시 조회해 주세요.</p>
      : deliveries.length === 0 ? <>
        <p className="text-sm text-text-secondary">아직 전달된 글이 없습니다.</p>
        <p className="text-xs text-text-secondary">보관 중인 전달 기록 기준입니다. 과거 관찰 기록은 포함하지 않습니다.</p>
      </> : deliveries.map((delivery, index) => <details key={delivery.delivery_id} open={index === 0} className="rounded-lg border border-border-default px-3">
        <summary className="min-h-11 cursor-pointer py-3 text-sm text-text-default focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-text-strong">
          <time dateTime={delivery.recorded_at}>{recordedTime(delivery.recorded_at)}</time>
          {" · 전달 기록 "}{delivery.recorded_post_count === null ? "개수 확인 불가" : `${delivery.recorded_post_count}개`}
          {` · 현재 표시 ${delivery.visible_post_count}개`}
        </summary>
        {delivery.is_partial && <p className="pb-2 text-xs text-text-secondary">일부 기록만 확인할 수 있습니다.</p>}
        {delivery.posts.length === 0 ? <p className="pb-3 text-sm text-text-secondary">현재 표시할 수 있는 글이 없습니다.</p>
          : <ul className="space-y-3 pb-3">{delivery.posts.map(post => <li key={`${delivery.delivery_id}:${post.post_id}`} className="break-words text-sm text-text-default">
            <span className="font-medium">{post.title}</span>
            <span className="mt-1 block text-xs text-text-secondary">{post.lane ? lanes[post.lane] ?? "출처 기록 없음" : "출처 기록 없음"} · {resultLabel(post)}</span>
          </li>)}</ul>}
      </details>)}
  </div>;
}
