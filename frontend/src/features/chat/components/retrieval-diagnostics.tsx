"use client";

import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { listDiagnosticRequests, readRetrievalDiagnostics, setRetrievalCapture } from "@/features/chat/api/world-chat-client";
import type { DiagnosticRequestList, RetrievalDiagnosticsRead } from "@/features/chat/types/retrieval-diagnostics";
import { diagnosticExport, diagnosticFilename, diagnosticSnapshotMatches } from "@/features/chat/utils/diagnostic-export";
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

const stateLabels: Record<string, string> = { committed: "완료", failed: "실패", cancelled: "취소", accepted: "접수", running: "진행 중" };

export function RetrievalDiagnostics({ worldId, threadId }: {
  worldId: string; threadId: string;
}) {
  const [open, setOpen] = useState(false);
  const [requestId, setRequestId] = useState("");
  const [version, setVersion] = useState(0);
  const [snapshot, setSnapshot] = useState<{ key: string; value: RetrievalDiagnosticsRead } | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState(false);
  const [cursor, setCursor] = useState("");
  const [history, setHistory] = useState<{ key: string; cursor: string; value: DiagnosticRequestList } | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const baseKey = JSON.stringify([worldId, threadId, version]);
  const queryKey = JSON.stringify([baseKey, requestId]);
  const pageKey = JSON.stringify([baseKey, cursor]);
  const data = snapshot?.key === queryKey ? snapshot.value : null;
  const error = errorKey === queryKey;
  const requests = history?.key === baseKey ? history.value : null;
  const pageBusy = history?.key !== baseKey || history.cursor !== cursor;
  function refresh() { setCursor(""); setVersion(v => v + 1); }
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    readRetrievalDiagnostics(worldId, threadId, requestId, controller.signal).then(value => {
      if (!controller.signal.aborted) { setSnapshot({ key: queryKey, value }); setErrorKey(null); }
    }).catch(() => { if (!controller.signal.aborted) { setSnapshot(null); setErrorKey(queryKey); } });
    return () => controller.abort();
  }, [open, requestId, worldId, threadId, queryKey]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    listDiagnosticRequests(worldId, threadId, cursor, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setHistory(previous => ({ key: baseKey, cursor, value: { ...value,
        items: cursor && previous?.key === baseKey
          ? [...previous.value.items, ...value.items.filter(item => !previous.value.items.some(old => old.request_id === item.request_id))]
          : value.items } }));
      setHistoryError(null);
    }).catch(() => { if (!controller.signal.aborted) setHistoryError(pageKey); });
    return () => controller.abort();
  }, [open, worldId, threadId, cursor, baseKey, pageKey]);
  async function toggle(enabled: boolean) {
    setBusy(true);
    try { await setRetrievalCapture(worldId, threadId, enabled); setActionError(false); refresh(); }
    catch { setActionError(true); }
    finally { setBusy(false); }
  }
  function download() {
    if (!data?.request || !diagnosticSnapshotMatches(data, worldId, threadId, requestId)) return;
    const exported = diagnosticExport(data, worldId, threadId, requestId);
    const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = diagnosticFilename(data.request.request_id, data.request.created_at); link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <details className={styles.panel} onToggle={event => { if (event.target !== event.currentTarget) return; setOpen(event.currentTarget.open); if (event.currentTarget.open) refresh(); }}>
    <summary>검색 진단 · 문제 해결</summary>
    {open && <div className={styles.body}>
      <p>조회 과정과 답변에 전달한 근거를 확인합니다. 근거 전달은 답변의 정확성을 보장하지 않습니다.</p>
      <label>확인할 요청<select value={requestId} onChange={event => setRequestId(event.target.value)}>
        <option value="">가장 최근 요청</option>
        {requestId && !requests?.items.some(item => item.request_id === requestId) && <option value={requestId}>선택한 요청 · …{requestId.slice(-8)}</option>}
        {requests?.items.map(item => <option key={item.request_id} value={item.request_id}>{new Date(item.created_at).toLocaleString()} · {stateLabels[item.state] ?? item.state} · …{item.request_id.slice(-8)}</option>)}
      </select></label>
      {requests?.next_cursor && <Button variant="secondary" compact type="button" disabled={pageBusy} onClick={() => setCursor(requests.next_cursor!)}>이전 요청 더 보기</Button>}
      {historyError === pageKey && <p role="alert">요청 목록을 불러오지 못했어요. 진단 새로고침으로 다시 확인해 주세요.</p>}
      <Button variant="secondary" compact type="button" onClick={refresh}>진단 새로고침</Button>
      {actionError && <p role="alert">진단 설정 또는 복사를 완료하지 못했어요.</p>}
      {error && <p role="alert">진단을 불러오지 못했어요. 대화 접근 권한과 연결을 확인해 주세요.</p>}
      {!error && !data && <p role="status">진단을 불러오는 중이에요.</p>}
      {data && <>
        <p>요청 상태: {data.request_state ?? "요청 없음"}</p>
        {data.request && <>
          <p>요청 시각: {new Date(data.request.created_at).toLocaleString()}</p>
          <p>요청 ID: {data.request.request_id}</p>
          <Button variant="secondary" compact type="button" onClick={() => { void navigator.clipboard.writeText(data.request!.request_id).then(() => setActionError(false)).catch(() => setActionError(true)); }}>요청 ID 복사</Button>
          <Button variant="secondary" compact type="button" disabled={!diagnosticSnapshotMatches(data, worldId, threadId, requestId)} onClick={download}>{data.details === null ? "기본 진단만 파일 저장" : "상세 진단 파일 저장"}</Button>
        </>}
        {data.status !== "available" && <p>{data.status === "unavailable" ? "이 요청의 진단을 읽을 수 없어요. 채팅 기록은 그대로 유지됩니다." : data.status === "expired" ? "진단 보관 기간이 지났어요." : "이 요청에 저장된 기본 진단이 없어요. 검색 결과가 0개라는 뜻은 아닙니다."}</p>}
        {data.record && <ol aria-label="이 요청의 처리 이벤트" className={styles.events}>
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
          <Button variant="secondary" compact type="button" disabled={busy} onClick={() => void toggle(false)}>상세 기록 지우기</Button>
        </> : <p>이 요청의 상세 기록이 없습니다. 수집 전 요청이거나 만료·재시작으로 사라졌을 수 있습니다.</p>}
      </>}
    </div>}
  </details>;
}
