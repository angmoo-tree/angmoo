import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { worldAppSectionFromSegment } from "@/features/world-app/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { WorldAppRouteClient } from "../../../world-app-route-client";


type PageProps = {
  params: Promise<{ section: string; worldId: string }>;
};

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "World App · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default async function WorldAppSectionPage({ params }: PageProps) {
  const { section, worldId } = await params;
  const activeSection = worldAppSectionFromSegment(section);
  if (!activeSection) notFound();
  return <WorldAppRouteClient sectionId={activeSection.id} worldId={worldId} />;
}
