"use client";
import { useCallback } from "react";
import { Tags } from "lucide-react";
import { SettingsCard } from "@/components/ui/settings-card";
import { Button } from "@/components/ui/button";
import { useUiText } from "@/hooks/use-ui-text";
import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import { readRecommendationTopics } from "../api/recommendation-topics";
import { RecommendationTopicList, TOPIC_STATES } from "./recommendation-topic-list";

export function RecommendationTopicsSummary({ worldId, actorId, active }: { worldId: string; actorId: string; active: boolean }) {
  const t = useUiText("social");
  const load = useCallback(async (signal: AbortSignal) => {
    const value = await readRecommendationTopics(worldId, actorId, signal);
    if (value.world_id !== worldId || value.world_character_id !== actorId) throw new Error("topics_scope_invalid");
    return value;
  }, [worldId, actorId]);
  const { data, loading, error, refresh } = useActiveScopedRead({ scopeKey: `${worldId}:${actorId}`, active, read: load });
  return <SettingsCard elevated iconTone="soft" title={t("캐릭터 관심 주제")} description={t("현재 관심 주제를 확인해요.")} icon={<Tags size={20} />}>
    {error ? <p role="alert">{t(data ? "최신 정보를 확인하지 못했어요." : "정보를 불러오지 못했어요.")}</p> : null}
    {loading && !data ? <p role="status">{t("불러오는 중…")}</p> : null}
    {data ? <><p role="status">{t(TOPIC_STATES[data.state] ?? "확인 필요")}</p><RecommendationTopicList topics={data.topics} maxVisible={6} /></> : null}
    {error ? <Button variant="secondary" onClick={refresh}>{t("다시 시도")}</Button> : null}
  </SettingsCard>;
}
