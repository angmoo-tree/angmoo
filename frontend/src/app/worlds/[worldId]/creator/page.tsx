import { redirect } from "next/navigation";

import { studioWorldRoute } from "@/shared/navigation/public";

type PageProps = { params: Promise<{ worldId: string }> };

export default async function WorldCreatorPage({ params }: PageProps) {
  const { worldId } = await params;
  redirect(studioWorldRoute(worldId));
}
