import type { EpisodeDetailRead } from "../types/memory-contract";

const statusLabel = { missing: "원문이 없습니다.", changed: "원문이 변경되어 이전 내용을 표시하지 않습니다.", unavailable: "현재 확인할 수 없는 원문입니다." };
const roleLabel: Record<string, string> = { user: "사용자 발언", assistant: "캐릭터 응답", parent: "앞선 글", self: "내 활동", observed: "확인한 활동" };

export function EpisodeMemoryDetail({ episode }: { episode: EpisodeDetailRead }) {
  return <section aria-label="상황에 연결된 원문과 생각">
    <h3>{episode.representation === "episode_v1" ? "상황에 연결된 원문과 생각" : "기존 기억에 연결된 자료"}</h3>
    {episode.partial && <p>일부 자료만 표시합니다. 확인하지 못한 자료까지 확인된 것으로 볼 수는 없습니다.</p>}
    {episode.omitted_units > 0 && <p>표시 분량을 넘어 생략한 자료 묶음: {episode.omitted_units}개</p>}
    {episode.followup_count > 0 && <p>이 경험은 이전 기억 {episode.followup_count}개에서 이어졌습니다.</p>}
    <ol>{episode.units.map((unit, index) => <li key={index}>
      {unit.sources.map((source, offset) => <p key={offset}><strong>{roleLabel[source.role] ?? "원문"}: </strong>{source.status === "verified" ? source.text : statusLabel[source.status]}</p>)}
      {unit.thought && <p><strong>생각: </strong>{unit.thought.status === "recorded" ? unit.thought.text : unit.thought.status === "invalid" ? "연결된 생각을 현재 확인할 수 없습니다." : "기록하지 않았습니다."}{unit.thought.truncated && " (길이 제한으로 일부만 저장됨)"}</p>}
      {unit.legacy_declaration && <p><strong>과거 형식의 자기 관점: </strong>{unit.legacy_declaration}</p>}
    </li>)}</ol>
  </section>;
}
