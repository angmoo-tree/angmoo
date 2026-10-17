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
import { evidenceWarnings, relationshipStatus, evidenceTimes } from "../utils/chat-evidence-presentation";
import type { WorldChatEvidenceItemRead } from "../types/memory-contract";

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
  const warnings = read ? evidenceWarnings(read) : null;
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
          {warnings?.retrieval ? <p className={styles.degradedNotice}>{uiText("답변 생성 당시 일부 검색이 제한됐어요. 전달된 근거 중 확인 가능한 내용을 표시해요.")}</p> : null}
          {warnings?.current ? <p className={styles.degradedNotice}>{uiText("일부 근거는 지금 확인하거나 표시할 수 없어요.")}</p> : null}
          {warnings?.legacy ? <p className={styles.degradedNotice}>{uiText("일부 근거의 상태를 확인할 수 없어요.")}</p> : null}
          {!read.current_context?.length && read.items.some((item) => item.kind === "graph_relationship") ? <p>{uiText("답변을 만들 때 전달한 관계 정보예요. 이후 관계가 바뀌어도 당시 확인된 내용을 표시하며, 전체 관계 목록이나 과거 사건 기록은 아니에요.")}</p> : null}
          {(read.current_context?.length ?? 0) > 0 ? <section aria-label={uiText("답변에 사용한 사회적 맥락")}>
            <h3>{uiText("답변에 사용한 사회적 맥락")}</h3>
            <p>{uiText("답변을 만들 때 전달한 관계 정보예요. 이후 관계가 바뀌어도 당시 확인된 내용을 표시하며, 전체 관계 목록이나 과거 사건 기록은 아니에요.")}</p>
            <ol>{read.current_context?.map((item) => <li key={item.reference} data-availability={item.availability}>
              <div><ShieldCheck aria-hidden="true" size={17} /><strong>{uiText("답변 당시 관계")}{item.related_character ? ` · ${item.related_character}` : ""}</strong><span>{uiText(relationshipStatus(item, read))}</span></div>
              {item.occurred_at ? <time dateTime={item.occurred_at}>{formatDate(item.occurred_at)}</time> : null}
              <RelationshipText item={item} />
            </li>)}</ol>
          </section> : null}
          {read.items.length === 0 && !read.current_context?.length ? <p>{uiText("현재 표시할 수 있는 근거가 없습니다.")}</p> : (
            <ol>
              {read.items.map((item) => (
                <li key={item.reference} data-availability={item.availability}>
                  <div><ShieldCheck aria-hidden="true" size={17} /><strong>{item.kind === "graph_relationship" ? uiText("답변 당시 관계") : item.label}</strong><span>{item.kind === "graph_relationship" ? uiText(relationshipStatus(item, read)) : item.availability === "available" ? uiText("확인됨") : item.availability === "deleted" ? uiText("삭제됨") : uiText("확인 불가")}</span></div>
                  {evidenceTimes(item).map(row => <small key={row.label}>{uiText(row.label)}{row.value ? <> · <time dateTime={row.value}>{formatDate(row.value)}</time></> : null}</small>)}
                  <RelationshipText item={item} />
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

function RelationshipText({ item }: { item: WorldChatEvidenceItemRead }) {
  const uiText = useUiText("memory");
  const value = item.relationship_projection;
  if (!value) return item.excerpt ? <p>{item.excerpt}</p> : null;
  return <>
    <p>{uiText("친숙도 {{familiarity}} · 호감 {{affinity}} · 신뢰 {{trust}} · 긴장 {{tension}} · 상호작용 {{interactions}}회", {
      familiarity: value.familiarity, affinity: value.affinity, trust: value.trust, tension: value.tension, interactions: value.interactions,
    })}</p>
    {value.relationship_label ? <p>{value.relationship_label}</p> : null}
    {value.perception ? <p>{value.perception}</p> : null}
  </>;
}
