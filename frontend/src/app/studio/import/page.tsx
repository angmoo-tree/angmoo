import type { Metadata } from "next";

import { CreatorStudioFrame } from "@/composition/shells/creator-studio-frame";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { StudioImportRouteClient } from "@/composition/screens/studio-import-screen";

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
