"use client";

import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { readRetrievalDiagnostics, setRetrievalCapture } from "@/features/chat/api/world-chat-client";
import type { RetrievalDiagnosticsRead } from "@/features/chat/types/retrieval-diagnostics";
import styles from "./retrieval-diagnostics.module.css";

const labels: Record<string, string> = {
  request: "요청", router: "조회 경로 선택", step: "조회 단계", search: "실제 검색",
  step_elapsed: "단계 소요 시간", graph_query: "관계 조회", validated_result: "검증된 결과",
  planner: "조회 계획", both_merge: "두 경로 조합", bundle: "근거 묶음", evidence_deduplication: "중복 제거", evidence_limit: "근거 상한", revalidation: "원본 재검증",
  crg_input: "답변 생성에 근거 전달", evidence_kind: "근거 종류", crg_completed: "답변 생성 완료",
  workflow_failed: "처리 실패", candidates: "후보", accepted: "검증 후", excluded: "제외",
  returned: "조회 결과", items: "근거 수", queries: "조회 횟수", elapsed_ms: "소요 시간(ms)",
  skipped: "건너뜀", executed: "실행", search_memory_items: "기억 검색", search_posts: "게시글·답글 근거 검색",
  search_thread_messages: "대화 근거 검색", canonical_dependency_empty: "앞 단계 결과가 없어 건너뜀",
  graph_dependency_empty: "앞 단계 결과가 없어 건너뜀",
};

export function RetrievalDiagnostics({ worldId, threadId, requestIds }: {
  worldId: string; threadId: string; requestIds: string[];
}) {
  const [open, setOpen] = useState(false);
  const [requestId, setRequestId] = useState("");
  const [version, setVersion] = useState(0);
  const [data, setData] = useState<RetrievalDiagnosticsRead | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    readRetrievalDiagnostics(worldId, threadId, requestId, controller.signal).then(value => {
      if (!controller.signal.aborted) { setData(value); setError(false); }
    }).catch(() => { if (!controller.signal.aborted) { setData(null); setError(true); } });
    return () => controller.abort();
  }, [open, requestId, worldId, threadId, version]);
  async function toggle(enabled: boolean) {
    setBusy(true);
    try { await setRetrievalCapture(worldId, threadId, enabled); setVersion(v => v + 1); }
    catch { setError(true); }
    finally { setBusy(false); }
  }
  function download() {
    if (!data?.details) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(data.details, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = "angmoo-query-diagnostics.json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <details className={styles.panel} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>검색 진단 · 문제 해결</summary>
    {open && <div className={styles.body}>
      <p>조회 과정과 답변에 전달한 근거를 확인합니다. 근거 전달은 답변의 정확성을 보장하지 않습니다.</p>
      <label>확인할 요청<select value={requestId} onChange={event => { setRequestId(event.target.value); setData(null); }}>
        <option value="">가장 최근 요청</option>
        {requestIds.map((id, index) => <option key={id} value={id}>이전 응답 {index + 1}</option>)}
      </select></label>
      <Button variant="secondary" compact type="button" onClick={() => setVersion(v => v + 1)}>진단 새로고침</Button>
      {error && <p role="alert">진단을 불러오지 못했어요. 대화 접근 권한과 연결을 확인해 주세요.</p>}
      {!error && !data && <p role="status">진단을 불러오는 중이에요.</p>}
      {data && <>
        <p>요청 상태: {data.request_state ?? "요청 없음"}</p>
        {data.status !== "available" && <p>{data.status === "unavailable" ? "이 요청의 진단을 읽을 수 없어요. 채팅 기록은 그대로 유지됩니다." : data.status === "expired" ? "진단 보관 기간이 지났어요." : "이 요청에 저장된 기본 진단이 없어요. 검색 결과가 0개라는 뜻은 아닙니다."}</p>}
        {data.record && <ol className={styles.events}>
          {data.record.events.map((entry, index) => <li key={index}>
            <strong>{labels[String(entry.event)] ?? entry.event}</strong>
            <dl>{Object.entries(entry).filter(([key]) => key !== "event").map(([key, value]) => <div key={key}>
              <dt>{labels[key] ?? key}</dt><dd>{typeof value === "boolean" ? (value ? "예" : "아니요") : labels[String(value)] ?? String(value)}</dd>
            </div>)}</dl>
          </li>)}
        </ol>}
        {!!data.record?.omitted_events && <p>상한으로 생략한 관측 {data.record.omitted_events}개가 있습니다.</p>}
        <hr />
        <p>상세 진단은 검색어와 적용 조건을 포함할 수 있습니다. 현재 대화의 다음 10개 요청 또는 30분 동안만 수집하며, 재시작하면 사라집니다.</p>
        <Button variant="secondary" compact type="button" disabled={busy} onClick={() => void toggle(!data.capture.enabled)}>
          {data.capture.enabled ? "상세 진단 끄고 기록 지우기" : "현재 대화의 상세 진단 켜기"}
        </Button>
        <p>상세 수집: {data.capture.enabled ? `켜짐 · 남은 요청 ${data.capture.remaining}개` : "꺼짐"}</p>
        {data.details ? <>
          <details><summary>수집한 검색 조건 보기</summary><pre>{JSON.stringify(data.details, null, 2)}</pre></details>
          <p>검색어에 개인 내용이 포함될 수 있습니다. 내려받은 복사본은 직접 관리해야 합니다.</p>
          <Button variant="secondary" compact type="button" onClick={download}>상세 진단 파일 저장</Button>
          <Button variant="secondary" compact type="button" disabled={busy} onClick={() => void toggle(false)}>상세 기록 지우기</Button>
        </> : <p>이 요청의 상세 기록이 없습니다. 수집 전 요청이거나 만료·재시작으로 사라졌을 수 있습니다.</p>}
      </>}
    </div>}
  </details>;
}
