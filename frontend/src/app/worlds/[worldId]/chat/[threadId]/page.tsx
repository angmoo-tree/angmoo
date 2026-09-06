import type { Metadata } from "next";

import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { WorldAppRouteClient } from "@/composition/screens/world-app-screen";

type PageProps = {
  params: Promise<{ threadId: string; worldId: string }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World Chat · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function WorldChatThreadPage({ params }: PageProps) {
  const { threadId, worldId } = await params;
  return (
    <WorldAppRouteClient
      chatThreadId={threadId}
      sectionId="chat"
      worldId={worldId}
    />
  );
}
