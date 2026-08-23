"use client";

import { useAuth } from "@/components/auth-provider";
import { WorldApp, type WorldAppSectionId } from "@/features/world-app/public";


export function WorldAppRouteClient({
  postId,
  sectionId,
  worldId,
}: {
  postId?: string;
  sectionId: WorldAppSectionId;
  worldId: string;
}) {
  const { status } = useAuth();
  return (
    <WorldApp
      authStatus={status}
      key={worldId}
      postId={postId}
      sectionId={sectionId}
      worldId={worldId}
    />
  );
}
