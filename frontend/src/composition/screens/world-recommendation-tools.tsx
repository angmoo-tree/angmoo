"use client";
import { useEffect, useState } from "react";
import { getStudioWorldCharacters } from "@/features/creator-studio/api/studio-world-character-client";
import { RecommendationTopicsPanel, type TopicCharacterChoice } from "@/features/social/components/recommendation-topics-panel";
import { Field, Select } from "@/components/ui/form-controls";

export function WorldRecommendationTools({ worldId }: { worldId: string }) {
  const [characters, setCharacters] = useState<TopicCharacterChoice[]>([]);
  const [selected, setSelected] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    getStudioWorldCharacters(worldId, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) setCharacters(result.items.filter(item => item.control_mode === "autonomous" && ["pending", "active", "inactive"].includes(item.status)).map(item => ({ id: item.world_character_id, name: item.display_name })));
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [worldId]);
  return <section className="space-y-4" aria-label="추천 주제 설정">
    <RecommendationTopicsPanel key={worldId} worldId={worldId} characters={characters} />
    {failed && <p role="alert" className="text-state-danger">캐릭터 목록을 불러오지 못했습니다.</p>}
    <Field label="관심 주제를 확인할 캐릭터">{props => <Select {...props} value={selected} onChange={event => setSelected(event.target.value)}>
      <option value="">캐릭터 선택</option>{characters.map(character => <option key={character.id} value={character.id}>{character.name}</option>)}
    </Select>}</Field>
    {selected && <RecommendationTopicsPanel key={selected} worldId={worldId} characterId={selected} />}
  </section>;
}
