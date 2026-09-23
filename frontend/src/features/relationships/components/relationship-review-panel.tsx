"use client";

import { useEffect, useState } from "react";
import { getRelationshipReview } from "@/features/relationships/api/relationship-graph";
import type { RelationshipReviewRead } from "@/features/relationships/types/relationship-graph";

const labels: Record<string, string> = {
  memory_disabled: "기억 사용 꺼짐", consent_or_ai_required: "기억 AI 설정·동의 필요",
  schedule_disabled: "하루 정리 예약 꺼짐", scheduled: "기억 생성 이후 순서대로 정리",
  pending: "검토 대기", running: "검토 중", ready: "최종 적용 대기", applied: "검토 완료",
  failed: "제한·오류 확인 후 재개", stale: "자료 변경으로 검토 제외",
};

export function RelationshipReviewPanel({ characterId, worldId, revision, authenticated, names }: {
  characterId: string; worldId: string; revision: number; authenticated: boolean; names: Record<string, string>;
}) {
  const [data, setData] = useState<RelationshipReviewRead | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!authenticated) return;
    let current = true;
    getRelationshipReview(characterId, worldId).then((value) => {
      if (current) { setData(value); setError(false); }
    }).catch(() => { if (current) setError(true); });
    return () => { current = false; };
  }, [characterId, worldId, revision, authenticated]);
  return <section aria-label="하루 관계 정리 상태" className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-5">
    <h2 className="font-bold">하루 관계 정리</h2>
    <p className="mt-2 text-sm text-on-surface-variant">저장된 에피소드 기억을 상대별로 검토합니다. 새로고침은 상태만 조회하며 AI를 실행하지 않습니다.</p>
    {error ? <p role="alert" className="mt-2 text-sm">정리 상태를 불러오지 못했습니다. 기존 관계는 보존됩니다.</p> : !data ? <p className="mt-2 text-sm">상태 확인 중…</p> : <>
      <p className="mt-2 text-sm">{data.mode === "interpreted" ? "개인화 관계 적용 중" : "관계 정책 전환 대기"} · {labels[data.configuration.status] ?? data.configuration.status}</p>
      {data.configuration.manual_available ? <p className="text-sm text-on-surface-variant">기억 화면의 ‘지금 기억·관계 정리’로 예약 시간과 관계없이 실행할 수 있습니다.</p> : null}
      {data.configuration.local_time ? <p className="text-sm text-on-surface-variant">예약 {data.configuration.local_time} ({data.configuration.timezone})</p> : null}
      {data.jobs.length === 0 ? <p className="mt-2 text-sm">아직 관계 정리 기록이 없습니다. 적용 이후 새 경험에서 만들어진 기억을 사용합니다.</p> : <details className="mt-3">
        <summary className="cursor-pointer font-semibold">최근 검토 {data.jobs.length}건</summary>
        <ul className="mt-2 space-y-2 text-sm">{data.jobs.map((job) => <li key={job.id}>
          {names[job.target_id] ?? "상대"} · {job.period.startsWith("manual:") ? "수동 정리" : job.period} · {labels[job.status] ?? job.status} · 기억 {job.memory_count}개 · {job.phase === "final" ? "분할·종합" : "상대별 검토"}
          {job.error_code ? <span className="block text-on-surface-variant">재개 상태: {job.error_code}</span> : null}
        </li>)}</ul>
      </details>}
      {data.states.length ? <details className="mt-3"><summary className="cursor-pointer text-sm font-semibold">지표 갱신 시점</summary>
        <ul className="mt-2 space-y-1 text-sm">{data.states.map((row) => <li key={row.target_id}>{names[row.target_id] ?? "상대"} · {row.last_metric_at ? new Date(row.last_metric_at).toLocaleString("ko-KR") : "개인화 지표 반영 전"}</li>)}</ul>
      </details> : null}
      {Object.keys(data.excluded_counts).length ? <p className="mt-2 text-sm text-on-surface-variant">상대 또는 근거를 확정하지 못해 제외한 기억 {Object.values(data.excluded_counts).reduce((a, b) => a + b, 0)}개. 원래 기억은 보존됩니다.</p> : null}
    </>}
  </section>;
}
