import type { Metadata } from "next";

import { AgentCreateClient } from "@/components/agent-create-client";
import { AppShell } from "@/components/app-shell";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default function NewAgentPage() {
  return (
    <AppShell>
      <AgentCreateClient />
    </AppShell>
  );
}
