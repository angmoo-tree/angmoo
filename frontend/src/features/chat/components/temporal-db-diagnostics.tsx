"use client";

import { useUiText } from "@/hooks/use-ui-text";
import type { RetrievalDiagnosticsRead } from "../types/retrieval-diagnostics";
import styles from "./retrieval-diagnostics.module.css";

const labels: Record<string, string> = {
  resolved: "날짜 조건 적용", invalid: "날짜 해석 오류", ambiguous: "날짜 범위 불명확", not_requested: "날짜 조건 없음",
  admission: "요청 접수", workflow_checkpoint: "처리 중 저장", diagnostic_persist: "진단 저장",
  response_finalize: "최종 응답 저장", cancel_or_failure: "취소·실패 정리", post_commit: "응답 저장 후 처리",
  complete: "관측한 쓰기 구간 완료", partial: "일부 구간 미측정", write_span_only: "쓰기 구간만 관측", no_writes: "관측한 쓰기 없음",
  committed: "저장 완료", rolled_back: "되돌림 완료", busy: "쓰기 경합",
  model_search_text: "모델이 해석한 검색어", original_user_message: "원래 사용자 질문", none: "검색어 없음",
};

export function TemporalDbDiagnostics({ data }: { data: RetrievalDiagnosticsRead }) {
  const uiText = useUiText("chat");
  const time = data.temporal_recall;
  const db = data.db_write?.request_id === data.request_id && data.db_write?.attempt_number === data.request?.attempt_number ? data.db_write : null;
  const name = (value: string) => uiText(labels[value] ?? value);
  const measured = (value: number | null | undefined) => value == null ? uiText("미측정") : `${value.toFixed(3)} ms`;
  return <section aria-label={uiText("날짜 해석과 DB 쓰기 진단")} className={styles.timing}>
    {time && <>
      <h4>{uiText("날짜 해석")}</h4>
      <p>{name(time.time_resolution)}</p>
      <dl>
        <dt>{uiText("질문 기준 시각·시간대")}</dt><dd>{time.reference_utc ?? uiText("미측정")} · {time.timezone ?? uiText("미측정")}</dd>
        <dt>{uiText("검색어 출처")}</dt><dd>{name(time.query_origin)}</dd>
        <dt>{uiText("날짜 필터 적용 / 실제 검색 실행")}</dt><dd>{uiText(time.time_filter_applied ? "예" : "아니요")} / {uiText(time.retrieval_executed ? "예" : "아니요")}</dd>
        {time.time_filter_applied && <><dt>{uiText("적용한 날짜 범위")}</dt><dd>{time.applied_from} — {time.applied_to}</dd></>}
      </dl>
      {time.retrieval_executed && (time.time_resolution === "invalid" || time.time_resolution === "ambiguous") && <p>{uiText("날짜 조건을 적용하지 않은 관련 검색입니다. 검색 결과가 질문한 날짜의 일이라는 뜻은 아닙니다.")}</p>}
    </>}
    <h4>{uiText("DB 쓰기 시간")}</h4>
    {!db ? <p>{uiText("이 요청의 DB 쓰기 시간은 수집되지 않았거나 보관이 끝났습니다.")}</p> : <>
      <p>{name(db.coverage)}</p>
      <dl>
        <dt>{uiText("가장 긴 한 번의 잠금 보유")}</dt><dd>{measured(db.longest_hold_ms)}</dd>
        <dt>{uiText("관측한 잠금 보유 합계")}</dt><dd>{measured(db.total_hold_ms)}</dd>
        <dt>{uiText("쓰기 구간 합계·잠금 시간 아님")}</dt><dd>{measured(db.total_write_span_ms)}</dd>
        <dt>{uiText("재시도 횟수 / 실제 대기")}</dt><dd>{db.retry_count} / {measured(db.retry_wait_ms)}</dd>
      </dl>
      <p>{uiText("획득 시간에는 BEGIN 실행과 대기가 포함됩니다. commit과 진단 저장은 바깥 쓰기 구간에 포함되므로 더하지 않습니다. 이 기록만으로 SNS 지연의 원인을 단정할 수 없습니다.")}</p>
      <details><summary>{uiText("DB 쓰기 구간 보기")}</summary>
        <ol className={styles.events}>{db.attempts.slice(0, 64).map(row => <li key={row.sequence}>
          <strong>{name(row.stage)} · {name(row.outcome)}</strong>
          <dl>
            <dt>{uiText("기준점 이후 시작 / 종료")}</dt><dd>{measured(row.start_offset_ms)} / {measured(row.end_offset_ms)}</dd>
            <dt>{uiText("연결 / BEGIN 획득")}</dt><dd>{measured(row.checkout_ms)} / {measured(row.acquire_ms)}</dd>
            <dt>{uiText("잠금 보유 / 쓰기 구간")}</dt><dd>{measured(row.hold_ms)} / {measured(row.write_span_ms)}</dd>
            <dt>{uiText("commit / rollback / 내부 진단 저장")}</dt><dd>{measured(row.commit_ms)} / {measured(row.rollback_ms)} / {measured(row.diagnostic_persist_ms)}</dd>
          </dl>
        </li>)}</ol>
      </details>
      {db.omitted_attempts > 0 && <p>{uiText("생략하거나 끝을 확인하지 못한 쓰기 구간: {{count}}개", { count: db.omitted_attempts })}</p>}
    </>}
  </section>;
}
