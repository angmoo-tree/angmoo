import type { Metadata } from "next";

import { AgentDetailClient } from "@/components/agent-detail-client";
import { AppShell } from "@/components/app-shell";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

type PageProps = {
  params: Promise<{
    characterId: string;
  }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default async function AgentDetailPage({ params }: PageProps) {
  const { characterId } = await params;
  return (
    <AppShell>
      <AgentDetailClient characterId={characterId} />
    </AppShell>
  );
}
