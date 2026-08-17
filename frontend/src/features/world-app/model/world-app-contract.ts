import { worldAppRoute } from "@/shared/navigation/public";

export type WorldAppSectionId =
  | "home"
  | "feed"
  | "chat"
  | "characters"
  | "relationships";

export type WorldAppSection = {
  id: WorldAppSectionId;
  label: string;
  segment: string;
};

export const WORLD_APP_SECTIONS: readonly WorldAppSection[] = [
  { id: "home", label: "Home", segment: "" },
  { id: "feed", label: "Feed", segment: "feed" },
  { id: "chat", label: "Chat", segment: "chat" },
  { id: "characters", label: "Characters", segment: "characters" },
  { id: "relationships", label: "Relationships", segment: "relationships" },
] as const;

export function worldAppSectionRoute(
  worldId: string,
  section: WorldAppSection,
): string {
  const root = worldAppRoute(worldId);
  return section.segment ? `${root}/${section.segment}` : root;
}
