"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form-controls";
import { InlineError } from "@/components/ui/feedback";
import { FeedStatusPanel } from "@/features/social/components/feed-status";
import { RecommendationHistory } from "@/features/social/components/recommendation-history";
import { connectRecommendationKey, readRecommendationTopics, regenerateRecommendationTopics, type RecommendationTopics } from "@/features/social/api/recommendation-topics";

export type TopicCharacterChoice = { id: string; name: string };
const labels = { pending: "주제 준비 필요", running: "주제 만드는 중", ready: "준비됨", failed: "주제 생성 실패 · 이전 결과 유지", stale: "저장된 설정으로 갱신 필요" };

// LOCAL: existing semantic form/button primitives; shared by Next and static screens.
export function RecommendationTopicsPanel({ worldId, characterId, characters = [] }: {
  worldId: string; characterId?: string; characters?: TopicCharacterChoice[];
}) {
  const [data, setData] = useState<RecommendationTopics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [readError, setReadError] = useState<{ scope: string; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [keyId, setKeyId] = useState("");
  const [reload, setReload] = useState(0);
  const request = useRef<string | null>(null);
  const activeScope = useRef(`${worldId}:${characterId ?? "world"}`);
  useEffect(() => {
    activeScope.current = `${worldId}:${characterId ?? "world"}`;
    return () => { activeScope.current = "unmounted"; };
  }, [worldId, characterId]);
  useEffect(() => {
    const controller = new AbortController();
    readRecommendationTopics(worldId, characterId, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      setData(result); setKeyId(result.key_world_character_id ?? ""); setError(null); setReadError(null);
    }).catch(() => { if (!controller.signal.aborted) setReadError({ scope: `${worldId}:${characterId ?? "world"}`, message: "추천 주제와 전달 이력을 불러오지 못했습니다. 접근 권한을 확인한 뒤 상태 새로고침을 눌러 주세요." }); });
    return () => controller.abort();
  }, [worldId, characterId, reload]);

  async function mutate(action: "generate" | "key") {
    if (request.current) return;
    const scope = activeScope.current;
    request.current = crypto.randomUUID();
    setBusy(true); setError(null);
    try {
      const result = action === "key"
        ? await connectRecommendationKey(worldId, keyId || null)
        : await regenerateRecommendationTopics(worldId, request.current, characterId);
      if (activeScope.current === scope) setData(result);
    } catch {
      if (activeScope.current === scope) setError("처리하지 못했습니다. 일과 생성용 Google API 키와 승인된 프로필을 확인한 뒤 다시 시도해 주세요.");
    } finally {
      request.current = null;
      if (activeScope.current === scope) setBusy(false);
    }
  }
  const current = data?.world_id === worldId && data?.world_character_id === (characterId ?? null) ? data : null;
  const currentReadError = readError?.scope === `${worldId}:${characterId ?? "world"}` ? readError.message : undefined;
  return <section className="space-y-4 rounded-2xl border border-border-default bg-surface p-5" aria-busy={busy}>
    <h3 className="font-bold text-text-strong">{characterId ? "캐릭터 관심 주제" : "World 추천 주제"}</h3>
    <p className="text-sm text-text-secondary">저장한 설정을 바탕으로 주제를 준비합니다. 설정을 수정한 뒤에는 다시 만들기를 눌러 갱신해 주세요.</p>
    <p role="status" className="text-sm text-text-default">{current ? labels[current.state] : "주제 확인 중"}</p>
    {current && <ul className="flex flex-wrap gap-2" aria-label="현재 주제 목록">{current.topics.map(topic => <li key={topic.id} className="rounded-full bg-surface-muted px-3 py-1 text-sm text-text-default">{topic.name}</li>)}</ul>}
    {current && current.topics.length === 0 && <p className="text-sm text-text-secondary">등록된 주제가 없습니다.</p>}
    {current?.approval_required && <p className="text-sm text-text-secondary">먼저 이 World의 캐릭터 프로필을 승인해 주세요.</p>}
    {!characterId && <div className="space-y-2">
      <Field label="주제 생성에 사용할 캐릭터의 일과 생성 키">{props => <Select {...props} value={keyId} onChange={event => setKeyId(event.target.value)} disabled={busy}>
        <option value="">연결하지 않음</option>{characters.map(character => <option key={character.id} value={character.id}>{character.name}</option>)}
      </Select>}</Field>
      <Button variant="secondary" disabled={busy || !current} onClick={() => void mutate("key")}>키 연결 저장</Button>
    </div>}
    {current && <p className="text-xs text-text-secondary">{current.model} · thinking {current.thinking_level}{characterId ? " · 이 캐릭터의 일과 생성 키 사용" : ""}</p>}
    {error && <InlineError>{error}</InlineError>}
    {currentReadError && <InlineError>{currentReadError}</InlineError>}
    <div className="flex flex-wrap gap-2">
      <Button loading={busy} disabled={!current || current.approval_required || (!characterId && !current.key_world_character_id)} onClick={() => void mutate("generate")}>{characterId ? "캐릭터 주제 다시 만들기" : "World 주제 다시 만들기"}</Button>
      <Button variant="ghost" disabled={busy} onClick={() => { setData(null); setReadError(null); setReload(value => value + 1); }}>상태 새로고침</Button>
    </div>
    {characterId && current && !currentReadError && <FeedStatusPanel status={current.feed_status} />}
    {characterId && <RecommendationHistory deliveries={current?.recent_deliveries} loading={!current} error={currentReadError} />}
  </section>;
}
