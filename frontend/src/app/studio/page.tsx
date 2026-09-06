import type { Metadata } from "next";

import { CreatorStudioFrame } from "@/composition/shells/creator-studio-frame";
import { NO_INDEX_ROBOTS } from "@/config/seo";

import { StudioRouteClient } from "@/composition/screens/studio-screen";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Creator Studio · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default function CreatorStudioPage() {
  return (
    <CreatorStudioFrame activeSection="worlds">
      <StudioRouteClient />
    </CreatorStudioFrame>
  );
}
