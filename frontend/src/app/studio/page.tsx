import type { Metadata } from "next";

import {
  CreatorStudioFrame,
} from "@/features/creator-studio/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

import { StudioRouteClient } from "./studio-route-client";

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
