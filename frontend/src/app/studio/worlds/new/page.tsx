import type { Metadata } from "next";

import { WorldCreatorClient } from "@/composition/screens/world-creator-screen";
import { CreatorStudioFrame } from "@/composition/shells/creator-studio-frame";
import { NO_INDEX_ROBOTS } from "@/config/seo";

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
