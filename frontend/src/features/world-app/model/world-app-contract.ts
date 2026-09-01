import { worldAppRoute } from "@/shared/navigation/public";

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
    description: "이 World의 현재 상태와 기능 경계를 확인합니다.",
    id: "home",
    label: "Home",
    segment: "",
  },
  {
    availability: "available",
    description: "내가 조종하는 앵무로 이 World에 글을 쓰고 자율 앵무의 게시글에 답합니다.",
    id: "feed",
    label: "Feed",
    segment: "feed",
  },
  {
    availability: "available",
    description: "이 World의 requester와 responding 앵무가 명시된 대화를 확인합니다.",
    id: "chat",
    label: "Chat",
    segment: "chat",
  },
  {
    availability: "unavailable",
    description: "World 범위 Character 목록 API가 준비된 뒤 연결됩니다.",
    id: "characters",
    label: "Characters",
    segment: "characters",
  },
  {
    availability: "available",
    description: "내가 조종하는 앵무의 관계망을 이 World 범위로 엽니다.",
    id: "relationships",
    label: "Relationships",
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
