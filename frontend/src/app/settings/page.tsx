import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { SettingsClient } from "@/components/settings-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default function SettingsPage() {
  return (
    <AppShell>
      <SettingsClient />
    </AppShell>
  );
}
