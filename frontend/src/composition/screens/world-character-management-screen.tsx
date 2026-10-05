"use client";

import { useCallback } from "react";
import { WorldCharacterManagement } from "@/features/characters/components/world-character-management";
import type { WorldCharacterManagementView } from "@/features/characters/types/world-character-management";
import { parseWorldCharacterManagementView } from "@/features/characters/utils/world-character-dashboard-presentation";
import { useRuntimeBack, useRuntimeRouter, useRuntimeSearchParams } from "@/hooks/use-runtime-navigation";
import { worldCharacterDirectoryRoute, worldCharacterProfileRoute } from "@/lib/navigation/product-routes";
import { WorldCharacterProfile } from "./world-character-profile-screen";

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
    activeView={activeView} onViewChange={selectView} onBack={back} renderProfile={({ read, onEditProfile }) =>
      <WorldCharacterProfile worldId={worldId} worldCharacterId={worldCharacterId} profile={read.item.profile}
        canViewGraph={read.item.capabilities.can_view_graph} onEditProfile={onEditProfile} />} />;
}
