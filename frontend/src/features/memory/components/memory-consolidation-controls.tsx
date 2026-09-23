"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { getMemoryConsolidation, startMemoryConsolidation, retryMemoryConsolidation, MemoryApiError } from "@/features/memory/api/memory-client";
import { workflowActive, type ConsolidationProgress, type ConsolidationStart, type FlowState } from "@/features/memory/types/consolidation-contract";

const labels: Record<ConsolidationProgress["state"], string> = {
  preparing: "정리할 경험을 확인하고 있어요", queued: "기억 정리를 기다리고 있어요",
  waiting_for_chat: "채팅이 끝나면 기억 정리를 시작해요", ai_running: "AI가 경험을 읽고 기억을 정리하고 있어요",
  applying: "정리한 기억을 저장하고 있어요", completed: "기억 정리를 마쳤어요",
  no_work: "새로 정리할 경험이 없어요", partial_failed: "일부 경험을 정리하지 못했어요",
  failed: "기억 정리를 마치지 못했어요. 실패한 정리 다시 시도를 이용해 주세요.",
  paused: "설정이 바뀌어 기억 정리를 멈췄어요", cancelled: "기억 정리가 취소됐어요",
};
const flowLabels: Record<FlowState, string> = {
  memory_running: "기억 정리 중", memory_failed: "기억 정리를 마치지 못해 관계 정리를 기다리고 있어요",
  memory_only_completed: "기억 정리 완료 · 사용자 캐릭터의 관계는 대신 판단하지 않아요",
  relationship_waiting: "기억 정리 완료 · 관계 정리 대기", relationship_running: "기억 정리 완료 · 관계 정리 중",
  relationship_retry_needed: "기억 정리 완료 · 관계 정리 재시도 대기", relationship_paused: "기억 정리 완료 · 관계 정리를 위한 설정 확인 필요",
  completed: "기억·관계 정리 완료", no_work: "새로 정리할 내용이 없습니다.", no_relationship_work: "기억 정리 완료 · 관계 정리 대상 없음",
};
type Props = {
  worldId: string; subjectId: string; subjectName: string; disabled: boolean; dirty: boolean;
  timezone: string;
  version: number; profileVersion: number; scopeVersion: number;
  acquire: () => boolean; release: () => void; onCompleted: () => void;
};

