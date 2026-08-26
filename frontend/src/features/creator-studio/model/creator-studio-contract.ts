import { PRODUCT_ROUTES } from "@/shared/navigation/public";

export type CreatorStudioSectionId = "worlds" | "new-world" | "import";

export type CreatorStudioSection = {
  id: CreatorStudioSectionId;
  label: string;
  href: string;
  availability: "available" | "planned";
};

export const CREATOR_STUDIO_SECTIONS: readonly CreatorStudioSection[] = [
  {
    id: "worlds",
    label: "Worlds",
    href: PRODUCT_ROUTES.studio,
    availability: "available",
  },
  {
    id: "new-world",
    label: "새 World",
    href: PRODUCT_ROUTES.studioNewWorld,
    availability: "available",
  },
  {
    id: "import",
    label: "Import",
    href: PRODUCT_ROUTES.studioImport,
    availability: "available",
  },
] as const;
