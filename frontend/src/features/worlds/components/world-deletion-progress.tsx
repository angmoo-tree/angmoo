"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { useUiText } from "@/hooks/use-ui-text";
import { getWorldDeletion, listWorldDeletions, retryWorldDeletion } from "../api/world-deletion";
import type { WorldDeletionReceipt } from "../types/world-deletion";

export function WorldDeletionProgress({ initial, onCompleted }: { initial: WorldDeletionReceipt; onCompleted?: () => void }) {
  const identity = useAuthRuntimeIdentity(initial.request_id);
  return <ScopedProgress key={identity} initial={initial} onCompleted={onCompleted} />;
}

function ScopedProgress({ initial, onCompleted }: { initial: WorldDeletionReceipt; onCompleted?: () => void }) {
  const text = useUiText("worlds");
  const [receipt, setReceipt] = useState(initial);
  const [unavailable, setUnavailable] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [revision, setRevision] = useState(0);
  const request = useRef<AbortController | null>(null);
  const completed = useRef(false);
  useEffect(() => {
    const abort = new AbortController(); request.current = abort;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const value = await getWorldDeletion(initial.request_id, abort.signal);
        if (abort.signal.aborted) return;
        setReceipt(value); setUnavailable(false);
        if (value.state === "completed" && !completed.current) { completed.current = true; onCompleted?.(); }
        if (value.state === "completed" || value.state === "failed") return;
      } catch { if (abort.signal.aborted) return; setUnavailable(true); }
      timer = setTimeout(() => void poll(), 2_000);
    }
    void poll();
    return () => { abort.abort(); if (timer) clearTimeout(timer); };
  }, [initial.request_id, onCompleted, revision]);
  async function retry() {
    if (!receipt.can_retry || retrying) return;
    const abort = new AbortController(); request.current?.abort(); request.current = abort; setRetrying(true);
    try { const value = await retryWorldDeletion(receipt.request_id, abort.signal); if (!abort.signal.aborted) { setReceipt(value); setRevision(value => value + 1); } }
    catch { if (!abort.signal.aborted) { setUnavailable(true); setRevision(value => value + 1); } }
    finally { if (!abort.signal.aborted) setRetrying(false); }
  }
  return <section aria-live="polite">
    <p role="status">{text(unavailable ? "삭제 상태를 확인하지 못했어요." : receipt.state === "completed" ? "World를 삭제했어요." : receipt.state === "failed" ? "삭제를 마치지 못했어요. 정리를 다시 시도해주세요." : "World 삭제 중…")}</p>
    {receipt.can_retry && !unavailable ? <Button variant="secondary" loading={retrying} onClick={() => void retry()}>{text("삭제 다시 시도")}</Button> : null}
  </section>;
}

export function WorldDeletionProgressList({ revision = 0, onCompleted }: { revision?: number; onCompleted?: () => void }) {
  const identity = useAuthRuntimeIdentity("world-deletions");
  return <ScopedProgressList key={identity} revision={revision} onCompleted={onCompleted} />;
}

function ScopedProgressList({ revision = 0, onCompleted }: { revision?: number; onCompleted?: () => void }) {
  const text = useUiText("worlds");
  const [items, setItems] = useState<WorldDeletionReceipt[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    listWorldDeletions(abort.signal).then(value => { if (!abort.signal.aborted) {
      setItems(current => [...value, ...current.filter(item => !value.some(next => next.request_id === item.request_id))]);
      setUnavailable(false);
    } })
      .catch(() => { if (!abort.signal.aborted) setUnavailable(true); });
    return () => abort.abort();
  }, [revision]);
  return <>{unavailable ? <p role="status">{text("삭제 상태를 확인하지 못했어요.")}</p> : null}
    {items.map(item => <WorldDeletionProgress key={item.request_id} initial={item} onCompleted={onCompleted} />)}</>;
}
