"use client";

import { useCallback } from "react";
import { WorldCharacterManagement } from "@/features/characters/components/world-character-management";
import type { WorldCharacterManagementView } from "@/features/characters/types/world-character-management";
import { parseWorldCharacterManagementView } from "@/features/characters/utils/world-character-dashboard-presentation";
import { useRuntimeBack, useRuntimeRouter, useRuntimeSearchParams } from "@/hooks/use-runtime-navigation";
import { worldCharacterDirectoryRoute, worldCharacterProfileRoute } from "@/lib/navigation/product-routes";
import { WorldCharacterProfile } from "./world-character-profile-screen";
import { WorldImageGenerationCard, WorldVisionControls } from "@/features/media/components/world-image-policy-controls";
import { RecommendationTopicsPanel } from "@/features/social/components/recommendation-topics-panel";
import { PersonalizedActivityPanel } from "@/features/characters/components/personalized-activity-panel";
import { WorldDailyPlanCard } from "@/features/characters/components/world-daily-plan-card";
import { WorldCharacterDeletionCard } from "@/features/characters/components/world-character-deletion-card";

export function WorldCharacterManagementScreen({ worldId, worldCharacterId }: { worldId: string; worldCharacterId: string }) {
  const router = useRuntimeRouter(), searchParams = useRuntimeSearchParams();
  const activeView = parseWorldCharacterManagementView(searchParams.get("view"));
  const back = useRuntimeBack(worldCharacterDirectoryRoute(worldId));
  const selectView = useCallback((view: WorldCharacterManagementView) => {
    const next = new URLSearchParams(searchParams.toString());
    if (view === "profile") next.delete("view"); else next.set("view", view);
    const query = next.toString(), pathname = worldCharacterProfileRoute(worldId, worldCharacterId);
    router.replace(query ? `${pathname}?${query}` : pathname);
  }, [router, searchParams, worldId, worldCharacterId]);
  return <WorldCharacterManagement key={`${worldId}:${worldCharacterId}`} worldId={worldId} worldCharacterId={worldCharacterId}
    activeView={activeView} onViewChange={selectView} onBack={back} renderSettings={read => ({
      imageCard: <WorldImageGenerationCard key={`${worldId}:${worldCharacterId}:image`} worldId={worldId} actorId={worldCharacterId} />,
      visionControls: <WorldVisionControls key={`${worldId}:${worldCharacterId}:vision`} worldId={worldId} actorId={worldCharacterId} />,
      interestCard: <RecommendationTopicsPanel key={`${worldId}:${worldCharacterId}:topics`} worldId={worldId} characterId={worldCharacterId} />,
      modeCard: <PersonalizedActivityPanel key={`${worldId}:${worldCharacterId}:mode`} worldId={worldId} actorId={worldCharacterId} onlyCharacter />,
      dayCard: <WorldDailyPlanCard key={`${worldId}:${worldCharacterId}:day`} worldId={worldId} actorId={worldCharacterId} characterId={read.character_id} />,
      deleteCard: <WorldCharacterDeletionCard key={`${worldId}:${worldCharacterId}:delete`} worldId={worldId} actorId={worldCharacterId} revision={read.item.revision} name={read.item.profile.display_name} onDeleted={() => router.replace(worldCharacterDirectoryRoute(worldId))} />,
    })} renderProfile={({ read, onEditProfile }) =>
      <WorldCharacterProfile worldId={worldId} worldCharacterId={worldCharacterId} profile={read.item.profile}
        canViewGraph={read.item.capabilities.can_view_graph} onEditProfile={onEditProfile} />} />;
}
