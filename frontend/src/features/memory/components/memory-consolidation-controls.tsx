"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { getMemoryConsolidation, startMemoryConsolidation, MemoryApiError } from "@/features/memory/api/memory-client";
import { consolidationActive, type ConsolidationProgress, type ConsolidationStart } from "@/features/memory/types/consolidation-contract";

const labels: Record<ConsolidationProgress["state"], string> = {
  preparing: "정리할 경험을 확인하고 있어요", queued: "기억 정리를 기다리고 있어요",
  waiting_for_chat: "채팅이 끝나면 기억 정리를 시작해요", ai_running: "AI가 경험을 읽고 기억을 정리하고 있어요",
  applying: "정리한 기억을 저장하고 있어요", completed: "기억 정리를 마쳤어요",
  no_work: "새로 정리할 경험이 없어요", partial_failed: "일부 경험을 정리하지 못했어요",
  failed: "기억 정리를 마치지 못했어요. 실패한 정리 다시 시도를 이용해 주세요.",
  paused: "설정이 바뀌어 기억 정리를 멈췄어요", cancelled: "기억 정리가 취소됐어요",
};
type Props = {
  worldId: string; subjectId: string; subjectName: string; disabled: boolean; dirty: boolean;
  version: number; profileVersion: number; scopeVersion: number;
  acquire: () => boolean; release: () => void; onCompleted: () => void;
};

export function MemoryConsolidationControls(props: Props) {
  const { worldId, subjectId, onCompleted } = props;
  const [progress, setProgress] = useState<ConsolidationProgress | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<ConsolidationStart | null>(null);
  const alive = useRef(false);
  const generation = useRef(0);
  const finished = useRef<string | null>(null);
  const accepted = useRef<string | null>(null);
  useEffect(() => {
    alive.current = true;
    const scopeGeneration = ++generation.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      let interval = 5_000;
      const acceptedBefore = accepted.current;
      try {
        const value = await getMemoryConsolidation(worldId, subjectId, controller.signal);
        if (controller.signal.aborted || scopeGeneration !== generation.current || acceptedBefore !== accepted.current) return;
        setProgress(value);
        if (value && consolidationActive(value.state)) interval = document.hidden ? 5_000 : 1_000;
        if (value && ["completed", "partial_failed"].includes(value.state) && finished.current !== value.request_id) {
          finished.current = value.request_id; onCompleted();
        }
      } catch {
        if (!controller.signal.aborted) setError("정리 상태를 확인하지 못했어요. 잠시 후 다시 확인합니다.");
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
      expected_profile_version: props.profileVersion, expected_scope_version: props.scopeVersion };
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
  const running = progress !== null && consolidationActive(progress.state);
  return <div>
    <p>{props.subjectName}의 현재까지 쌓인 경험을 정리합니다. 저장한 기억 정리 모델을 사용하며 AI 이용 비용이 발생할 수 있습니다.</p>
    <Button disabled={props.disabled || props.dirty || running} loading={busy} loadingLabel="요청 중" onClick={() => void start()}>지금 기억 정리</Button>
    {props.dirty ? <p>변경한 설정을 먼저 저장해 주세요.</p> : null}
    {progress ? <p role="status">{labels[progress.state]}{progress.state === "completed" ? ` · 새 기억 ${progress.saved_count}개` : ""}
      {progress.state === "partial_failed" ? ` · 저장한 기억 ${progress.saved_count}개 · 남은 경험 ${progress.remaining_count}개` : ""}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
  </div>;
}
