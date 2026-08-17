import type { Metadata } from "next";

import { WorldCreatorClient } from "@/components/world-creator-client";
import { CreatorStudioFrame } from "@/features/creator-studio/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "새 World · Creator Studio · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default function NewStudioWorldPage() {
  return (
    <CreatorStudioFrame activeSection="new-world">
      <WorldCreatorClient />
    </CreatorStudioFrame>
  );
}
