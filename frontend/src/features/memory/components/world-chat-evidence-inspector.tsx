"use client";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";

import { useUiText } from "@/hooks/use-ui-text";


import { ExternalLink, LoaderCircle, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { LocalProductLink } from "@/components/navigation/local-product-link";
import { Dialog } from "@/components/ui/dialog";

import { getWorldChatEvidence } from "@/features/memory/api/memory-client";
import type { WorldChatEvidenceRead } from "@/features/memory/types/memory-contract";
import styles from "./memory-workspace.module.css";
import { EpisodeMemoryDetail } from "./episode-memory-detail";

export function WorldChatEvidenceInspector({ open, onOpenChange, requestId, threadId, worldId }: { open: boolean; onOpenChange: (open: boolean) => void; requestId: string | null; threadId: string; worldId: string }) {
  const uiText = useUiText("memory");
  return <Dialog description={uiText("답변 전에 고정되었고, 지금 다시 확인한 근거만 표시합니다.")} dialogAttributes={{ "data-world-chat-evidence-dialog": "true" }} onOpenChange={onOpenChange} open={open} title={uiText("이 답변의 근거")}>
    <EvidenceInspectorContent key={`${worldId}:${threadId}:${requestId}:${open}`} open={open} requestId={requestId} threadId={threadId} worldId={worldId} />
  </Dialog>;
}

function EvidenceInspectorContent({ open, requestId, threadId, worldId }: { open: boolean; requestId: string | null; threadId: string; worldId: string }) {
  const formatDate = useUiDateFormatter();
  const uiText = useUiText("memory");
  const [read, setRead] = useState<WorldChatEvidenceRead | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => {
    if (!open || !requestId) return;
    const controller = new AbortController();
    void getWorldChatEvidence(worldId, threadId, requestId, { signal: controller.signal })
      .then((value) => { if (!controller.signal.aborted) { setRead(value); setState("ready"); } })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setState("error");
      });
    return () => controller.abort();
  }, [open, requestId, threadId, worldId]);
  return (
    <>
      {state === "loading" ? <div className={styles.dialogState}><LoaderCircle aria-hidden="true" className={styles.spin} /><p>{uiText("근거를 확인하는 중")}</p></div> : null}
      {state === "error" ? <div className={styles.dialogState} role="alert"><p>{uiText("근거를 불러오지 못했어요.")}</p></div> : null}
      {state === "ready" && read ? (
        <div className={styles.chatEvidence}>
          {read.capability === "degraded" ? <p className={styles.degradedNotice}>{uiText("일부 검색 축을 사용할 수 없어 확인된 근거만 표시합니다.")}</p> : null}
          {(read.current_context?.length ?? 0) > 0 ? <section aria-label={uiText("답변에 사용한 사회적 맥락")}>
            <h3>{uiText("답변에 사용한 사회적 맥락")}</h3>
            <p>{uiText("답변 당시 선택된 나의 관계입니다. 전체 관계 목록이나 과거 사건의 기록은 아닙니다. 이후 바뀌었거나 확인할 수 없는 관계는 내용을 표시하지 않습니다.")}</p>
            <ol>{read.current_context?.map((item) => <li key={item.reference} data-availability={item.availability}>
              <div><ShieldCheck aria-hidden="true" size={17} /><strong>{item.related_character ?? uiText("현재 관계")}</strong><span>{item.availability === "available" ? uiText("현재도 확인됨") : uiText("변경되었거나 확인 불가")}</span></div>
              {item.occurred_at ? <time dateTime={item.occurred_at}>{formatDate(item.occurred_at)}</time> : null}
              {item.excerpt ? <p>{item.excerpt}</p> : null}
            </li>)}</ol>
          </section> : null}
          {read.items.length === 0 && !read.current_context?.length ? <p>{uiText("현재 표시할 수 있는 근거가 없습니다.")}</p> : (
            <ol>
              {read.items.map((item) => (
                <li key={item.reference} data-availability={item.availability}>
                  <div><ShieldCheck aria-hidden="true" size={17} /><strong>{item.label}</strong><span>{item.availability === "available" ? uiText("확인됨") : item.availability === "deleted" ? uiText("삭제됨") : uiText("확인 불가")}</span></div>
                  {item.occurred_at ? <time dateTime={item.occurred_at}>{formatDate(item.occurred_at)}</time> : null}
                  {item.excerpt ? <p>{item.excerpt}</p> : null}
                  {item.episode && <EpisodeMemoryDetail episode={item.episode} />}
                  {item.related_character ? <small>{item.direction === "outgoing" ? "→" : item.direction === "incoming" ? "←" : "·"} {item.related_character}</small> : null}
                  {item.canonical_href ? <LocalProductLink ariaLabel={uiText("근거 원문 열기")} className={styles.sourceLink} href={item.canonical_href}>{uiText("원문 열기")}<ExternalLink aria-hidden="true" size={15} /></LocalProductLink> : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </>
  );
}
