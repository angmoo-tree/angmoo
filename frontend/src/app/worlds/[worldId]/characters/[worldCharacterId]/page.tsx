import type { Metadata } from "next";

import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { WorldAppRouteClient } from "../../../../world-app-route-client";

type PageProps = {
  params: Promise<{ worldCharacterId: string; worldId: string }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World Character · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function WorldCharacterProfilePage({ params }: PageProps) {
  const { worldCharacterId, worldId } = await params;
  return (
    <WorldAppRouteClient
      sectionId="characters"
      worldCharacterId={worldCharacterId}
      worldId={worldId}
    />
  );
}
