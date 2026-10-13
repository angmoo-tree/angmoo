import type { Metadata } from "next";

import { WorldAppRouteClient } from "@/composition/screens/world-app-screen";
import { NO_INDEX_ROBOTS } from "@/config/seo";

type PageProps = {
  params: Promise<{ characterId: string; worldId: string }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World 관계망 · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function RelationshipGraphPage({ params }: PageProps) {
  const { characterId, worldId } = await params;
  return <WorldAppRouteClient sectionId="relationships" relationshipCharacterId={characterId} worldId={worldId} />;
}
