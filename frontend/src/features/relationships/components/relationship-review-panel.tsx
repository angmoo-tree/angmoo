"use client";
import { SettingsCard } from "@/components/ui/settings-card";
import { History } from "lucide-react";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";

import { useUiText } from "@/hooks/use-ui-text";


import { useEffect, useState } from "react";
import { getRelationshipReview } from "@/features/relationships/api/relationship-graph";
import type { RelationshipReviewRead } from "@/features/relationships/types/relationship-graph";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";

const labels: Record<string, string> = {
  memory_disabled: "기억 사용 꺼짐", consent_or_ai_required: "기억 AI 설정·동의 필요",
  schedule_disabled: "하루 정리 예약 꺼짐", scheduled: "기억 생성 이후 순서대로 정리",
  consolidation_configuration_required: "기억 정리용 API 키·모델 설정 필요",
  pending: "검토 대기", running: "검토 중", ready: "최종 적용 대기", applied: "검토 완료",
  failed: "제한·오류 확인 후 재개", stale: "자료 변경으로 검토 제외",
};

const errorLabels: Record<string, string> = {
  relationship_review_profile_changed: "설정이 변경되어 다시 확인이 필요해요.",
  relationship_review_credential_changed: "API 키가 변경되어 다시 확인이 필요해요.",
  relationship_review_credential_unavailable: "기억 정리용 API 키를 확인해주세요.",
  relationship_review_credential_binding_required: "기억 정리용 API 키를 확인해주세요.",
  relationship_review_no_eligible_memory: "현재 정리할 수 있는 기억이 없어요.",
  relationship_review_identity_unavailable: "현재 캐릭터와 상대의 접근 권한을 확인해주세요.",
  relationship_review_split_after_incomplete: "기억을 나누어 정리를 이어가요.",
  relationship_review_validation_failed: "정리 결과를 확인하지 못해 다시 확인이 필요해요.",
  relationship_review_retry_required: "정리 상태를 확인해주세요.",
};

export function RelationshipReviewPanel({ characterId, worldId, revision, authenticated, names }: {
  characterId: string; worldId: string; revision: number; authenticated: boolean; names: Record<string, string>;
}) {
  const formatDate = useUiDateFormatter();
  const uiText = useUiText("relationships");
  const [data, setData] = useState<RelationshipReviewRead | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!authenticated) return;
    let current = true;
    const controller = new AbortController();
    const scope = captureAuthRequestScope();
    const canApply = () => current && !controller.signal.aborted && isCurrentAuthRequestScope(scope);
    getRelationshipReview(characterId, worldId, controller.signal).then((value) => {
      if (canApply()) { setData(value); setError(false); }
    }).catch(() => { if (canApply()) setError(true); });
    return () => { current = false; controller.abort(); };
  }, [characterId, worldId, revision, authenticated]);
  if (!authenticated) return null;
  return <SettingsCard elevated title={uiText("하루 관계 정리")} description={uiText("저장된 기억으로 관계를 정리해요. 조회와 새로고침은 AI를 호출하지 않아요.")} icon={<History size={20} />}>
    {error ? <p role="alert" className="mt-2 text-sm">{uiText("정리 상태를 불러오지 못했습니다. 기존 관계는 보존됩니다.")}</p> : !data ? <p className="mt-2 text-sm">{uiText("상태 확인 중…")}</p> : <>
      <p className="mt-2 text-sm">{data.mode === "interpreted" ? uiText("개인화 관계 적용 중") : uiText("관계 정책 전환 대기")} · {uiText(labels[data.configuration.status] ?? "정리 상태 확인 필요")}</p>
      {data.configuration.manual_available ? <p className="text-sm text-on-surface-variant">{uiText("기억 화면의 ‘지금 기억·관계 정리’로 예약 시간과 관계없이 실행할 수 있습니다.")}</p> : null}
      {data.configuration.local_time ? <p className="text-sm text-on-surface-variant">{uiText("예약")}{data.configuration.local_time} ({data.configuration.timezone})</p> : null}
      {data.jobs.length === 0 ? <p className="mt-2 text-sm">{uiText("아직 관계 정리 기록이 없습니다. 적용 이후 새 경험에서 만들어진 기억을 사용합니다.")}</p> : <details className="mt-3">
        <summary className="cursor-pointer font-semibold">{uiText("최근 검토")}{data.jobs.length}{uiText("건")}</summary>
        <ul className="mt-2 space-y-2 text-sm">{data.jobs.map((job) => <li key={job.id}>
          {names[job.target_id] ?? uiText("상대")} · {job.period.startsWith("manual:") ? uiText("수동 정리") : job.period} · {uiText(labels[job.status] ?? "정리 상태 확인 필요")} {uiText("· 기억")}{job.memory_count}{uiText("개 ·")}{job.phase === "final" ? uiText("분할·종합") : uiText("상대별 검토")}
          {job.error_code ? <span className="block text-on-surface-variant">{uiText("재개 상태:")}{uiText(errorLabels[job.error_code] ?? "정리 상태를 확인해주세요.")}</span> : null}
        </li>)}</ul>
      </details>}
      {data.states.length ? <details className="mt-3"><summary className="cursor-pointer text-sm font-semibold">{uiText("지표 갱신 시점")}</summary>
        <ul className="mt-2 space-y-1 text-sm">{data.states.map((row) => <li key={row.target_id}>{names[row.target_id] ?? uiText("상대")} · {row.last_metric_at ? formatDate(row.last_metric_at) : uiText("개인화 지표 반영 전")}</li>)}</ul>
      </details> : null}
      {Object.keys(data.excluded_counts).length ? <p className="mt-2 text-sm text-on-surface-variant">{uiText("상대 또는 근거를 확정하지 못해 제외한 기억")}{Object.values(data.excluded_counts).reduce((a, b) => a + b, 0)}{uiText("개. 원래 기억은 보존됩니다.")}</p> : null}
    </>}
  </SettingsCard>;
}
