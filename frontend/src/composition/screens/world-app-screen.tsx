"use client";

import { useAuth } from "@/hooks/use-auth";
import { WorldApp } from "@/composition/screens/world-app";
import { type WorldAppSectionId } from "@/composition/shells/world-app-navigation";


export function WorldAppRouteClient({
  chatThreadId,
  postId,
  notifications,
  relationshipCharacterId,
  sectionId,
  worldCharacterId,
  worldId,
}: {
  chatThreadId?: string;
  postId?: string;
  notifications?: boolean;
  relationshipCharacterId?: string;
  sectionId: WorldAppSectionId;
  worldCharacterId?: string;
  worldId: string;
}) {
  const { status, user, sessionRevision } = useAuth();
  return (
    <WorldApp
      authStatus={status}
      chatThreadId={chatThreadId}
      key={`${user?.id ?? ""}:${sessionRevision ?? 0}:${worldId}:${chatThreadId ?? "section"}`}
      postId={postId}
      notifications={notifications}
      relationshipCharacterId={relationshipCharacterId}
      sectionId={sectionId}
      worldCharacterId={worldCharacterId}
      worldId={worldId}
    />
  );
}
