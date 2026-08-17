import type { Metadata } from "next";

import { WorldCreatorClient } from "@/components/world-creator-client";
import { CreatorStudioFrame } from "@/features/creator-studio/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

type PageProps = { params: Promise<{ worldId: string }> };

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World 편집 · Creator Studio · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function StudioWorldPage({ params }: PageProps) {
  const { worldId } = await params;
  return (
    <CreatorStudioFrame activeSection="worlds">
      <WorldCreatorClient worldId={worldId} />
    </CreatorStudioFrame>
  );
}
