"use client";

import { useAuth } from "@/components/auth-provider";
import { WorldApp, type WorldAppSectionId } from "@/features/world-app/public";


export function WorldAppRouteClient({
  chatThreadId,
  postId,
  sectionId,
  worldId,
}: {
  chatThreadId?: string;
  postId?: string;
  sectionId: WorldAppSectionId;
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
      worldId={worldId}
    />
  );
}
