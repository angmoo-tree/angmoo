"use client";
import { useCallback, useState } from "react";
import { Tags } from "lucide-react";
import { SettingsCard } from "@/components/ui/settings-card";
import { Button } from "@/components/ui/button";
import { useUiText } from "@/hooks/use-ui-text";
import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { readRecommendationTopics, regenerateRecommendationTopics } from "../api/recommendation-topics";
import { RecommendationTopicList, TOPIC_STATES } from "./recommendation-topic-list";
export function RecommendationTopicsPanel({ worldId, characterId, elevated = false }: {
    worldId: string;
    characterId: string;
    elevated?: boolean;
}) {
    const t = useUiText("social"), [busy, setBusy] = useState(false), [failed, setFailed] = useState(false);
    const load = useCallback(async (signal: AbortSignal) => { const value = await readRecommendationTopics(worldId, characterId, signal); if (value.world_id !== worldId || value.world_character_id !== characterId)
        throw new Error("topics_scope_invalid"); return value; }, [worldId, characterId]);
    const { data, error, refresh } = useActiveScopedRead({ scopeKey: `${worldId}:${characterId}`, active: true, read: load });
    async function generate() {
        if (busy)
            return;
        const auth = captureAuthRequestScope();
        setBusy(true);
        setFailed(false);
        try {
            await regenerateRecommendationTopics(worldId, crypto.randomUUID(), characterId);
            if (isCurrentAuthRequestScope(auth))
                refresh();
        }
        catch {
            if (isCurrentAuthRequestScope(auth))
                setFailed(true);
        }
        finally {
            if (isCurrentAuthRequestScope(auth))
                setBusy(false);
        }
    }
    return <SettingsCard elevated={elevated} title={t("캐릭터 관심 주제")} description={t("저장한 설정을 바탕으로 주제를 준비합니다. 설정을 수정한 뒤에는 다시 만들기를 눌러 갱신해 주세요.")} icon={<Tags size={20}/>}>
    <p role="status">{t(data ? TOPIC_STATES[data.state] ?? "확인 필요" : "주제 확인 중")}</p>
    {data ? <><RecommendationTopicList topics={data.topics}/><p>{data.model} · thinking {data.thinking_level} {t("· 이 캐릭터의 일과 생성 키 사용")}</p>{data.approval_required ? <p>{t("먼저 이 World의 캐릭터 프로필을 승인해 주세요.")}</p> : null}</> : null}
    {failed || error ? <p role="alert">{t("처리하지 못했습니다. 활동용 Google API 키와 캐릭터 설정을 확인한 뒤 다시 시도해 주세요.")}</p> : null}
    <div className="flex flex-wrap gap-2"><Button loading={busy} disabled={!data || data.approval_required} onClick={() => void generate()}>{t("캐릭터 주제 다시 만들기")}</Button><Button variant="ghost" disabled={busy} onClick={refresh}>{t("상태 새로고침")}</Button></div>
  </SettingsCard>;
}
