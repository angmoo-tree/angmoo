import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { RelationshipGraphClient } from "@/components/relationship-graph-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

type PageProps = {
  params: Promise<{ characterId: string; worldId: string }>;
  searchParams: Promise<{ provider?: string }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World 관계망 · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function RelationshipGraphPage({ params, searchParams }: PageProps) {
  const { characterId, worldId } = await params;
  const { provider: requestedProvider } = await searchParams;
  const provider = requestedProvider === "ladybug" ? "ladybug" : "neo4j";
  return (
    <AppShell>
      <RelationshipGraphClient
        characterId={characterId}
        worldId={worldId}
        provider={provider}
      />
    </AppShell>
  );
}
