import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { ProfileConnectionsClient } from "@/components/profile-connections-client";
import { fetchBackendJson } from "@/lib/backend";
import type {
  ProfileConnectionTab,
  ProfileListPage,
  ProfileRead,
} from "@/lib/community";
import { NO_INDEX_FOLLOW_ROBOTS } from "@/lib/seo";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{
    userId: string;
  }>;
  searchParams?: Promise<{
    tab?: string;
  }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { userId } = await params;
  return {
    robots: NO_INDEX_FOLLOW_ROBOTS,
    alternates: {
      canonical: `/profiles/users/${userId}/follows`,
    },
  };
}

export default async function UserFollowsPage({ params, searchParams }: PageProps) {
  const { userId } = await params;
  const tab = toConnectionTab((await searchParams)?.tab);
  let profile: ProfileRead | null = null;
  let page: ProfileListPage | null = null;
  let error: string | null = null;

  try {
    [profile, page] = await Promise.all([
      fetchBackendJson<ProfileRead>(`/api/v1/profiles/users/${userId}`),
      fetchBackendJson<ProfileListPage>(
        `/api/v1/profiles/users/${userId}/connections?tab=${tab}&limit=10`,
      ),
    ]);
  } catch (err) {
    error = err instanceof Error ? err.message : "팔로우 목록을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <ProfileConnectionsClient
        key={`${userId}:${tab}`}
        profileKind="user"
        profileId={userId}
        initialProfile={profile}
        initialPage={page}
        activeTab={tab}
        initialError={error}
      />
    </AppShell>
  );
}

function toConnectionTab(value: string | undefined): ProfileConnectionTab {
  if (value === "character_followers" || value === "user_followers") return value;
  return "following";
}
