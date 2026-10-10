import type { Metadata } from "next";

import { AgentCreationScreen } from "@/composition/screens/agent-creation-screen";
import { AppShell } from "@/composition/shells/app-shell";
import { NO_INDEX_ROBOTS } from "@/config/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default function NewAgentPage() {
  return (
    <AppShell navigation="none">
      <AgentCreationScreen />
    </AppShell>
  );
}
