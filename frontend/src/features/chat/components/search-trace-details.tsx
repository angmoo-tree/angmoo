import type { SearchDiagnosticTrace } from "../types/search-trace";
import styles from "./retrieval-diagnostics.module.css";

const labels: Record<string, string> = {
  embedding: "질문 임베딩", slot_wait: "작업 슬롯 대기", process_start: "프로세스 시작",
  child_bootstrap: "작업 프로세스 진입", extension_verify: "확장 무결성 확인", query_validate: "검색 입력 검증",
  db_open: "DB 열기", extension_load: "Vec1 로딩", metadata_read: "인덱스 정보 확인",
  eligible_count: "조회 범위의 벡터 수 확인", nn_query: "NN 검색", mapping_read: "문서 매핑",
  result_transport: "결과 전달", worker_cleanup: "작업 프로세스 정리", fts_search: "FTS 검색",
  success: "성공", error: "오류", deadline: "제한 시간 만료", cancelled: "취소", unexpected_exit: "예기치 않은 종료",
  disabled: "사용 안 함", completed: "완료", running: "진행 중 마지막 관측", failed: "실패", unknown: "확인되지 않음",
  ready: "검색 완료", partial: "일부만 사용 가능", unavailable: "검색 사용 불가",
  axis: "검색 축", rrf: "순위 결합", canonical: "원본 검증", select: "기억 선택", hydrate: "원문 연결",
  evidence: "근거 변환", dedup: "중복 제거", limit: "근거 상한", freeze: "근거 동결",
  crg: "응답 생성에 전달", inspector: "근거 화면 snapshot", bundle: "근거 묶음",
  returned: "반환", accepted: "검증 통과", excluded: "제외", merged: "병합", selected: "선택",
  added: "추가", existing: "기존 참조 유지", missing: "확인 불가", kept: "유지", linked: "연결", count: "개수",
};
const name = (value: string | null) => value === null ? "확인되지 않음" : labels[value] ?? value;
const value = (item: string | number | boolean | null) =>
  item === null ? "확인되지 않음" : typeof item === "boolean" ? (item ? "예" : "아니요") : String(item);

export function SearchTraceDetails({ trace }: { trace: SearchDiagnosticTrace }) {
  const stages = [...trace.stages].sort((a, b) => a.axis.localeCompare(b.axis) ||
    (a.clock_domain === b.clock_domain ? a.start_ms - b.start_ms : a.clock_domain === "parent" ? -1 : 1));
  return <section aria-label="상세 검색 실행 진단">
    <p>실행 진단: {trace.coverage === "complete" ? "수집한 기록에 생략 없음" : "일부만 확인됨"} · {trace.version}</p>
    <p>단계 기록 {trace.stage_events_dropped}개, 연결 기록 {trace.lineage_edges_dropped}개, 별칭 {trace.aliases_dropped}개, 검색 조건 {trace.detail_rows_dropped ?? 0}개가 생략되었습니다. 기록이 완전해도 답변의 정확성을 보장하지 않습니다.</p>
    {trace.terminals.map(terminal => <div key={terminal.axis}>
      <strong>{terminal.axis === "vector" ? "벡터" : "FTS"}: {name(terminal.axis_status ?? null)}</strong>
      <p>작업 종료 상태: {name(terminal.terminal_state)}</p>
      <p>마지막 확인 단계: {name(terminal.last_observed_stage)}</p>
      {terminal.failure && <p>오류: {terminal.failure.failure_code} · 실패 단계: {name(terminal.failure.failure_stage)} · {terminal.failure.exception_kind}</p>}
      <dl>
        <dt>프로세스 시작 / 결과 수신 / 정리 완료</dt><dd>{value(terminal.worker_started)} / {value(terminal.result_received)} / {value(terminal.joined)}</dd>
        <dt>종료 사유 / 종료 코드</dt><dd>{terminal.termination_reason} / {value(terminal.worker_exit_code)}</dd>
        <dt>대상 벡터 수</dt><dd>{value(terminal.eligible_vector_count)}</dd>
        <dt>요청 세대 / 실제 확인 세대</dt><dd>{value(terminal.requested_generation)} / {value(terminal.observed_generation)}</dd>
        <dt>실제 세대 일치 확인</dt><dd>{value(terminal.generation_match)}</dd>
      </dl>
      {!terminal.terminal_observed && <p>작업의 최종 보고를 받지 못했습니다. 마지막 단계만으로 내부 원인을 단정하지 않습니다.</p>}
    </div>)}
    <details><summary>검색 실행 단계 보기</summary>
      <p>부모 시간은 요청 관측 시작 기준, 자식 시간은 각 작업 프로세스 시작 기준입니다. 병렬·중첩 구간을 합산하지 않습니다.</p>
      <ol className={styles.events}>{stages.map(row => <li key={[row.axis, row.clock_domain, row.stage].join(":")}>
        <strong>{row.axis} · {name(row.stage)} · {name(row.state)}</strong>
        <p>{row.clock_domain === "parent" ? "부모" : "자식"} 시작 {row.start_ms.toFixed(2)}ms · 소요 {row.elapsed_ms === null ? "확인되지 않음" : row.elapsed_ms.toFixed(2) + "ms"}</p>
        <p>시작 예산 {row.budget_at_start_ms.toFixed(2)}ms · 종료 시 남은 예산 {row.remaining_at_end_ms === null ? "확인되지 않음" : row.remaining_at_end_ms.toFixed(2) + "ms"}</p>
      </li>)}</ol>
    </details>
    <details><summary>후보와 근거 연결 보기</summary>
      <p>d: 문서 · i: 문서 버전 · m: 기억 · s: 원문 · r: 반환 기록 · e: 최종 근거 · k: 중복 키. 이 별칭은 해당 요청 안에서만 연결됩니다.</p>
      <ol className={styles.events}>{trace.lineage.map((row, index) => <li key={index}>
        <strong>{name(row.stage)} · {name(row.action)}</strong>
        <p>{[row.document_ref, row.identity_ref, row.memory_ref, row.source_ref, row.record_ref, row.evidence_ref, row.key_ref].filter(Boolean).join(" · ")}
          {row.related_ref ? " ← " + row.related_ref : ""}</p>
        {row.rank !== null && <span>순위 {row.rank} </span>}
        {row.count !== null && <span>개수 {row.count} </span>}
        {row.reason && <span>기준: {row.reason}</span>}
      </li>)}</ol>
    </details>
  </section>;
}
