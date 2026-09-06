import type { Metadata } from "next";

import { AppShell } from "@/composition/shells/app-shell";
import { SettingsClient } from "@/composition/screens/settings-screen";
import { NO_INDEX_ROBOTS } from "@/config/seo";

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
