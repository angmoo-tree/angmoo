"use client";

import { ExternalLink, LoaderCircle, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { LocalProductLink } from "@/features/device-shell/public";
import { Dialog } from "@/shared/ui/public";

import { getWorldChatEvidence } from "../api/memory-client";
import type { WorldChatEvidenceRead } from "../model/memory-contract";
import styles from "./memory-workspace.module.css";

export function WorldChatEvidenceInspector({ open, onOpenChange, requestId, threadId, worldId }: { open: boolean; onOpenChange: (open: boolean) => void; requestId: string | null; threadId: string; worldId: string }) {
  const [read, setRead] = useState<WorldChatEvidenceRead | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => {
    if (!open || !requestId) return;
    const controller = new AbortController();
    void getWorldChatEvidence(worldId, threadId, requestId, { signal: controller.signal })
      .then((value) => { setRead(value); setState("ready"); })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setState("error");
      });
    return () => controller.abort();
  }, [open, requestId, threadId, worldId]);
  return (
    <Dialog description="답변 전에 고정되었고, 지금 다시 확인한 근거만 표시합니다." dialogAttributes={{ "data-world-chat-evidence-dialog": "true" }} onOpenChange={onOpenChange} open={open} title="이 답변의 근거">
      {state === "loading" ? <div className={styles.dialogState}><LoaderCircle aria-hidden="true" className={styles.spin} /><p>근거를 확인하는 중</p></div> : null}
      {state === "error" ? <div className={styles.dialogState} role="alert"><p>근거를 불러오지 못했어요.</p></div> : null}
      {state === "ready" && read ? (
        <div className={styles.chatEvidence}>
          {read.capability === "degraded" ? <p className={styles.degradedNotice}>일부 검색 축을 사용할 수 없어 확인된 근거만 표시합니다.</p> : null}
          {read.items.length === 0 ? <p>현재 표시할 수 있는 근거가 없습니다.</p> : (
            <ol>
              {read.items.map((item) => (
                <li key={item.reference} data-availability={item.availability}>
                  <div><ShieldCheck aria-hidden="true" size={17} /><strong>{item.label}</strong><span>{item.availability === "available" ? "확인됨" : item.availability === "deleted" ? "삭제됨" : "확인 불가"}</span></div>
                  {item.occurred_at ? <time dateTime={item.occurred_at}>{new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.occurred_at))}</time> : null}
                  {item.excerpt ? <p>{item.excerpt}</p> : null}
                  {item.related_character ? <small>{item.direction === "outgoing" ? "→" : item.direction === "incoming" ? "←" : "·"} {item.related_character}</small> : null}
                  {item.canonical_href ? <LocalProductLink ariaLabel="근거 원문 열기" className={styles.sourceLink} href={item.canonical_href}>원문 열기 <ExternalLink aria-hidden="true" size={15} /></LocalProductLink> : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </Dialog>
  );
}
