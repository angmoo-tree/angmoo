import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { ProfileSetupClient } from "@/components/profile-setup-client";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

export default function ProfileSetupPage() {
  return (
    <AppShell>
      <ProfileSetupClient />
    </AppShell>
  );
}
