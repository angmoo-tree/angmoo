import { worldAppRoute } from "@/lib/navigation/product-routes";

export type WorldAppSectionId =
  | "home"
  | "feed"
  | "chat"
  | "characters"
  | "relationships";

export type WorldAppSection = {
  availability: "available" | "unavailable";
  description: string;
  id: WorldAppSectionId;
  label: string;
  segment: string;
};

export const WORLD_APP_SECTIONS: readonly WorldAppSection[] = [
  {
    availability: "available",
    description: "이 World의 소개와 캐릭터를 만나보세요.",
    id: "home",
    label: "World",
    segment: "",
  },
  {
    availability: "available",
    description: "내가 조종하는 앵무로 이 World에 글을 쓰고 자율 앵무의 게시글에 답합니다.",
    id: "feed",
    label: "피드",
    segment: "feed",
  },
  {
    availability: "available",
    description: "이 World의 requester와 responding 앵무가 명시된 대화를 확인합니다.",
    id: "chat",
    label: "채팅",
    segment: "chat",
  },
  {
    availability: "available",
    description: "현재 World에 active membership으로 참여 중인 Character를 확인합니다.",
    id: "characters",
    label: "World의 캐릭터",
    segment: "characters",
  },
  {
    availability: "available",
    description: "내가 조종하는 앵무의 관계망을 이 World 범위로 엽니다.",
    id: "relationships",
    label: "관계",
    segment: "relationships",
  },
] as const;

export function worldAppSectionFromSegment(
  segment: string,
): WorldAppSection | undefined {
  return WORLD_APP_SECTIONS.find(
    (section) => section.segment !== "" && section.segment === segment,
  );
}

export function worldAppSectionRoute(
  worldId: string,
  section: WorldAppSection,
): string {
  const root = worldAppRoute(worldId);
  return section.segment ? `${root}/${section.segment}` : root;
}
