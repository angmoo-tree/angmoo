import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { WorldCreatorClient } from "@/components/world-creator-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

type PageProps = { params: Promise<{ worldId: string }> };

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World 제작 스튜디오 · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function WorldCreatorPage({ params }: PageProps) {
  const { worldId } = await params;
  return <AppShell><WorldCreatorClient worldId={worldId} /></AppShell>;
}
