"use client";

import { useAuth } from "@/hooks/use-auth";
import { WorldApp } from "@/composition/screens/world-app";
import { type WorldAppSectionId } from "@/composition/shells/world-app-navigation";


export function WorldAppRouteClient({
  chatThreadId,
  postId,
  sectionId,
  worldCharacterId,
  worldId,
}: {
  chatThreadId?: string;
  postId?: string;
  sectionId: WorldAppSectionId;
  worldCharacterId?: string;
  worldId: string;
}) {
  const { status } = useAuth();
  return (
    <WorldApp
      authStatus={status}
      chatThreadId={chatThreadId}
      key={`${worldId}:${chatThreadId ?? "section"}`}
      postId={postId}
      sectionId={sectionId}
      worldCharacterId={worldCharacterId}
      worldId={worldId}
    />
  );
}
