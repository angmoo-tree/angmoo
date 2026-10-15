import type { Metadata } from "next";
import { NO_INDEX_ROBOTS } from "@/config/seo";
import { WorldAppRouteClient } from "@/composition/screens/world-app-screen";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Notifications · Angmoo", robots: NO_INDEX_ROBOTS };
export default async function WorldNotificationsPage({ params }: { params: Promise<{ worldId: string }> }) {
  const { worldId } = await params;
  return <WorldAppRouteClient worldId={worldId} sectionId="feed" notifications />;
}
