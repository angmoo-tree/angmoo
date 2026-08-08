import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { WorldCreatorClient } from "@/components/world-creator-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "새 World 만들기 · Angmoo",
  robots: NO_INDEX_ROBOTS,
};

export default function NewWorldPage() {
  return <AppShell><WorldCreatorClient /></AppShell>;
}
