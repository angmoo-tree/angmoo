import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { MessagesClient } from "@/features/chat/public";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

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
