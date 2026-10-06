"use client";

import { useUiText } from "@/hooks/use-ui-text";
import type { EpisodeDetailRead } from "../types/memory-contract";

const statusLabel = { missing: "원문이 없습니다.", changed: "원문이 변경되어 이전 내용을 표시하지 않습니다.", unavailable: "현재 확인할 수 없는 원문입니다." };
const roleLabel: Record<string, string> = { user: "사용자 발언", assistant: "캐릭터 응답", parent: "앞선 글", self: "내 활동", observed: "확인한 활동" };

export function EpisodeMemoryDetail({ episode }: { episode: EpisodeDetailRead }) {
  const uiText = useUiText("memory");
  return <section aria-label={uiText("상황에 연결된 원문과 생각")}>
    <h3>{episode.representation === "episode_v1" ? uiText("상황에 연결된 원문과 생각") : uiText("기존 기억에 연결된 자료")}</h3>
    {episode.partial && <p>{uiText("일부 자료만 표시합니다. 확인하지 못한 자료까지 확인된 것으로 볼 수는 없습니다.")}</p>}
    {episode.omitted_units > 0 && <p>{uiText("표시 분량을 넘어 생략한 자료 묶음: {{count}}개", {count: episode.omitted_units})}</p>}
    {episode.followup_count > 0 && <p>{uiText("이 경험은 이전 기억 {{count}}개에서 이어졌습니다.", {count: episode.followup_count})}</p>}
    <ol>{episode.units.map((unit, index) => <li key={index}>
      {unit.sources.map((source, offset) => <p key={offset}><strong>{uiText(roleLabel[source.role] ?? uiText("원문"))}: </strong>{source.status === "verified" ? source.text : uiText(statusLabel[source.status])}</p>)}
      {unit.thought && <p><strong>{uiText("생각:")}</strong>{unit.thought.status === "recorded" ? unit.thought.text : unit.thought.status === "invalid" ? uiText("연결된 생각을 현재 확인할 수 없습니다.") : uiText("기록하지 않았습니다.")}{unit.thought.truncated && uiText("(길이 제한으로 일부만 저장됨)")}</p>}
      {unit.legacy_declaration && <p><strong>{uiText("과거 형식의 자기 관점:")}</strong>{unit.legacy_declaration}</p>}
    </li>)}</ol>
  </section>;
}
