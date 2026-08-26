import type { Metadata } from "next";

import { CreatorStudioFrame } from "@/features/creator-studio/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { StudioImportRouteClient } from "./studio-import-route-client";

export const metadata: Metadata = {
  title: "World Import · Creator Studio · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default function StudioImportPage() {
  return (
    <CreatorStudioFrame activeSection="import">
      <StudioImportRouteClient />
    </CreatorStudioFrame>
  );
}
