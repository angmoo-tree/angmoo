"use client";
import { useCallback } from "react";
import { Button } from "@/components/ui/button";
import { useUiText } from "@/hooks/use-ui-text";
import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import { useRuntimeBack } from "@/hooks/use-runtime-navigation";
import { getStudioWorldCharacters } from "@/features/creator-studio/api/studio-world-character-client";
import { studioWorldRoute } from "@/lib/navigation/product-routes";
import { WorldCharacterBasicSettings } from "./world-character-basic-settings";
export function WorldCharacterAutonomySetupClient({ characterId, worldId }: {
    characterId: string;
    worldId: string;
}) {
    const t = useUiText("shell"), back = useRuntimeBack(studioWorldRoute(worldId));
    const load = useCallback(async (signal: AbortSignal) => {
        // Studio's owned list supports unpublished Worlds without widening the
        // published entry/Chat/graph authorization gates.
        const list = await getStudioWorldCharacters(worldId, { signal });
        const value = list.items.find(item => item.character_id === characterId && item.control_mode === "autonomous" && ["active", "pending", "inactive"].includes(item.status));
        if (list.world_id !== worldId || !value)
            throw new Error("activity_settings_scope_invalid");
        return value;
    }, [worldId, characterId]);
    const { data, error, refresh } = useActiveScopedRead({ scopeKey: `${worldId}:${characterId}`, active: true, read: load });
    return <section className="grid min-w-0 gap-6 px-4 py-6 md:px-9">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">{t("활동 설정")}</h1><Button variant="ghost" onClick={back}>{t("돌아가기")}</Button></header>
    {data ? <WorldCharacterBasicSettings key={data.world_character_id} worldId={worldId} actorId={data.world_character_id}/> : <p role="status">{t("설정 확인 중")}</p>}
    {error ? <><p role="alert">{t("활동 설정을 불러오지 못했어요.")}</p><Button variant="secondary" onClick={refresh}>{t("다시 시도")}</Button></> : null}
  </section>;
}
