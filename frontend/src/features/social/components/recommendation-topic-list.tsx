"use client";
import { useId, useState } from "react";
import { IconButton } from "@/components/ui/button";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useUiText } from "@/hooks/use-ui-text";
import type { RecommendationTopics } from "../api/recommendation-topics";
export const TOPIC_STATES = { pending: "주제 준비 전", running: "주제 만드는 중", ready: "주제 준비됨", failed: "주제 생성 실패 · 이전 결과 유지", stale: "설정 변경됨 · 기존 주제 사용 중" };

export function RecommendationTopicList({ topics, maxVisible }: { topics: RecommendationTopics["topics"]; maxVisible?: number }) {
  const t = useUiText("social"), id = useId(), [expanded, setExpanded] = useState(false);
  const remaining = maxVisible === undefined ? 0 : Math.max(0, topics.length - maxVisible);
  const visible = expanded || maxVisible === undefined ? topics : topics.slice(0, maxVisible);
  return <>
    <ul id={id} className="flex min-w-0 flex-wrap gap-2" aria-label={t("현재 주제 목록")}>{visible.map(topic => <li key={topic.id} className="max-w-full break-words rounded-full bg-surface-muted px-3 py-1 text-sm text-text-default">{topic.name}</li>)}</ul>
    {!topics.length ? <p className="text-sm text-text-secondary">{t("등록된 주제가 없습니다.")}</p> : null}
    {remaining > 0 ? <IconButton variant="ghost" label={t(expanded ? "주제 접기" : "주제 펼치기")} aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded(value => !value)}>{expanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}</IconButton> : null}
  </>;
}
