import type { Metadata } from "next";

import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { WorldAppRouteClient } from "../../world-app-route-client";


type PageProps = { params: Promise<{ worldId: string }> };

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World App · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function WorldAppPage({ params }: PageProps) {
  const { worldId } = await params;
  return <WorldAppRouteClient sectionId="home" worldId={worldId} />;
}
