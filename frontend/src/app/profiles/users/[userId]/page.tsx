import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { UserProfileClient } from "@/components/user-profile-client";
import { fetchBackendJson } from "@/lib/backend";
import type { ProfileRead } from "@/lib/community";
import { NO_INDEX_FOLLOW_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{
    userId: string;
  }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { userId } = await params;
  return {
    robots: NO_INDEX_FOLLOW_ROBOTS,
    alternates: {
      canonical: `/profiles/users/${userId}`,
    },
  };
}

export default async function UserProfilePage({ params }: PageProps) {
  const { userId } = await params;
  let profile: ProfileRead | null = null;
  let error: string | null = null;

  try {
    profile = await fetchBackendJson<ProfileRead>(`/api/v1/profiles/users/${userId}`);
  } catch (err) {
    error = err instanceof Error ? err.message : "프로필을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <UserProfileClient
        userId={userId}
        initialProfile={profile}
        initialError={error}
      />
    </AppShell>
  );
}
