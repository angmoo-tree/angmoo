"use client";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { useUiText } from "@/hooks/use-ui-text";
import type { DailyActivityPlanRead } from "../api/world-activity-runtime";
import { DAYPARTS, PLAN_ITEM_STATES } from "../utils/daily-plan-presentation";

export function DailyPlanRows({ plan, compact = false, highlightCurrent = true }: { plan: DailyActivityPlanRead | null; compact?: boolean; highlightCurrent?: boolean }) {
  const t = useUiText("characters"), id = useId();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  return <ul className="grid min-w-0 gap-3">{DAYPARTS.map(([part, label, window]) => {
    const item = plan?.items.find(row => row.daypart === part), current = highlightCurrent && plan?.current_daypart === part;
    const detailId = `${id}-${part}`;
    return <li key={part} className={`min-w-0 rounded-xl p-4 ${current ? "bg-brand-soft" : "bg-surface-muted"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold">{t(label)} · {window}</h3>{current ? <span className="text-sm text-text-secondary">{t("현재 시간대")}</span> : null}</div>
      {item ? <><p className={`break-words ${compact ? "line-clamp-2" : ""}`}>{item.title}</p><p className="text-sm text-text-secondary">{t(PLAN_ITEM_STATES[item.status] ?? "확인 필요")}</p>
        {compact ? <><Button variant="ghost" aria-expanded={Boolean(expanded[part])} aria-controls={detailId} onClick={() => setExpanded(previous => ({ ...previous, [part]: !previous[part] }))}>{t(expanded[part] ? "접기" : "상세 보기")}</Button>
          <div id={detailId} hidden={!expanded[part]} className="min-w-0 whitespace-pre-wrap break-words"><p>{item.title}</p><p>{item.activity_seed}</p></div></> : <p className="whitespace-pre-wrap break-words text-text-secondary">{item.activity_seed}</p>}
      </> : <p className="text-text-secondary">{t("등록된 계획 없음")}</p>}
    </li>;
  })}</ul>;
}
