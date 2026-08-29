import type { Metadata } from "next";

import {
  RelationshipGraphClient,
  RelationshipGraphFrame,
} from "@/features/relationships/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

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
  return (
    <RelationshipGraphFrame>
      <RelationshipGraphClient
        characterId={characterId}
        worldId={worldId}
        provider="ladybug"
      />
    </RelationshipGraphFrame>
  );
}
