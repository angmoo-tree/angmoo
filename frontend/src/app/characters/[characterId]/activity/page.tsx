import { AppShell } from "@/components/app-shell";
import { CharacterActivityClient } from "@/components/character-activity-client";
import { fetchBackendJson } from "@/lib/backend";
import type { CharacterActivityRead } from "@/lib/community";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{
    characterId: string;
  }>;
};

export default async function CharacterActivityPage({ params }: PageProps) {
  const { characterId } = await params;
  let activity: CharacterActivityRead | null = null;
  let error: string | null = null;

  try {
    activity = await fetchBackendJson<CharacterActivityRead>(
      `/api/v1/characters/${characterId}/activity`,
    );
  } catch (err) {
    error = err instanceof Error ? err.message : "활동을 불러오지 못했습니다.";
  }

  return (
    <AppShell>
      <CharacterActivityClient
        characterId={characterId}
        initialActivity={activity}
        initialError={error}
      />
    </AppShell>
  );
}
