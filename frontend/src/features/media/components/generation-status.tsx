"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { getGenerationJob, changeGenerationJob } from "../api/media-client";
import type { GenerationJob } from "../types/media";
import styles from "./media-settings.module.css";

const labels: Record<string, string> = { queued: "이미지 생성 대기", running: "이미지 생성 중", result_pending: "받은 이미지 저장 복구 중", result_ready: "이미지 저장 중", succeeded: "이미지 생성 완료", failed: "이미지 생성 실패", outcome_unknown: "생성 결과 확인 필요", cancelled: "이미지 생성 취소", skipped: "이미지 생성 생략", blocked: "이미지 생성 준비 필요" };
export function GenerationStatus({ worldId, postId, onCompleted }: { worldId: string; postId: string; onCompleted?: () => void }) {
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const completed = useRef<string | number | null>(null);
  const completionCallback = useRef(onCompleted);
  useEffect(() => { completionCallback.current = onCompleted; }, [onCompleted]);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    async function read() {
      try {
        const next = await getGenerationJob(worldId, postId, controller.signal);
        if (!controller.signal.aborted) {
          setJob(next);
          if (next?.status === "succeeded" && next.job_id !== completed.current) {
            completed.current = next.job_id;
            completionCallback.current?.();
          }
          if (next && ["queued", "running", "result_pending", "result_ready"].includes(next.status)) timer = setTimeout(() => void read(), 3000);
        }
      }
      catch { /* Feed remains usable when optional generation status is unavailable. */ }
    }
    void read(); return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [worldId, postId, busy]);
  async function change(action: "cancel" | "retry") {
    setBusy(true); setError(null);
    try { setJob(await changeGenerationJob(worldId, postId, action)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "이미지 작업을 변경하지 못했습니다."); }
    finally { setBusy(false); }
  }
  if (!job || job.status === "succeeded") return null;
  return <div className={styles.panel} aria-label="게시글 이미지 생성 상태"><p role="status">{labels[job.status] ?? job.status}</p>{job.reason ? <p className={styles.note}>{job.reason}</p> : null}
    {job.status === "outcome_unknown" || job.status === "result_pending" ? <p className={styles.note}>중복 비용을 막기 위해 새 생성 요청을 보내지 않습니다. 저장된 결과나 조회 가능한 작업 ID로 같은 결과를 복구합니다.</p> : null}
    <div className={styles.actions}>{job.cancellable ? <Button variant="ghost" disabled={busy} onClick={() => void change("cancel")}>이미지 생성 취소</Button> : null}{job.retryable ? <Button disabled={busy} onClick={() => void change("retry")}>{["outcome_unknown", "result_pending", "result_ready"].includes(job.status) ? "기존 결과 확인" : "이미지 생성 다시 시도"}</Button> : null}</div>{error ? <InlineError>{error}</InlineError> : null}
  </div>;
}
