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
    characterId: string;
  }>;
  searchParams?: Promise<{
    tab?: string;
  }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { characterId } = await params;
  return {
    robots: NO_INDEX_FOLLOW_ROBOTS,
    alternates: {
      canonical: `/profiles/characters/${characterId}/follows`,
    },
  };
}

export default async function CharacterFollowsPage({ params, searchParams }: PageProps) {
  const { characterId } = await params;
  const tab = toConnectionTab((await searchParams)?.tab);
  let profile: ProfileRead | null = null;
  let page: ProfileListPage | null = null;
  let error: string | null = null;

  try {
    [profile, page] = await Promise.all([
      fetchBackendJson<ProfileRead>(`/api/v1/profiles/characters/${characterId}`),
      fetchBackendJson<ProfileListPage>(
        `/api/v1/profiles/characters/${characterId}/connections?tab=${tab}&limit=10`,
      ),
    ]);
  } catch (err) {
    error = err instanceof Error ? err.message : "팔로우 목록을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <ProfileConnectionsClient
        key={`${characterId}:${tab}`}
        profileKind="character"
        profileId={characterId}
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
