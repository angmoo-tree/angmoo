import type { Metadata } from "next";

import { AppShell } from "@/composition/shells/app-shell";
import { NotificationsClient } from "@/features/social/components/notifications-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default function NotificationsPage() {
  return (
    <AppShell>
      <NotificationsClient />
    </AppShell>
  );
}
