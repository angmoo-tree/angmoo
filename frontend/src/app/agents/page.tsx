import type { Metadata } from "next";

import { AgentsDashboardClient } from "@/features/characters/public";
import { AppShell } from "@/components/app-shell";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default function AgentsPage() {
  return (
    <AppShell>
      <AgentsDashboardClient />
    </AppShell>
  );
}
