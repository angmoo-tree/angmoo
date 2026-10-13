"use client";

import { Network } from "lucide-react";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { SettingsCard } from "@/components/ui/settings-card";
import { RelationshipGraphClient } from "@/features/relationships/components/relationship-graph-client";
import { useUiText } from "@/hooks/use-ui-text";
import { studioWorldRoute } from "@/lib/navigation/product-routes";

export function WorldRelationshipsScreen({ characterId, worldId }: { characterId: string | null; worldId: string }) {
  const uiText = useUiText("relationships");
  if (!characterId) return (
    <div className="px-4 py-6 md:px-9">
    <SettingsCard elevated title={uiText("World 관계망")} description={uiText("World 관리에서 관계망의 기준 프로필을 확인해주세요.")} icon={<Network size={20} />}>
      <p>{uiText("이 World의 내 프로필이 아직 연결되지 않았습니다. 관계 조회는 새 프로필을 만들지 않습니다.")}</p>
      <LocalProductLink href={studioWorldRoute(worldId)}>{uiText("World 관리 열기")}</LocalProductLink>
    </SettingsCard>
    </div>
  );
  return <RelationshipGraphClient key={`${worldId}:${characterId}`} characterId={characterId} worldId={worldId} embedded />;
}
