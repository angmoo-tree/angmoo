import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { CharacterProfileClient } from "@/components/character-profile-client";
import { fetchBackendJson } from "@/lib/backend";
import type { FeedPage, ProfileFeedTab, ProfileRead } from "@/lib/community";
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

function toProfileFeedTab(value: string | undefined): ProfileFeedTab {
  if (value === "replies" || value === "likes") return value;
  return "posts";
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { characterId } = await params;
  return {
    robots: NO_INDEX_FOLLOW_ROBOTS,
    alternates: {
      canonical: `/profiles/characters/${characterId}`,
    },
  };
}

export default async function CharacterProfilePage({ params, searchParams }: PageProps) {
  const { characterId } = await params;
  const tab = toProfileFeedTab((await searchParams)?.tab);
  let profile: ProfileRead | null = null;
  let feed: FeedPage | null = null;
  let error: string | null = null;

  try {
    [profile, feed] = await Promise.all([
      fetchBackendJson<ProfileRead>(`/api/v1/profiles/characters/${characterId}`),
      fetchBackendJson<FeedPage>(
        `/api/v1/profiles/characters/${characterId}/feed?tab=${tab}&limit=5`,
      ),
    ]);
  } catch (err) {
    error = err instanceof Error ? err.message : "프로필을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <CharacterProfileClient
        key={`${characterId}:${tab}`}
        characterId={characterId}
        initialProfile={profile}
        initialFeed={feed}
        activeTab={tab}
        initialError={error}
      />
    </AppShell>
  );
}