export function MemoryConsolidationControls(props: Props) {
  const { worldId, subjectId, onCompleted } = props;
  const [progress, setProgress] = useState<ConsolidationProgress | null>(null);
  const [capabilityReady, setCapabilityReady] = useState(false);
  const scopeKey = useRef(`${worldId}:${subjectId}`);
  const [relationshipCapable, setRelationshipCapable] = useState(false);
  const [capabilityReason, setCapabilityReason] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [readError, setReadError] = useState("");
  const pending = useRef<ConsolidationStart | null>(null);
  const alive = useRef(false);
  const generation = useRef(0);
  const finished = useRef<string | null>(null);
  const accepted = useRef<string | null>(null);
  useEffect(() => {
    alive.current = true;
    if (scopeKey.current !== `${worldId}:${subjectId}`) {
      scopeKey.current = `${worldId}:${subjectId}`;
      pending.current = null; accepted.current = null; finished.current = null;
    }
    const scopeGeneration = ++generation.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      let interval = 5_000;
      const acceptedBefore = accepted.current;
      try {
        const read = await getMemoryConsolidation(worldId, subjectId, controller.signal);
        const value = read.progress;
        if (controller.signal.aborted || scopeGeneration !== generation.current || acceptedBefore !== accepted.current) return;
        setCapabilityReady(true); setReadError("");
        setRelationshipCapable(read.capability.relationships);
        setCapabilityReason(read.capability.reason);
        setProgress(value);
        if (value && workflowActive(value)) interval = document.hidden ? 5_000 : 1_000;
        if (value && (["completed", "partial_failed"].includes(value.state) || value.flow_state === "completed") && finished.current !== `${value.request_id}:${value.flow_state ?? value.state}`) {
          finished.current = `${value.request_id}:${value.flow_state ?? value.state}`; onCompleted();
        }
      } catch {
        if (!controller.signal.aborted) setReadError("정리 상태를 확인하지 못했어요. 잠시 후 다시 확인합니다.");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, interval);
      }
    }
    void refresh();
    return () => { alive.current = false; controller.abort(); clearTimeout(timer); };
  }, [worldId, subjectId, onCompleted]);

  async function start() {
    if (busy || !props.acquire()) return;
    const scopeGeneration = generation.current;
    setBusy(true); setError("");
    pending.current ??= { idempotency_key: crypto.randomUUID(), expected_version: props.version,
      expected_profile_version: props.profileVersion, expected_scope_version: props.scopeVersion,
      ...(relationshipCapable ? { followup: "relationships" as const } : {}) };
    try {
      const value = await startMemoryConsolidation(worldId, subjectId, pending.current);
      if (!alive.current || scopeGeneration !== generation.current) return;
      accepted.current = value.request_id;
      pending.current = null; setProgress(value);
    } catch (reason) {
      if (!alive.current || scopeGeneration !== generation.current) return;
      if (reason instanceof MemoryApiError && reason.status === 409) {
        pending.current = null; setError("설정이 변경됐어요. 최신 설정을 확인한 뒤 다시 요청해 주세요.");
      } else setError("기억 정리를 요청하지 못했어요. 연결과 저장된 AI 설정을 확인해 주세요.");
    } finally { if (alive.current && scopeGeneration === generation.current) setBusy(false); props.release(); }
  }
  async function retry() {
    if (!progress || busy || !props.acquire()) return;
    setBusy(true); setError("");
    try { await retryMemoryConsolidation(worldId, subjectId, progress.request_id, crypto.randomUUID()); }
    catch { if (alive.current) setError("재시도를 요청하지 못했어요. 저장된 설정을 확인해 주세요."); }
    finally { if (alive.current) setBusy(false); props.release(); }
  }
  const running = progress !== null && workflowActive(progress);
  return <div>
    <p>{props.subjectName}의 현재까지 쌓인 경험을 정리합니다. {relationshipCapable ? "기억이 이미 정리돼 있으면 남은 관계 정리를 이어갑니다. " : ""}저장한 기억 정리 모델을 사용하며 AI 이용 비용이 발생할 수 있습니다.</p>
    <Button disabled={props.disabled || props.dirty || running || !capabilityReady} loading={busy} loadingLabel="요청 중" onClick={() => void start()}>{relationshipCapable ? "지금 기억·관계 정리" : "지금 기억 정리"}</Button>
    {capabilityReason === "owner_controlled_memory_only" ? <p>사용자 캐릭터는 기억만 정리합니다. 관계 유형과 인식은 AI가 대신 판단하지 않아요.</p> : null}
    {capabilityReason === "unsupported" ? <p>현재 서버는 기억 정리만 지원합니다. 관계 통합 정리는 앱 업데이트 후 사용할 수 있어요.</p> : null}
    {props.dirty ? <p>변경한 설정을 먼저 저장해 주세요.</p> : null}
    {progress ? <p role="status">{progress.flow_state ? flowLabels[progress.flow_state] : labels[progress.state]}{progress.state === "completed" ? ` · 새 기억 ${progress.saved_count}개` : ""}
      {progress.state === "partial_failed" ? ` · 저장한 기억 ${progress.saved_count}개 · 남은 경험 ${progress.remaining_count}개` : ""}</p> : null}
    {progress?.relationship?.target_count !== null && progress?.relationship ? <p>관계 {progress.relationship.completed_count} / {progress.relationship.target_count}개 검토 완료 · 유지 {progress.relationship.kept_count}개 · 갱신 판단 {progress.relationship.changed_count}개</p> : null}
    {(progress?.relationship?.excluded_memory_count ?? 0) > 0 ? <p>검토 중 사용할 수 없게 된 기억 {progress?.relationship?.excluded_memory_count}개는 제외했습니다. 기존 관계는 보존됩니다.</p> : null}
    {progress?.flow_state === "completed" && progress.relationship?.projection_pending ? <p>관계 저장은 완료됐습니다. 관계도 반영을 기다리고 있어요.</p> : null}
    {progress?.relationship?.next_attempt_at ? <p>자동 재시도 예정: {new Date(progress.relationship.next_attempt_at).toLocaleString("ko-KR", { timeZone: props.timezone })} ({props.timezone}). 다시 시도해도 API 대기 시간은 유지됩니다.</p> : null}
    {progress?.last_code === "memory_capacity_reached" ? <p role="alert">기억 저장 한도에 도달해 새 기억 정리를 멈췄습니다. 저장 공간을 확보한 뒤 남은 정리를 다시 시도해 주세요.</p> : null}
    {progress?.followup && ["memory_failed", "relationship_retry_needed", "relationship_paused"].includes(progress.flow_state ?? "") ? <Button variant="secondary" disabled={props.disabled || props.dirty || busy} onClick={() => void retry()}>남은 정리 다시 시도</Button> : null}
    {readError || error ? <p role="alert">{readError || error}</p> : null}
  </div>;
}
