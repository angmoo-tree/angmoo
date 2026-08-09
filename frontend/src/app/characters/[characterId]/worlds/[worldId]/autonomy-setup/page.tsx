import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { WorldCharacterAutonomySetupClient } from "@/components/world-character-autonomy-setup-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

type PageProps = {
  params: Promise<{ characterId: string; worldId: string }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World 활동 준비 · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function WorldCharacterAutonomySetupPage({ params }: PageProps) {
  const { characterId, worldId } = await params;
  return (
    <AppShell>
      <WorldCharacterAutonomySetupClient
        characterId={characterId}
        worldId={worldId}
      />
    </AppShell>
  );
}
