"use client";

import { useAuth } from "@/components/auth-provider";
import { WorldApp, type WorldAppSectionId } from "@/features/world-app/public";


export function WorldAppRouteClient({
  sectionId,
  worldId,
}: {
  sectionId: WorldAppSectionId;
  worldId: string;
}) {
  const { status } = useAuth();
  return (
    <WorldApp
      authStatus={status}
      key={worldId}
      sectionId={sectionId}
      worldId={worldId}
    />
  );
}
