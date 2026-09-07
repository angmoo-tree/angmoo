import type { Metadata } from "next";

import { AppShell } from "@/composition/shells/app-shell";
import { MessagesClient } from "@/features/chat/components/messages-client";
import { NO_INDEX_ROBOTS } from "@/config/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default function MessagesPage() {
  return (
    <AppShell>
      <MessagesClient />
    </AppShell>
  );
}
