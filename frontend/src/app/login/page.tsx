import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { LoginClient } from "@/components/login-client";
import { safeLoginReturnTo } from "@/lib/safe-navigation";
import { NO_INDEX_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  robots: NO_INDEX_ROBOTS,
};

type LoginPageProps = {
  searchParams?: Promise<{
    logout?: string | string[];
    mode?: string | string[];
    returnTo?: string | string[];
  }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const emailLoginEnabled = params?.mode === "email";
  const logoutLocallyOnly = params?.logout === "local-only";
  const returnTo = safeLoginReturnTo(
    typeof params?.returnTo === "string" ? params.returnTo : null,
  );

  return (
    <AppShell>
      <LoginClient
        emailLoginEnabled={emailLoginEnabled}
        logoutLocallyOnly={logoutLocallyOnly}
        returnTo={returnTo}
      />
    </AppShell>
  );
}
