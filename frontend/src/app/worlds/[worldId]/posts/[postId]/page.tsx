import type { Metadata } from "next";

import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { WorldAppRouteClient } from "../../../../world-app-route-client";


type PageProps = {
  params: Promise<{ postId: string; worldId: string }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World 게시글 · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function WorldPostDetailPage({ params }: PageProps) {
  const { postId, worldId } = await params;
  return (
    <WorldAppRouteClient
      postId={postId}
      sectionId="feed"
      worldId={worldId}
    />
  );
}
