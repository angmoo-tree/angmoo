import type { Metadata } from "next";

import { AppShell } from "@/composition/shells/app-shell";
import { LocalOwnerClient } from "@/features/identity/components/local-owner-client";
import { safeLoginReturnTo } from "@/utils/safe-navigation";
import { NO_INDEX_ROBOTS } from "@/config/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

type LoginPageProps = {
  searchParams?: Promise<{
    logout?: string | string[];
    returnTo?: string | string[];
  }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const logoutLocallyOnly = params?.logout === "local-only";
  const returnTo = safeLoginReturnTo(
    typeof params?.returnTo === "string" ? params.returnTo : null,
  );

  return (
    <AppShell>
      <LocalOwnerClient
        logoutLocallyOnly={logoutLocallyOnly}
        returnTo={returnTo}
      />
    </AppShell>
  );
}
